#!/usr/bin/env python3
"""Passive stop collector for the explicitly labelled trace-only diagnostic app.

Do not use for normal speech qualification: pending captions are not drained
while teardown is running. On any failure the token is invalidated; the caller
must reset/recover the board rather than retry a possibly stale stop.
"""
import json
import re
import time
import teardowndiag

class TeardownEvidenceError(RuntimeError):
    pass

DONE=re.compile(r'TL teardown phase=321 event=2 ms=\d+ end(?:\s|$)')

def stop_after_teardown(device,timeout=90):
    if not device.token:return None
    token=device.token
    with device.rd.lock:start=len(device.rd.history)
    try:
        device.command(f'stt stop {token}',r'STT request accepted',20)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            device.check_health()
            with device.rd.lock:lines=list(device.rd.history[start:])
            if any(DONE.search(line) for line in lines):
                marker_error=None
                try:
                    summary=teardowndiag.summarize(lines)
                    if len(summary['cycles'])!=1 or summary['complete_cycles']!=1 or summary['cycles'][0]['mode']!='trace':
                        raise ValueError('trace-only teardown markers incomplete')
                    device.teardown_summary=summary
                except ValueError as error:
                    marker_error=str(error)
                # No CLI status/next/ack during the marker stream. Phase 321
                # is after terminal state publication, before worker self-delete.
                state=json.loads(device.command(f'stt status {token}',r'\{[^\r\n]*"state":[^\r\n]*\}').group(0))
                if state.get('state')!='done' or state.get('audioOverruns',0) or state.get('error'):
                    raise RuntimeError('STT terminal fault/overrun')
                device.token=None
                device.terminal_state=state
                if marker_error:raise TeardownEvidenceError(marker_error)
                return state
            time.sleep(.05)
        raise RuntimeError('passive teardown markers timed out')
    except BaseException:
        device.token=None
        raise
