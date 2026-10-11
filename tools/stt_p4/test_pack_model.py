#!/usr/bin/env python3
"""Model envelope format, identity binding, and refusal tests (no private model)."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parent


class PackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hw1-stt-pack-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        # Only envelope/integrity behavior is under test; this is not a runnable graph.
        self.raw = b'EDL2' + struct.pack('<III', 0, 256, 0) + bytes(range(256))
        self.frontend = '37' * 32
        (self.directory/'quartznet.espdl').write_bytes(self.raw)
        self.manifest = {
            'stage':'full', 'frontend':'portable', 'target':'esp32p4',
            'frontend_contract_sha256':self.frontend,
            'model':{'file':'quartznet.espdl','bytes':len(self.raw),
                     'sha256':hashlib.sha256(self.raw).hexdigest()},
            'runtime':{'inputs':[{'name':'input.1','dtype':3,'exponents':[-5]}],
                       'outputs':[{'name':'189','dtype':3,'exponents':[-2]}], 'node_count':71}}

    def run_pack(self, frontend=None):
        path = self.directory/'manifest.json'
        path.write_text(json.dumps(self.manifest))
        return subprocess.run([sys.executable,str(HERE/'pack_model.py'),'--manifest',str(path),
                               '--frontend-sha256',frontend or self.frontend],capture_output=True,text=True)

    def test_roundtrip_and_identity_header(self):
        result = self.run_pack()
        self.assertEqual(result.returncode,0,result.stderr)
        data = (self.directory/'quartznet5x5.p4.stt').read_bytes()
        fields = struct.unpack('<8sIIIIII32s32s',data[:96])
        self.assertEqual(fields[:4],(b'HW1STT1\0',1,1,len(self.raw)))
        self.assertEqual(fields[4],len(data)-96)
        self.assertEqual(fields[5:7],(16000,480000))
        self.assertEqual(fields[7],hashlib.sha256(self.raw).digest())
        self.assertEqual(fields[8],bytes.fromhex(self.frontend))
        self.assertEqual(zlib.decompress(data[96:]),self.raw)
        header = (self.directory/'stt_model_identity.h').read_text()
        for needle in ['namespace hw1::stt::identity','kInputName[] = "input.1"',
                       'kInputExponent = -5','kOutputExponent = -2','kNodeCount = 71']:
            self.assertIn(needle,header)

    def test_model_change_refused(self):
        (self.directory/'quartznet.espdl').write_bytes(self.raw[:-1]+b'X')
        self.assertNotEqual(self.run_pack().returncode,0)
        self.assertFalse((self.directory/'quartznet5x5.p4.stt').exists())

    def test_wrong_frontend_refused(self):
        self.assertNotEqual(self.run_pack('38'*32).returncode,0)
        self.assertFalse((self.directory/'quartznet5x5.p4.stt').exists())

    def test_unsupported_dtype_refused_before_artifact(self):
        self.manifest['runtime']['inputs'][0]['dtype']=5
        self.assertNotEqual(self.run_pack().returncode,0)
        self.assertFalse((self.directory/'quartznet5x5.p4.stt').exists())


if __name__=='__main__': unittest.main()
