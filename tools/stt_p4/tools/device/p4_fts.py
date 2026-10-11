import os
import serial, time, re, sys
SETUP_USER = os.environ['HW1_SETUP_USERNAME']
SETUP_PASS = os.environ['HW1_SETUP_PASSWORD']
if not SETUP_USER or not SETUP_PASS:
    raise ValueError('HW1_SETUP_USERNAME and HW1_SETUP_PASSWORD must be nonempty')
# Setup replies may echo credentials; logs contain answer labels only.
s = serial.Serial(); s.port=os.environ['HW1_P4_PORT']; s.baudrate=115200; s.timeout=0.05; s.dtr=False; s.rts=False; s.open()
log = open(sys.argv[1], 'wb'); pending = ''; started = False; t_end = time.time() + 180; done_at = None; answers = []
def send(x, why):
    time.sleep(0.5); s.write(x.encode() + b'\r\n'); answers.append(why); log.write((why + '\n').encode()); print(f'-> sent answer for: {why}')
while time.time() < t_end:
    d = s.read(4096)
    if not d:
        if done_at and time.time() > done_at: break
        continue
    pending += d.decode('utf-8', 'replace')
    lines = pending.split('\n'); pending = lines[-1]
    for raw in lines[:-1] + ([pending] if re.search(r'(?i)(enter|username|password)[^\n]*[:?]\s*$', pending) else []):
        line = raw.strip()
        if 'FIRST-TIME SETUP' in line or 'SETUP MODE' in line: started = True
        if not started or not line: continue
        low = line.lower()
        if re.search(r'enter 1 or 2|enter 1, 2', low) and 'mode' not in answers: send('1', 'mode')
        elif 'username' in low and ('enter' in low or low.endswith(':')) and 'user' not in answers: send(SETUP_USER, 'user')
        elif 'password' in low and ('confirm' in low or 'again' in low or 're-enter' in low) and 'confirm' not in answers and 'pass' in answers: send(SETUP_PASS, 'confirm')
        elif 'password' in low and ('enter' in low or low.endswith(':')) and 'pass' not in answers: send(SETUP_PASS, 'pass')
        elif re.search(r'\(y/n\)|\[y/n\]', low): print('   (y/n prompt — not answering automatically)')
        if re.search(r'setup complete|saved /system/users/users.json', low): done_at = time.time() + 8
    if pending and re.search(r'(?i)(enter|username|password)[^\n]*[:?]\s*$', pending): pending = ''
s.close(); log.close(); print('answers sent:', answers)
