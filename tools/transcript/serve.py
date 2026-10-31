#!/usr/bin/env python3
"""Loopback-only standalone captions viewer; optional USB serial bridge.

python3 serve.py                        # import/replay viewer only
<IDF python> serve.py --port /dev/cu...  # real final captions + commands
No transcript/password is written by this bridge. Only one process may own USB.
"""
import argparse
import collections
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

WEB = Path(__file__).with_name('web')
class Events:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = collections.deque(maxlen=1024)
        self.cursor = 0
    def append(self, event):
        with self.lock:
            self.cursor += 1
            self.items.append({'cursor': self.cursor, 'event': event})
    def since(self, cursor):
        with self.lock:
            gap = bool(self.items and cursor and cursor < self.items[0]['cursor'] - 1)
            return {'cursor': self.cursor, 'gap': gap, 'events': [x for x in self.items if x['cursor'] > cursor]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='USB serial port; omitted for import/replay only')
    parser.add_argument('--http-port', type=int, default=8765)
    args = parser.parse_args()
    events = Events()
    device = None
    write_lock = threading.Lock()
    if args.port:
        import serial
        # Opening the port must not pulse the device's reset/boot pins.
        class NoControlSerial(serial.Serial):
            def _update_dtr_state(self): pass
            def _update_rts_state(self): pass
        device = NoControlSerial(args.port, 115200, timeout=.25, write_timeout=2, exclusive=True)
        import termios
        attributes = termios.tcgetattr(device.fileno())
        attributes[2] &= ~termios.HUPCL
        termios.tcsetattr(device.fileno(), termios.TCSANOW, attributes)
        def reader():
            buffer = bytearray()
            try:
                while True:
                    data = device.read(4096)
                    if not data: continue
                    buffer.extend(data)
                    while b'\n' in buffer:
                        line, _, rest = buffer.partition(b'\n'); buffer[:] = rest
                        marker = line.find(b'STT_EVENT ')
                        if marker >= 0:
                            try:
                                event = json.loads(line[marker + 10:])
                                if isinstance(event, dict) and event.get('schema') == 1: events.append(event)
                            except (ValueError, UnicodeError):
                                events.append({'schema': 1, 'type': 'message', 'ok': False, 'text': 'Invalid USB event; SD recording may still be intact'})
                    if len(buffer) > 65536:
                        buffer.clear()
                        events.append({'schema': 1, 'type': 'message', 'ok': False, 'text': 'Oversized USB line discarded'})
            except Exception as error:
                events.append({'schema': 1, 'type': 'message', 'ok': False, 'text': 'USB disconnected: ' + str(error)})
        threading.Thread(target=reader, daemon=True).start()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass  # keep transcript/query details out of logs
        def reply(self, code, body, content_type='application/json'):
            if not isinstance(body, bytes): body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{args.http_port}', f'localhost:{args.http_port}'}
        def do_GET(self):
            if not self.valid_host(): return self.reply(403, {'error': 'Use the loopback URL'})
            url = urlsplit(self.path)
            if url.path == '/api/events':
                try: cursor = max(0, int(parse_qs(url.query).get('after', ['0'])[0]))
                except ValueError: return self.reply(400, {'error': 'Invalid cursor'})
                return self.reply(200, {**events.since(cursor), 'usb': bool(device)})
            paths = {'/': 'index.html', '/app.js': 'app.js', '/model.mjs': 'model.mjs', '/style.css': 'style.css', '/replay.jsonl': 'replay.jsonl'}
            if url.path not in paths: return self.reply(404, {'error': 'Not found'})
            file = WEB / paths[url.path]
            content_type = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
            if file.suffix in {'.js', '.mjs'}: content_type = 'text/javascript'
            self.reply(200, file.read_bytes(), content_type)
        def do_POST(self):
            if not self.valid_host() or self.headers.get('Origin') not in {f'http://127.0.0.1:{args.http_port}', f'http://localhost:{args.http_port}'}:
                return self.reply(403, {'error': 'Local viewer origin required'})
            if self.path != '/api/command': return self.reply(404, {'error': 'Not found'})
            if not device: return self.reply(409, {'error': 'Viewer has no USB connection'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024: raise ValueError('Invalid command length')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict): raise ValueError('Expected a command object')
                cmd = body.get('command', '')
                if not isinstance(cmd, str) or not 0 < len(cmd) <= 240 or any(ord(c) < 32 or ord(c) > 126 for c in cmd): raise ValueError('Invalid command')
                if cmd not in {'help', 'status', 'notes', 'note start', 'note stop', 'vocab list', 'vocab reload'} and not cmd.startswith(('vocab add ', 'vocab remove ', 'note read ', 'clock set ')):
                    raise ValueError('Unsupported command')
                with write_lock: device.write((cmd + '\n').encode('ascii')); device.flush()
            except (ValueError, TypeError) as error: return self.reply(400, {'error': str(error)})
            except Exception: return self.reply(503, {'error': 'USB write failed'})
            self.reply(200, {'accepted': True})
    server = ThreadingHTTPServer(('127.0.0.1', args.http_port), Handler)
    print(f'Viewer: http://127.0.0.1:{args.http_port} (USB {"connected" if device else "not attached"})', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        if device: device.close()
if __name__ == '__main__': main()
