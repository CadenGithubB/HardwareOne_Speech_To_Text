#!/usr/bin/env python3
"""Create the isolated CPU exporter overlay without replacing inspected Torch.

Run with the Python executable from the inspected checkpoint environment.
Existing base packages are read through a .pth; pip writes only the new venv.
"""
import argparse
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-venv',type=Path,default=HERE.parent/'speech_portable/private/stt-quartznet/venv')
    p.add_argument('--venv',type=Path,default=HERE/'private/export-venv')
    args=p.parse_args()
    base=args.base_venv.resolve(); target=args.venv.resolve()
    if target.exists(): p.error('Target environment already exists; use a new path')
    base_python=base/'bin/python'
    site=subprocess.check_output([str(base_python),'-c','import site;print(site.getsitepackages()[0])'],text=True).strip()
    subprocess.run([str(base_python),'-m','venv',str(target)],check=True)
    python=target/'bin/python'
    target_site=subprocess.check_output([str(python),'-c','import site;print(site.getsitepackages()[0])'],text=True).strip()
    (Path(target_site)/'inspected_torch_environment.pth').write_text(site+'\n')
    subprocess.run([str(python),'-m','pip','install','-r',str(HERE/'export-requirements.txt')],check=True)
    print('Exporter Python:',python)

if __name__=='__main__':main()
