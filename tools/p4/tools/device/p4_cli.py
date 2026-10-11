"""Log into the P4 serial CLI and run commands.

p4_cli.py LOG "cmd1" "wait:SECONDS" "cmd2" ...   (P4_USER / P4_PASS from env)
Each command's reply (the device's log lines included) is printed; the
password is never printed and is blanked in the saved log.
"""
import os, re, sys, time
import serial

USER, PASS = os.environ['P4_USER'], os.environ['P4_PASS']
LOG = sys.argv[1]
s = serial.Serial()
s.port, s.baudrate, s.timeout, s.dtr, s.rts = os.environ['HW1_P4_PORT'], 115200, 0.05, False, False
s.open()  # resets the P4
buf = bytearray()


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        data = s.read(4096)
        if data:
            buf.extend(data)


def cmd(line, wait=3.0):
    start = len(buf)
    s.write((line + '\r\n').encode())
    pump(wait)
    out = bytes(buf[start:]).decode('utf-8', 'replace')
    return out.replace(PASS, '********') if len(PASS) >= 4 else out


try:
    end = time.time() + 40
    while time.time() < end and b'Setup complete' not in buf:
        pump(0.5)
    pump(4)
    cmd(f'login {USER} {PASS}', 3)
    assert 'You are' in cmd('whoami', 2), 'login failed'
    print('== logged in')
    for arg in sys.argv[2:]:
        if arg.startswith('wait:'):
            start = len(buf); pump(float(arg[5:]))
            print(f'== waited {arg[5:]}s; log during wait:')
            print(bytes(buf[start:]).decode('utf-8', 'replace')[-3000:])
            continue
        print(f'== {arg}')
        print(cmd(arg, 4)[-3000:])
    cmd('logout', 1)
finally:
    s.close()
    open(LOG, 'wb').write(bytes(buf).replace(PASS.encode(), b'********') if len(PASS) >= 4 else bytes(buf))
