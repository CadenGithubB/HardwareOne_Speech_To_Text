"""Offset-checked chunks for the bench helper's sequential filewrite uploader.

A late success for an earlier chunk must never acknowledge the current one.
Retrying an already committed chunk returns Offset mismatch at the expected end;
that is a valid acknowledgement only for this same payload/offset retry.
"""
import base64
import json


def write_chunk(console, destination, offset, payload, timeout=60, attempts=3):
    if attempts < 1:
        raise ValueError('attempts must be positive')
    if not payload or offset < 0 or any(c in destination for c in '\r\n"\\'):
        raise ValueError('invalid filewrite chunk or destination')
    expected = offset + len(payload)
    command = f'filewrite "{destination}" {offset} {base64.b64encode(payload).decode()}'
    if len(command.encode()) > 2047:
        raise ValueError('filewrite command exceeds firmware CMD_INPUT_MAX')
    # Match the exact acknowledged size, not a delayed reply to a previous chunk.
    pattern = (r'\{(?=[^\r\n]*"size":' + str(expected) + r'[,}])'
               r'[^\r\n]*"success":(?:true|false)[^\r\n]*\}')
    for attempt in range(attempts):
        try:
            reply = json.loads(console.command(command, pattern, timeout).group(0))
        except RuntimeError:
            if attempt + 1 == attempts:
                raise
            continue
        if reply.get('size') != expected:
            raise RuntimeError('filewrite acknowledgement has an unexpected size')
        if reply.get('success') is True or (attempt > 0 and reply.get('error') == 'Offset mismatch'):
            return expected
        raise RuntimeError('filewrite rejected the chunk: ' + str(reply.get('error')))
    raise ValueError('attempts must be positive')
