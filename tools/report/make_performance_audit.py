"""Derive the audit's public evidence without private logs or hardware access."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent


def build():
    breakdown = json.loads((REPORT / 'breakdown.json').read_text())
    layers = json.loads((REPORT / 'layers.json').read_text())['c12']
    versions = json.loads((REPORT / 'versions.json').read_text())
    identity = (ROOT / 'firmware/components/hw1_stt/stt/stt_model_identity.h').read_text()
    raw_bytes = int(re.search(r'kRawBytes = (\d+)', identity)[1])
    phases = ['wait', 'trigger', 'queue', 'rebuild', 'features', 'pw', 'dw', 'other', 'lm', 'delivery']
    timings = {}
    for group in ['short', 'all', 'longer']:
        row = breakdown['v1.8/' + group]
        # Tiny decimal discrepancies are expected from the original source aggregates.
        assert abs(sum(row[key] for key in phases) - row['iqm_L']) < .002
        timings[group] = row
    evidence = {
        'schema': 1,
        'audit_date': '2026-10-31',
        'controlled_benchmark_this_audit': False,
        'historical': {
            'period': '2026-10-10 through 2026-10-11',
            'build': 'v1.8 / c12, with early final scheduling; not standalone app_main',
            'latency_seconds': timings,
            'latency_statistic': 'interquartile mean; layer split allocated from stage-profile fits',
            'layers_five_second_audio_seconds': layers,
            'memory_v1_8': {k: versions['1.8'][k] for k in
                            ['psram_low_mb', 'psram_warm_mb', 'internal_low_kb']},
            'memory_units': 'decimal MB and kB; divide bytes by 2**20 / 2**10 for MiB / KiB',
            'sources': ['tools/report/breakdown.json', 'tools/report/layers.json',
                        'tools/report/versions.json', 'docs/index.html'],
        },
        'current_source': {
            'psram_physical_bytes': 32 * 1024**2,
            'retained_model_bytes': raw_bytes,
            'retained_pcm_bytes': 3 * 10 * 16000 * 2,
            'lm_options': [
                {'label': 'LM not loaded', 'bytes': 0, 'evidence': 'possible fallback'},
                {'label': '1.6 MB LM (approx.)', 'bytes': 1600000,
                 'evidence': 'approximate size only; Oct 21 qualification used this class'},
                {'label': 'Archive LM: 2.5 MB', 'bytes': 2499996,
                 'evidence': 'archive manifest exact asset size; current card unknown'},
            ],
            'frontend_bytes_per_frame': 64 * 4,
            'samples_per_frame': 160,
            'frontend_workspace_bytes_approx': 8200,
            'model_header_logical_bytes_per_call': 96,
            'endpoint_silence_seconds': {'long_eligible': .6, 'short_close': 1.0},
            'actual_heap_peaks': None,
            'physical_flash_read_counts': None,
            'sources': ['firmware/examples/p4_eye_captions/main/main.cpp',
                        'firmware/components/hw1_stt/stt/stt_model_identity.h',
                        'firmware/components/hw1_stt/stt/quartznet_frontend.h',
                        'firmware/components/hw1_stt/stt/stt_model_container.h'],
        },
    }
    device = ROOT / 'docs/performance-device-summary.json'
    if device.exists():
        evidence['connected_device'] = json.loads(device.read_text())
    live=ROOT/'docs/performance-glasses-live.json'
    if live.exists():
        evidence['fresh_glasses_profile']=json.loads(live.read_text())
    return evidence


if __name__ == '__main__':
    dest = ROOT / 'docs/performance-evidence.json'
    dest.write_text(json.dumps(build(), indent=2) + '\n')
    print(dest)
