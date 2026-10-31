"""Count system-log bytes by category without printing private message bodies."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def analyze(path):
    data=path.read_bytes()
    categories=Counter();category_bytes=Counter();commands=Counter();times=[]
    lines=data.splitlines(keepends=True)
    errors=Counter()
    for raw in lines:
        line=raw.decode('utf-8',errors='replace')
        match=re.match(r'\[(\d+)\]\s+\[([^]]+)\]',line)
        if match:
            times.append(int(match[1]));category=match[2]
            # Collapse user/transport labels so analysis does not expose account names.
            if re.match(r'(serial|web|ble|oled|g2)\s',category):category='command response capture'
        else:category='unclassified / continuation'
        categories[category]+=1;category_bytes[category]+=len(raw)
        match=re.search(r"(?:cmd=|queued )'([^']+)'",line)
        if match:
            command=match[1].split()
            if command:commands[command[0]]+=1
        if 'No more free space' in line:errors['filesystem_no_space']+=1
        if 'Save failed' in line or 'save FAILED' in line:errors['settings_save_failure_lines']+=1
        if 'short write' in line.lower():errors['short_write_lines']+=1
    span=(times[-1]-times[0])/1000 if len(times)>1 and times[-1]>=times[0] else None
    return {'file':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
            'lines':len(lines),'first_uptime_ms':times[0] if times else None,
            'last_uptime_ms':times[-1] if times else None,'uptime_span_seconds':span,
            'mean_bytes_per_logged_second':round(len(data)/span,2) if span else None,
            'categories':[{'name':name,'lines':categories[name],'bytes':size,
                           'percent_bytes':round(100*size/len(data),2)}
                          for name,size in category_bytes.most_common()],
            'command_roots':dict(commands.most_common()),'error_markers':dict(errors)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    text=json.dumps(analyze(args.log),indent=2)+'\n'
    if args.output:args.output.write_text(text)
    else:print(text,end='')
