import re
import unittest
from upload_chunks import write_chunk


class Console:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.commands = []

    def command(self, command, pattern, timeout):
        self.commands.append(command)
        for line in next(self.replies):
            match = re.search(pattern, line)
            if match:
                return match
        raise RuntimeError('no matching acknowledgement')


class UploadChunksTest(unittest.TestCase):
    def test_stale_success_does_not_advance_current_chunk(self):
        c = Console([['{"success":true,"size":3}', '{"success":true,"size":6}']])
        self.assertEqual(write_chunk(c, '/sd/recordings/test.pcm', 3, b'def'), 6)

    def test_lost_reply_retries_identical_chunk_and_accepts_committed_offset(self):
        c = Console([[], ['{"success":false,"error":"Offset mismatch","size":6}']])
        self.assertEqual(write_chunk(c, '/sd/recordings/test.pcm', 3, b'def'), 6)
        self.assertEqual(c.commands[0], c.commands[1])

    def test_unexpected_preexisting_data_is_not_accepted_as_a_retry(self):
        c = Console([['{"success":false,"error":"Offset mismatch","size":6}']])
        with self.assertRaises(RuntimeError):
            write_chunk(c, '/sd/recordings/test.pcm', 3, b'def')

    def test_wrong_offset_never_advances(self):
        c = Console([['{"success":false,"error":"Offset mismatch","size":7}']])
        with self.assertRaises(RuntimeError):
            write_chunk(c, '/sd/recordings/test.pcm', 3, b'def', attempts=1)

    def test_write_failure_is_not_an_acknowledgement(self):
        c = Console([['{"success":false,"error":"Write failed","size":6}']])
        with self.assertRaises(RuntimeError):
            write_chunk(c, '/sd/recordings/test.pcm', 3, b'def')

    def test_limit_and_quoted_path_rejected_before_sending(self):
        c = Console([])
        for path, payload in [('/sd/recordings/test.pcm', b'x' * 1600), ('bad"path', b'a')]:
            with self.assertRaises(ValueError):
                write_chunk(c, path, 0, payload)
        self.assertEqual(c.commands, [])


if __name__ == '__main__':
    unittest.main()
