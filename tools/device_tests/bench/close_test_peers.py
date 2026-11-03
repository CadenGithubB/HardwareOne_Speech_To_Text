"""Retry explicit transient peer-close replies; do not wait out a success-only regex."""
import re
import time


def close_peer(console,command,success_pattern,attempts=12,timeout=90,retry_delay=5,sleep=time.sleep):
    if command not in ('closering','closeg2') or attempts<1:raise ValueError('invalid peer close')
    for attempt in range(attempts):
        reply=console.command(command,r'(?:OK: (?:RING:|G2:)[^\r\n]*|Error:[^\r\n]*)',timeout).group(0)
        if re.search(success_pattern,reply):return attempt+1
        transient=reply.startswith('Error:') and any(s in reply.lower() for s in ('close deferred','retry closering','retry closeg2'))
        if not transient:raise RuntimeError('peer close rejected: '+command)
        if attempt+1<attempts:sleep(retry_delay)
    raise RuntimeError('peer close still deferred: '+command)
