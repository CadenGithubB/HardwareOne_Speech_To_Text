import codecs
import os
import serial, time, re, sys
SETUP_USER = os.environ['HW1_SETUP_USERNAME']
SETUP_PASS = os.environ['HW1_SETUP_PASSWORD']
if not SETUP_USER or not SETUP_PASS:
    raise ValueError('HW1_SETUP_USERNAME and HW1_SETUP_PASSWORD must be nonempty')
# Setup replies may echo credentials. Each settled burst is redacted before it reaches the
# log or the screen (whole tokens, password first, so a short name such as "a" does not
# erase every letter); answers appear only as labels.
SECRETS = [(re.compile(r'(?<!\w)' + re.escape(value) + r'(?!\w)'), label)
           for value, label in ((SETUP_PASS, '<redacted>'), (SETUP_USER, '<user>'))]
def redact(text):
    for pattern, label in SECRETS: text = pattern.sub(label, text)
    return text
s = serial.Serial(); s.port=os.environ['HW1_P4_PORT']; s.baudrate=115200; s.timeout=0.05; s.dtr=False; s.rts=False; s.open()
log = open(sys.argv[1], 'w', encoding='utf-8'); decode = codecs.getincrementaldecoder('utf-8')('replace').decode
buf = ''; mark = 0; sent = []; t_end = time.time() + 150; quiet_since = time.time()
def send(x, why):
    s.write((x + '\r').encode()); sent.append(why); log.write(f'\n-> sent {why}\n'); print(f'   -> sent {why}'); time.sleep(1.0)
while time.time() < t_end:
    d = s.read(4096)
    if d:
        buf += decode(d); quiet_since = time.time(); continue
    if time.time() - quiet_since < 0.8: continue   # act only once output settles
    new = buf[mark:]; mark = len(buf)
    if not new.strip(): continue
    log.write(redact(new))
    tail = [redact(l.strip()) for l in new.splitlines() if l.strip() and not l.strip().startswith(('I (', 'W (', 'E ('))][-8:]
    if 'FIRST-TIME' in buf or 'SETUP' in buf: print('P4 screen:', ' | '.join(tail)[:400])
    low = new.lower()
    if 'enter 1 or 2' in low and 'mode' not in sent: send('1', 'mode')
    elif 'username' in low and 'user' not in sent: send(SETUP_USER, 'user')
    elif 'password' in low and 'pass' in sent and 'confirm' not in sent and ('confirm' in low or 'again' in low): send(SETUP_PASS, 'confirm')
    elif 'password' in low and 'pass' not in sent: send(SETUP_PASS, 'pass')
    elif "'n' next" in low: send('n', 'next-page')
    if re.search(r'(?i)setup complete', buf) and 'pass' in sent: time.sleep(4); break
if buf[mark:]: log.write(redact(buf[mark:]))
s.close(); log.close(); print('sent:', sent)
