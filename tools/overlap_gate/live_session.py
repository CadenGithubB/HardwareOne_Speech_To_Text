"""Run a live overlap session on the P4 with an on-screen cue page (http://127.0.0.1:8765).

1. Writes the night test app at 0x10000 with the restore's MAC/partition/hash checks, boots to Listening.
2. "overlap on", "pcm save on", "perf dump"; every serial line recorded with host wall/monotonic time.
3. Waits for Start on the cue page, then runs phase4/live1/schedule.json: per trial "get ready" (text
   shown), "go" (read aloud and/or the Mac plays the voice clip at the bench volume), "quiet". Pause
   and resume take effect between trials. Every phase boundary and playback start goes to events.jsonl.
4. Restores the production backup (same checks) and records its boot, also on error or Ctrl-C.
Run with the ESP-IDF python from the repository root.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import night_driver as nd  # noqa: E402

LIVE = nd.PHASE4 / 'live1'
TEST_APP = nd.ROOT / 'firmware/examples/p4_eye_captions/build/night/p4_eye_captions.bin'
TEST_APP_SHA = '2b7e282dc67d2459dd41c3131d588c1bd8fda2f88592733ed64b30925caf6dcf'

STATE = dict(phase='setup', message='Preparing the P4 (about a minute)...', trial=None, total=0, started=False, paused=False, done=False)
LOCK = threading.Lock()

PAGE = """<!doctype html><html><head><meta charset=utf-8><title>Live overlap session</title>
<style>
body{font-family:-apple-system,system-ui,sans-serif;margin:0;padding:32px;background:#fcfcfb;color:#0b0b0b}
@media(prefers-color-scheme:dark){body{background:#1a1a19;color:#f0efec}.card{background:#262624!important}}
.phase{font-size:20px;letter-spacing:.02em;margin-bottom:12px;color:#898781}
.big{font-size:44px;font-weight:500;margin-bottom:20px}
.card{background:#f1efe8;border-radius:12px;padding:24px 28px;font-size:30px;line-height:1.5;margin:14px 0}
.who{font-size:16px;color:#898781;margin-bottom:6px}
.go{color:#0ca30c}.quiet{color:#898781}.ready{color:#c98500}
button{font-size:20px;padding:10px 22px;border-radius:8px;border:1px solid #b4b2a9;background:none;color:inherit;margin-right:10px;cursor:pointer}
.bar{height:8px;background:#e1e0d9;border-radius:4px;margin-top:24px}.fill{height:8px;background:#2a78d6;border-radius:4px}
</style></head><body>
<div class=phase id=phase></div><div class=big id=big></div><div id=cards></div>
<div id=controls></div><div class=bar><div class=fill id=fill style="width:0"></div></div>
<script>
async function post(p){await fetch(p,{method:'POST'})}
async function tick(){
 const s=await (await fetch('/state')).json();
 const t=s.trial, ph=document.getElementById('phase'), big=document.getElementById('big'), cards=document.getElementById('cards'), c=document.getElementById('controls');
 ph.textContent = t ? `Trial ${t.index+1} of ${s.total}` + (s.paused?' (pausing after this trial)':'') : '';
 let html='';
 if(t && (s.phase==='ready'||s.phase==='go')){
   if(t.prompt_a) html+=`<div class=card><div class=who>${t.prompt_b?'Person A':'You'} read:</div>${t.prompt_a}</div>`;
   if(t.prompt_b) html+=`<div class=card><div class=who>Person B read:</div>${t.prompt_b}</div>`;
 }
 const say={setup:['',s.message],waiting:['',s.message],ready:['ready','Get ready'],go:['go', t&&(t.prompt_a||t.prompt_b)?(t.voice?'Read now, over the voice':'Read now'):'Stay quiet and listen'],quiet:['quiet','Quiet'],paused:['quiet','Paused'],done:['',s.message]}[s.phase]||['',s.phase];
 big.className='big '+say[0]; big.textContent=say[1]; cards.innerHTML=html;
 c.innerHTML = s.phase==='waiting' ? '<button onclick="post(\\'/start\\')">Start</button>' :
   (s.started && !s.done ? (s.paused?'<button onclick="post(\\'/resume\\')">Resume</button>':'<button onclick="post(\\'/pause\\')">Pause</button>') : '');
 document.getElementById('fill').style.width = (t? (100*(t.index+(s.phase==='quiet'?1:0))/s.total):0)+'%';
}
setInterval(tick,200); tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/state':
            with LOCK:
                self._send(json.dumps(STATE).encode(), 'application/json')
        else:
            self._send(PAGE.encode(), 'text/html; charset=utf-8')

    def do_POST(self):
        with LOCK:
            if self.path == '/start' and STATE['phase'] == 'waiting':
                STATE['started'] = True
            elif self.path == '/pause':
                STATE['paused'] = True
            elif self.path == '/resume':
                STATE['paused'] = False
        self._send(b'{}', 'application/json')


def set_state(**kw):
    with LOCK:
        STATE.update(kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, default=nd.PHASE4 / 'live1-runs')
    ap.add_argument('--volume', type=int, default=nd.VOLUME)
    ap.add_argument('--port', type=int, default=8765)
    args = ap.parse_args()
    sched = json.loads((LIVE / 'schedule.json').read_text())
    trials = sched['trials']
    set_state(total=len(trials))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if nd.HEAPTW_LOCK.exists():
        sys.exit(f'{nd.HEAPTW_LOCK} exists: another bench chain owns the board')
    nd.HEAPTW_LOCK.write_text(f'overlap-gate live session pid {os.getpid()} since {nd.now()}\n')
    night = nd.Night(args.out)
    con = None
    try:
        night.event(kind='live-start', mode=sched['mode'], trials=len(trials), volume=args.volume)
        if not nd.restore(night, image=TEST_APP, want=TEST_APP_SHA, boot_pattern=r'Listening \(noise floor', label='flash-test-app'):
            set_state(phase='done', message='Could not prepare the P4. Production firmware is being restored.', done=True)
            return
        ok, tail = nd.reset_board()
        con = nd.Console(args.out / 'serial.log')
        line, pos = con.wait_for(r'Listening \(noise floor', 180)
        night.event(kind='listening', ok=ok, line=line)
        if not line:
            set_state(phase='done', message='The P4 did not start listening. Production firmware is being restored.', done=True)
            return
        con.send('overlap on')
        ack, pos = con.wait_for(r'Overlap gate (on|off)', 10, pos)
        con.send('pcm save on')
        pcm_ack, pos = con.wait_for(r'PCM save', 10, pos)
        con.send('perf dump')
        night.event(kind='armed', ack=ack, pcm_ack=pcm_ack)
        subprocess.run(['osascript', '-e', f'set volume output volume {args.volume} without output muted'], check=False)
        set_state(phase='waiting', message=f'Ready: {len(trials)} trials, about {sched["minutes"]:.0f} minutes. Sit where you normally would and press Start.')
        while not STATE['started']:
            time.sleep(0.2)
        mark = len(con.lines)
        night.event(kind='trials-start', wall=round(time.time(), 3))
        for t in trials:
            while STATE['paused']:
                set_state(phase='paused', trial=t)
                time.sleep(0.2)
            set_state(phase='ready', trial=t)
            r0 = time.monotonic()
            time.sleep(sched['ready_s'])
            set_state(phase='go')
            g0w, g0m = time.time(), time.monotonic()
            play = subprocess.Popen(['afplay', t['voice']['wav']]) if 'voice' in t else None
            time.sleep(sched['go_s'])
            rc = play.wait() if play else None
            g1m = time.monotonic()
            set_state(phase='quiet')
            time.sleep(sched['quiet_s'])
            night.event(kind='trial', index=t['index'], trial_kind=t['kind'], ready_mono=round(r0, 3), go_wall=round(g0w, 3), go_mono=round(g0m, 3),
                        go_end_mono=round(g1m, 3), voice=t.get('voice', {}).get('wav'), afplay_rc=rc, label_overlap=t['label_overlap'])
        time.sleep(10)
        con.send('perf dump')
        time.sleep(5)
        counts = dict(finals=con.count(r'"type":"final"', mark), pcm_saved=con.count(r'^STT_PCM .*"ok":true', mark),
                      pcm_failed=con.count(r'^STT_PCM .*"ok":false', mark), overlap_lines=con.count(r'^STT_OVERLAP ', mark),
                      failures=con.count(nd.FAIL, mark))
        night.event(kind='trials-done', counts=counts)
        set_state(phase='done', message='All done, thank you. Restoring production firmware (about a minute).', done=True)
    finally:
        if con:
            con.close()
        try:
            restored = nd.restore(night)
            set_state(phase='done', done=True, message='Finished. Production firmware restored.' if restored else 'Finished, but the production restore needs checking.')
        finally:
            nd.HEAPTW_LOCK.unlink(missing_ok=True)
            time.sleep(3)
            server.shutdown()


if __name__ == '__main__':
    main()
