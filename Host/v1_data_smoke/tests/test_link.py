import threading
import time
import unittest

from link import LinkSession, write_exact


class ScriptedPort:
    def __init__(self, steps) -> None:
        self.steps = list(steps)
        self.closed = False

    def write(self, data: bytes) -> int:
        if not self.steps:
            return len(data)
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    def close(self) -> None:
        self.closed = True


class RecordingFiles:
    def __init__(self) -> None:
        self.order: list[str] = []
        self.closed = False

    def close(self) -> None:
        self.order.append("files_close")
        self.closed = True


class WriteTest(unittest.TestCase):
    def test_full_write_is_complete(self) -> None:
        port = ScriptedPort([4, 2])
        outcome = write_exact(port.write, b"abcdef")
        self.assertTrue(outcome.complete)
        self.assertEqual(outcome.accepted, 6)
        self.assertIsNone(outcome.error)

    def test_short_write_is_not_a_full_frame(self) -> None:
        port = ScriptedPort([3, 0])
        outcome = write_exact(port.write, b"abcdefghij")
        self.assertFalse(outcome.complete)
        self.assertEqual(outcome.accepted, 3)
        self.assertIn("短写", outcome.error or "")

    def test_exception_keeps_only_accepted_bytes(self) -> None:
        port = ScriptedPort([2, OSError("reset")])
        outcome = write_exact(port.write, b"abcdef")
        self.assertFalse(outcome.complete)
        self.assertEqual(outcome.accepted, 2)
        self.assertIn("OSError", outcome.error or "")


class SessionTest(unittest.TestCase):
    def test_shutdown_closes_files_after_reader_exits(self) -> None:
        files = RecordingFiles()
        port = ScriptedPort([])
        session = LinkSession(port, files, parser=None, node_id=1)

        def reader(active: LinkSession) -> None:
            while not active.stop.is_set():
                time.sleep(0.01)
            files.order.append("thread_exit")

        session.start(reader)
        time.sleep(0.03)
        note = session.shutdown(join_s=1.0)
        self.assertIsNone(note)
        self.assertTrue(port.closed)
        self.assertEqual(files.order, ["thread_exit", "files_close"])
        assert session.worker is not None
        self.assertFalse(session.worker.is_alive())

    def test_close_error_is_reported(self) -> None:
        class BadPort:
            def close(self) -> None:
                raise OSError("busy")

        files = RecordingFiles()
        session = LinkSession(BadPort(), files, parser=None, node_id=2)
        note = session.shutdown()
        self.assertIn("关闭串口失败", note or "")
        self.assertTrue(files.closed)

    def test_reconnect_uses_a_new_inbox(self) -> None:
        old = LinkSession(ScriptedPort([]), RecordingFiles(), parser=None, node_id=1)
        old.push(("events", "old"))
        old.shutdown()
        new = LinkSession(ScriptedPort([]), RecordingFiles(), parser=None, node_id=2)
        new.push(("events", "new"))
        self.assertEqual(new.take(), [("events", "new")])
        self.assertEqual(old.take(), [("events", "old")])
        self.assertIsNot(old.stop, new.stop)

    def test_reader_keeps_its_own_session_objects(self) -> None:
        seen = {}

        def reader(active: LinkSession) -> None:
            seen["node"] = active.node_id
            seen["files"] = active.files
            while not active.stop.is_set():
                time.sleep(0.01)

        first_files = RecordingFiles()
        first = LinkSession(ScriptedPort([]), first_files, parser=object(), node_id=1)
        first.start(reader)
        time.sleep(0.03)
        self.assertEqual(seen["node"], 1)
        self.assertIs(seen["files"], first_files)
        first.shutdown()
        second = LinkSession(ScriptedPort([]), RecordingFiles(), parser=object(), node_id=2)
        self.assertEqual(second.node_id, 2)
        self.assertIsNot(second.files, first_files)
        self.assertFalse(first.worker.is_alive())


if __name__ == "__main__":
    unittest.main()
