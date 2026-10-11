#!/usr/bin/env python3
"""Launch afplay and time when its audio actually starts (stdlib only).

play_timed(path) runs `afplay -d path` under a pty (so its debug lines arrive as
they are printed, not at exit) while a CoreAudio watcher polls the default
output device's IsRunningSomewhere flag. It returns monotonic timestamps:

  t_launch       just before the process is spawned
  t_dbg_file     afplay printed 'Playing file:'
  t_dbg_buffer   afplay printed 'Buffer Byte Size:' (its last line before it
                 starts the queue = "afplay reports start")
  t_dev_running  default output device started IO (0 -> 1), or None
  t_exit         process exited
  t_audio_start  best estimate of the first file sample at the DAC:
                 t_dev_running + output pipeline latency (device + safety
                 offset + buffer + stream latency, read from CoreAudio), else
                 t_dbg_buffer + calib['dbg_buffer_to_audio_ms'], else
                 t_launch + calib['launch_to_audio_ms'].

Run directly to calibrate:  python afplay_timing.py --trials 6 [--idle 20]
(plays a short silent 48 kHz file, so nothing is audible).
"""
import argparse
import json
import os
import pty
import select
import statistics
import subprocess
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coreaudio_probe as cap  # noqa: E402


def play_timed(path, calib=None, extra_args=(), on_line=None):
    calib = calib or {}
    watcher = cap.RunWatcher().start()
    info = cap.output_latency_info(watcher.dev)
    master, slave = pty.openpty()
    t_launch = time.monotonic()
    proc = subprocess.Popen(['afplay', '-d', *extra_args, str(path)], stdin=subprocess.DEVNULL,
                            stdout=slave, stderr=slave, close_fds=True)
    os.close(slave)
    t_spawned = time.monotonic()
    marks, pending = {}, b''
    while True:
        r, _, _ = select.select([master], [], [], 0.05)
        if r:
            try:
                data = os.read(master, 4096)
            except OSError:
                data = b''
            if not data:
                break
            now = time.monotonic()
            pending += data
            *lines, pending = pending.split(b'\n')
            for ln in lines:
                txt = ln.decode(errors='replace').strip()
                if txt.startswith('Playing file') and 't_dbg_file' not in marks:
                    marks['t_dbg_file'] = now
                elif txt.startswith('Buffer Byte Size') and 't_dbg_buffer' not in marks:
                    marks['t_dbg_buffer'] = now
                if on_line:
                    on_line(now, txt)
        elif proc.poll() is not None:
            break
    proc.wait()
    t_exit = time.monotonic()
    os.close(master)
    time.sleep(0.05)
    watcher.stop()
    t_run = watcher.first_start_after(t_launch) if not watcher.initial else None
    t_stop = watcher.first_stop_after(t_launch) if not watcher.initial else None
    res = {'t_launch': t_launch, 't_spawned': t_spawned, 't_dbg_file': marks.get('t_dbg_file'),
           't_dbg_buffer': marks.get('t_dbg_buffer'), 't_dev_running': t_run, 't_dev_stopped': t_stop,
           't_exit': t_exit, 'returncode': proc.returncode, 'device_initially_running': watcher.initial,
           'output_path': info}
    pipe_ms = info.get('pipeline_ms') or 0.0
    if t_run is not None:
        res['t_audio_start'] = t_run + pipe_ms / 1000.0
        res['audio_start_method'] = 'coreaudio_device_running+pipeline'
    elif res['t_dbg_buffer'] is not None and 'dbg_buffer_to_audio_ms' in calib:
        res['t_audio_start'] = res['t_dbg_buffer'] + calib['dbg_buffer_to_audio_ms'] / 1000.0
        res['audio_start_method'] = 'afplay_debug_line+calibration'
    elif 'launch_to_audio_ms' in calib:
        res['t_audio_start'] = t_launch + calib['launch_to_audio_ms'] / 1000.0
        res['audio_start_method'] = 'launch+calibration'
    else:
        res['t_audio_start'] = None
        res['audio_start_method'] = 'unknown'
    return res


def ms(a, b):
    return None if a is None or b is None else round((b - a) * 1000.0, 2)


def summarize(r):
    return {'launch_to_dbg_buffer_ms': ms(r['t_launch'], r['t_dbg_buffer']),
            'launch_to_dev_running_ms': ms(r['t_launch'], r['t_dev_running']),
            'dbg_buffer_to_dev_running_ms': ms(r['t_dbg_buffer'], r['t_dev_running']),
            'launch_to_audio_ms': ms(r['t_launch'], r['t_audio_start']),
            'dbg_buffer_to_audio_ms': ms(r['t_dbg_buffer'], r['t_audio_start']),
            'launch_to_exit_ms': ms(r['t_launch'], r['t_exit']),
            'method': r['audio_start_method']}


def write_silence(path, seconds=0.5, rate=48000):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b'\0\0' * int(seconds * rate))


def calibrate(trials=6, idle=0.0, out=None):
    tmp = HERE / 'calib_silence_48k.wav'
    if not tmp.exists():
        write_silence(tmp)
    rows = []
    for i in range(trials):
        if idle and i:
            time.sleep(idle)
        r = play_timed(tmp)
        s = summarize(r)
        s['trial'] = i
        s['idle_before_s'] = idle if i else None
        rows.append(s)
        print(json.dumps(s), flush=True)
        time.sleep(0.3)
    keys = ['launch_to_dbg_buffer_ms', 'launch_to_dev_running_ms', 'dbg_buffer_to_dev_running_ms',
            'launch_to_audio_ms', 'dbg_buffer_to_audio_ms', 'launch_to_exit_ms']
    summary = {}
    for k in keys:
        v = [x[k] for x in rows if x[k] is not None]
        if v:
            summary[k] = {'median': round(statistics.median(v), 2), 'min': min(v), 'max': max(v), 'n': len(v)}
    calib = {'measured_at_wall': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'trials': rows, 'summary': summary,
             'output_path': cap.output_latency_info(cap.default_output_device()),
             'volume_read_only': cap.read_output_volume()}
    if 'launch_to_audio_ms' in summary:
        calib['launch_to_audio_ms'] = summary['launch_to_audio_ms']['median']
    if 'dbg_buffer_to_audio_ms' in summary:
        calib['dbg_buffer_to_audio_ms'] = summary['dbg_buffer_to_audio_ms']['median']
    if out:
        Path(out).write_text(json.dumps(calib, indent=1))
    return calib


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--trials', type=int, default=6)
    ap.add_argument('--idle', type=float, default=0.0, help='seconds of output idle between trials')
    ap.add_argument('--out', default=str(HERE / 'afplay_calibration.json'))
    a = ap.parse_args()
    c = calibrate(a.trials, a.idle, a.out)
    print(json.dumps(c['summary'], indent=1))
