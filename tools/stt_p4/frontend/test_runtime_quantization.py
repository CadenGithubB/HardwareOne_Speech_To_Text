#!/usr/bin/env python3
"""Compile the actual runtime quantizer and compare it with NumPy nearest-even."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import numpy as np
HERE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE.parent/'private/frontend')
    args=parser.parse_args()
    source=(HERE.parents[2]/'components/hardwareone/stt/quartznet_runtime.cpp').read_text()
    start=source.index('        const float scale=')
    end=source.index('\n    }\n    stats.frontendMs',start)
    actual=source[start:end].replace('identity::kInputExponent','exponent').replace('frames*64','count')
    # Only the two names above are adapted; the rounding/saturation body is compiled unchanged.
    program='''#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <vector>
int main(int argc,char**argv) {
 if(argc!=3)return 2;
 std::ifstream in(argv[1],std::ios::binary|std::ios::ate);auto bytes=in.tellg();
 if(bytes<0||bytes%4)return 3;
 size_t count=static_cast<size_t>(bytes)/4;std::vector<float>values(count);in.seekg(0);in.read(reinterpret_cast<char*>(values.data()),bytes);
 std::vector<int8_t>quantized(count);const float*f=values.data();int8_t*q=quantized.data();int exponent=-5;
'''+actual+'''
 std::ofstream out(argv[2],std::ios::binary);out.write(reinterpret_cast<const char*>(q),count);return out?0:4;
}
'''
    args.output.mkdir(parents=True,exist_ok=True)
    results=[]
    with tempfile.TemporaryDirectory(prefix='hw1-stt-quantizer-') as temporary:
        directory=Path(temporary);cpp=directory/'check.cpp';binary=directory/'check';cpp.write_text(program)
        subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(cpp),'-o',str(binary)],check=True)
        ties=(np.arange(-4096,4097,dtype=np.float32)+np.float32(0.5))/32
        rng=np.random.default_rng(117)
        values=np.concatenate([ties,np.nextafter(ties,np.float32(-np.inf)),np.nextafter(ties,np.float32(np.inf)),rng.uniform(-100,100,100000).astype(np.float32)])
        cases=[('ties_saturation_random',values)]
        for name in ['0','1']:
            path=args.output/(name+'.features.f32le')
            if path.exists():cases.append((name,np.fromfile(path,dtype='<f4')))
        for name,values in cases:
            input_path=directory/'values.bin';output_path=directory/'int8.bin';values.astype('<f4').tofile(input_path)
            subprocess.run([str(binary),str(input_path),str(output_path)],check=True)
            actual_q=np.fromfile(output_path,dtype=np.int8)
            reference_q=np.clip(np.rint(values*np.float32(32)),-128,127).astype(np.int8)
            if not np.array_equal(actual_q,reference_q):raise AssertionError('Runtime quantization differs from NumPy: '+name)
            item={'name':name,'values':len(values),'cpp_numpy_exact':True,'input_int8_sha256':hashlib.sha256(output_path.read_bytes()).hexdigest()}
            reference_path=args.output/(name+'.reference.npy')
            if reference_path.exists():
                reference_features=np.load(reference_path).reshape(-1)
                reference_q=np.clip(np.rint(reference_features*np.float32(32)),-128,127).astype(np.int8)
                item['cpp_vs_torch_quantized_feature_differences']=int(np.count_nonzero(actual_q!=reference_q))
                item['cpp_vs_torch_quantized_feature_max_error']=int(np.max(np.abs(actual_q.astype(int)-reference_q.astype(int))))
            results.append(item);print(json.dumps(item),flush=True)
    report={'scope':'Actual runtime rounding code, host ASan/UBSan; exponent -5','results':results}
    (args.output/'quantization-results.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
