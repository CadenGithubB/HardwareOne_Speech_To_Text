"""p4_steps.py LOG 'expect1=>answer1' 'expect2=>answer2' ... : answer each expected screen in order, then show the next screen."""
import os
import serial, time, sys
s = serial.Serial(); s.port=os.environ['HW1_P4_PORT']; s.baudrate=115200; s.timeout=0.05; s.dtr=False; s.rts=False; s.open()
log = open(sys.argv[1], 'wb'); buf = ''; mark = 0; steps = [a.split('=>', 1) for a in sys.argv[2:]]; i = 0
t_end = time.time() + 120; quiet = time.time()
while time.time() < t_end:
    d = s.read(4096)
    if d: log.write(d); buf += d.decode('utf-8', 'replace'); quiet = time.time(); continue
    if time.time() - quiet < 1.0: continue
    new = buf[mark:]
    if i < len(steps) and steps[i][0].lower() in new.lower():
        mark = len(buf); s.write((steps[i][1] + '\r').encode()); print(f'-> [{steps[i][0]}] sent {steps[i][1]!r}'); i += 1; time.sleep(0.5); quiet = time.time()
    elif i == len(steps) and new.strip() and time.time() - quiet > 2.5:
        start = new.rfind('========================================\n', 0, max(0, len(new) - 50))
        print('NEXT SCREEN:\n' + new[max(0, new.rfind('====', 0, new.rfind('====') - 1) - 45):][-1400:]); break
s.close()
