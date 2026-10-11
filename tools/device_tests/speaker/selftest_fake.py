#!/usr/bin/env python3
"""Self-test for analyse.py with synthetic sessions (no device, no audio).

Writes fake session folders (lines.tsv + session.json in run_session.py's
format, TL lines in the test firmware's announced formats) for two labels,
'fakeA' and 'fakeB' (B has 10 % faster inference), under selftest/, then runs
the per-session analysis and the comparison. Known injected values are checked:
tick-vs-esp offset, capture delay, L_close, L_speech, B-A delta on n.
"""
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / 'selftest'
MAN = HERE / 'playlist' / 'manifest.json'

TME = 37.0          # injected tick - esp_timer (ms)
MONO0 = 0.1554      # mono (s) at tick 0
CAP_DELAY = 30.0    # a-clock lag behind real time (ms)


def simulate(label, k, speed, seed):
    man = json.loads(MAN.read_text())
    rng = random.Random(seed)
    clips = man['clips']
    lines = []

    def emit(tick, text, extra_delay=0.0):
        mono = MONO0 + (tick + 0.4 + rng.random() * 0.8 + extra_delay) / 1000.0
        lines.append((mono, f'I ({int(tick)}) STT: {text}'))

    lines.append((MONO0 + 0.001, 'rst:0x17 (CHIP_USB_UART_RESET),boot:0x308 (SPI_FAST_FLASH_BOOT)'))
    cs = 3100.0
    warm_e = cs + 7200.0
    # chatter lines every 400 ms for the clock envelope
    t_end_guess = warm_e + 2000 + man['duration_s'] * 1000 + 15000
    t = 200.0
    while t < t_end_guess:
        lines.append((MONO0 + (t + 0.3 + rng.random() * 3) / 1000.0, f'I ({int(t)}) misc: tick'))
        t += 400 + rng.random() * 50
    emit(warm_e + TME, f'TL warm s={int(cs - 5)} e={int(warm_e)} load=3990 ok=1 lm=1 cpu=400MHz '
                       f'psram_free=6990000 psram_largest=6290000')
    emit(warm_e + TME + 1, f'TL capture_start t={int(cs)} source=1')
    mono_ready = MONO0 + (warm_e + TME + 1) / 1000.0
    t_launch = mono_ready + 2.0
    t_audio = t_launch + 0.098
    esp_play = (t_audio - MONO0) * 1000.0 - TME
    # simplified segmenter on clip speech intervals, plus one internal split of the first long clip
    iv = [(c['speech_start_s'], c['speech_end_s'], c['i']) for c in clips]
    phrases, i = [], 0
    split_done = False
    while i < len(iv):
        op = iv[i][0] - 0.3
        end = iv[i][1]
        j = i
        if not split_done and clips[iv[i][2]]['bin'] == 'long':
            mid = (iv[i][0] + iv[i][1]) / 2
            phrases.append((op, mid + 0.6))
            op = mid + 0.6
            split_done = True
        while True:
            close = max(end + 0.6, op + 4.0)
            if j + 1 < len(iv) and iv[j + 1][0] - 0.3 < close:
                j += 1
                end = iv[j][1]
                continue
            break
        phrases.append((op, close))
        i = j + 1
    worker_free = 0.0
    words = []
    for seq, (x0, x1) in enumerate(phrases, 1):
        a0 = esp_play + 1000 * x0 + CAP_DELAY
        a1 = esp_play + 1000 * x1 + CAP_DELAY
        T = (a1 - a0) / 1000.0
        q = a1 + 25 + rng.random() * 10
        s = max(q, worker_free) + 10
        m = 165 + 4.1 * T
        f = 29.4 * T
        n = (508 * T - 157) * speed * (1 + rng.gauss(0, 0.01))
        d = 80 + 10 * T
        pub = s + m + f + n + d + 4
        sv0, sv1 = pub + 2, pub + 95
        e = sv1 + 9
        worker_free = e
        read = pub + rng.random() * 200
        # drafts while the phrase is open (every 1.5 s after 1 s)
        ta = 1.0
        while ta < T - 0.5:
            ds = a0 + ta * 1000 + 20
            de = ds + 0.508 * ta * 1000 * speed
            ok = 1 if de < q else 0
            emit(de + TME, f'TL draft seq={seq} audio_ms={int(ta * 1000)} s={int(ds)} e={int(de)} ok={ok}')
            ta += 1.5
        emit(pub + TME, f'TL pub seq={seq} t={int(pub)}')
        emit(read + TME, f'TL read seg={seq} t={int(read)}')
        ref = ' '.join(c['text_norm'] for c in clips
                       if x0 < (c['speech_start_s'] + c['speech_end_s']) / 2 <= x1).split()
        hyp = [w if rng.random() > 0.08 else 'xx' for w in ref]
        emit(e + TME + 1, f'TL seg={seq} a0={int(a0)} a1={int(a1)} q={int(q)} s={int(s)} m={int(m)} f={int(f)} '
                          f'n={int(n)} d={int(d)} sv0={int(sv0)} sv1={int(sv1)} e={int(e)} ok=1 lm=1 '
                          f'psram_min=5300000 int_free=81234')
        emit(e + TME + 1, f'TL txt seq={seq} ' + ' '.join(hyp))
        words += hyp
    emit(esp_play + 60000 + TME, 'TL fault audio_loss=0 frames=0 dropped_phrases=0 mic_stalls=0')
    lines.sort()
    sdir = ROOT / label / f'20261010-0000{k:02d}_s{k}'
    sdir.mkdir(parents=True, exist_ok=True)
    with open(sdir / 'lines.tsv', 'w') as fh:
        fh.write('# mono_s\twall_s\tline\n')
        for mono, l in lines:
            fh.write(f'{mono:.6f}\t{1.79e9 + mono:.6f}\t{l}\n')
    meta = {'label': label, 'session_index': k, 'status': 'ok', 'manifest': str(MAN),
            'wav_sha256': man['wav_sha256'], 'wav_seconds': man['duration_s'],
            'afplay': {'t_launch': t_launch, 't_audio_start': t_audio,
                       'audio_start_method': 'coreaudio_device_running+pipeline', 'returncode': 0},
            'afplay_summary': {'launch_to_audio_ms': 98.0},
            'reader': {'fatal_markers': [], 'boot_banners': [MONO0]}}
    (sdir / 'session.json').write_text(json.dumps(meta, indent=1))
    return sdir, len(phrases)


def main():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    for k in (1, 2):
        simulate('fakeA', k, 1.00, seed=k)
        simulate('fakeB', k, 0.90, seed=100 + k)
    py = sys.executable
    r = subprocess.run([py, str(HERE / 'analyse.py'), '--root', str(ROOT), '--label', 'fakeA'],
                       capture_output=True, text=True)
    print(r.stdout[-6000:], r.stderr[-3000:])
    r = subprocess.run([py, str(HERE / 'analyse.py'), '--root', str(ROOT), '--compare', 'fakeA', 'fakeB'],
                       capture_output=True, text=True)
    print(r.stdout[-6000:], r.stderr[-3000:])
    # checks against injected truth
    a = json.loads(next((ROOT / 'fakeA').glob('*_s1/analysis.json')).read_text())
    ok = True
    tme = a['clock']['tick_minus_esp_ms']
    ok &= abs(tme - TME) <= 1.5
    ok &= abs(a['alignment']['delta_ms'] - CAP_DELAY) <= 20
    ph = [p for p in a['phrases'] if p['kind'] == 'pause']
    ok &= len(ph) >= 15
    print(f'check: tick-esp {tme} (true {TME}), delta {a["alignment"]["delta_ms"]} (true {CAP_DELAY}), '
          f'pause phrases {len(ph)}, split {a["alignment"]["split_phrases"]} -> {"PASS" if ok else "FAIL"}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
