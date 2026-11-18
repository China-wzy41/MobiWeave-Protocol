import os
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path

from link import write_exact
from reliable import (
    LIMITS,
    BootStore,
    ExperimentLimits,
    IdentityError,
    NodeEngine,
    age_at,
)
from v1frame import (
    DOC_ACK_FRAME,
    STATUS_ACCEPTED,
    STATUS_BUSY,
    STATUS_EXPIRED,
    AckFields,
    DataFields,
    StreamParser,
    encode_ack,
    encode_data,
)


FAST = ExperimentLimits(
    ack_timeout_ms=100,
    max_retries=2,
    retry_backoff_ms=50,
    busy_backoff_ms=80,
    cache_limit=4,
    lifetime_ms=1000,
    hop_limit=1,
)


class ScriptPort:
    def __init__(self, steps=None) -> None:
        self.steps = list(steps or [])
        self.written = b""

    def write(self, data: bytes) -> int:
        if not self.steps:
            self.written += data
            return len(data)
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        count = min(int(step), len(data))
        self.written += data[:count]
        return count


def one_event(frame: bytes):
    events = StreamParser().feed(frame, 0.0)
    if len(events) != 1:
        raise AssertionError(events)
    return events[0]


def direct(seq: int, text: str, *, boot: int = 1, age: int = 0, sender: int = 1, receiver: int = 2) -> bytes:
    return encode_data(
        DataFields(
            sender_id=sender,
            receiver_id=receiver,
            source_id=sender,
            destination_id=receiver,
            boot_counter=boot,
            sequence=seq,
            priority=0,
            age_ms=age,
            lifetime_ms=FAST.lifetime_ms,
            hop_count=1,
            hop_limit=1,
            payload_type=1,
            payload=text.encode("utf-8"),
        )
    )


def push(engine: NodeEngine, frame: bytes, now: int):
    return engine.on_event(one_event(frame), now)


class Pair:
    def __init__(self, limits: ExperimentLimits = FAST) -> None:
        self.a = NodeEngine(1, 2, 1, limits)
        self.b = NodeEngine(2, 1, 1, limits)
        self.port = ScriptPort()

    def send_reliable(self, text: str, now: int):
        request = self.a.submit_text(text, now)
        if request is None:
            raise AssertionError("not armed")
        outcome = write_exact(self.port.write, request.frame)
        lines = self.a.note_write(
            request, outcome.accepted, outcome.complete, outcome.error, now
        )
        return request, outcome, lines


class ReliableTest(unittest.TestCase):
    def test_document_ack_vector(self) -> None:
        fields = AckFields(2, 1, 1, 7, 12, STATUS_ACCEPTED)
        self.assertEqual(encode_ack(fields), DOC_ACK_FRAME)
        event = one_event(DOC_ACK_FRAME)
        self.assertEqual(event.kind, "ack")
        self.assertEqual(event.crc, 0x82F0)
        assert event.ack is not None
        self.assertEqual(event.ack.sequence, 12)

    def test_success_is_this_hop_only(self) -> None:
        pair = Pair()
        request, outcome, _lines = pair.send_reliable("hello", 0)
        self.assertTrue(outcome.complete)
        received = push(pair.b, request.frame, 10)
        self.assertIsNotNone(received.ack)
        self.assertIn("当地应用交付", received.lines[0])
        self.assertIn("不是端到端确认", received.lines[0])
        ack_event = one_event(received.ack or b"")
        assert ack_event.ack is not None
        self.assertEqual(ack_event.ack.status, STATUS_ACCEPTED)
        self.assertEqual(ack_event.ack.sender_id, 2)
        self.assertEqual(ack_event.ack.receiver_id, 1)
        done = pair.a.on_event(ack_event, 25)
        self.assertIn("本跳缓存确认", done.lines[0])
        self.assertIn("端到端未知", done.lines[0])
        self.assertEqual(pair.a.rtt_ms, [((1, 1, 1), 25)])
        self.assertEqual(pair.a.poll(25), [])
        self.assertIsNone(pair.b.on_event(ack_event, 25).ack)

    def test_lost_data_retries_same_id_and_hop_with_older_age(self) -> None:
        pair = Pair()
        first, _, _ = pair.send_reliable("hello", 0)
        first_fields = one_event(first.frame).fields
        assert first_fields is not None
        self.assertEqual(pair.a.poll(100), [])
        self.assertIn("重传原编号", "".join(pair.a.take_lines()))
        retry = pair.a.poll(150)
        self.assertEqual(len(retry), 1)
        outcome = write_exact(ScriptPort().write, retry[0].frame)
        pair.a.note_write(retry[0], outcome.accepted, outcome.complete, outcome.error, 150)
        again = one_event(retry[0].frame).fields
        assert again is not None
        self.assertEqual(again.sequence, first_fields.sequence)
        self.assertEqual(again.boot_counter, first_fields.boot_counter)
        self.assertEqual(again.hop_count, 1)
        self.assertEqual(first_fields.hop_count, 1)
        self.assertGreater(again.age_ms, first_fields.age_ms)
        self.assertEqual(again.age_ms, 150)

    def test_lost_ack_then_duplicate_is_not_delivered_twice(self) -> None:
        pair = Pair()
        request, _, _ = pair.send_reliable("kskbl", 0)
        first = push(pair.b, request.frame, 5)
        self.assertIn("当地应用交付", first.lines[0])
        pair.a.poll(100)
        retry = pair.a.poll(160)[0]
        write_exact(ScriptPort().write, retry.frame)
        pair.a.note_write(retry, len(retry.frame), True, None, 160)
        second = push(pair.b, retry.frame, 170)
        self.assertIn("ALREADY_HAVE", second.lines[0])
        self.assertEqual(len(pair.b.accepted_ids), 1)
        self.assertEqual(pair.b.duplicates, 1)
        done = pair.a.on_event(one_event(second.ack or b""), 180)
        self.assertIn("ALREADY_HAVE", done.lines[0])
        self.assertIn("端到端未知", done.lines[0])
        self.assertEqual(pair.a.outbound[0].state, "hop_cached")

    def test_reorder_delivers_each_id_once(self) -> None:
        engine = NodeEngine(2, 1, 1, FAST)
        later = push(engine, direct(2, "second"), 0)
        earlier = push(engine, direct(1, "first"), 1)
        self.assertIn("second", later.lines[0])
        self.assertIn("first", earlier.lines[0])
        self.assertEqual([item[2] for item in engine.accepted_ids], [2, 1])
        again = push(engine, direct(2, "second"), 2)
        self.assertIsNotNone(again.ack)
        self.assertEqual(len(engine.accepted_ids), 2)

    def test_delayed_ack_before_timeout_cancels_retry(self) -> None:
        pair = Pair()
        request, _, _ = pair.send_reliable("hi", 0)
        received = push(pair.b, request.frame, 5)
        self.assertEqual(pair.a.poll(40), [])
        done = pair.a.on_event(one_event(received.ack or b""), 40)
        self.assertIn("本跳缓存确认", done.lines[0])
        self.assertEqual(pair.a.poll(500), [])

    def test_bad_crc_and_bad_length_do_not_ack(self) -> None:
        engine = NodeEngine(2, 1, 1, FAST)
        bad = direct(2, "nope")
        bad = bad[:-2] + struct.pack("<H", struct.unpack("<H", bad[-2:])[0] ^ 0x00FF)
        result = push(engine, bad, 0)
        self.assertIsNone(result.ack)
        self.assertEqual(engine.bad_crc, 1)
        self.assertEqual(engine.accepted_ids, [])
        body = b"\x00" * 14
        covered = struct.pack("<BBH", 1, 2, 14) + body
        from v1frame import MAGIC, crc16_ibm3740
        frame = MAGIC + covered + struct.pack("<H", crc16_ibm3740(covered))
        length = engine.on_event(one_event(frame), 0)
        self.assertIsNone(length.ack)
        self.assertEqual(engine.bad_length, 1)

    def test_wrong_ack_does_not_succeed(self) -> None:
        pair = Pair()
        request, _, _ = pair.send_reliable("hi", 0)
        fields = one_event(request.frame).fields
        assert fields is not None
        wrong_status = encode_ack(
            AckFields(2, 1, fields.source_id, fields.boot_counter, fields.sequence, 9)
        )
        lines = pair.a.on_event(one_event(wrong_status), 10).lines
        self.assertIn("未知", lines[0])
        self.assertEqual(pair.a.outbound[0].state, "waiting")
        wrong_peer = encode_ack(
            AckFields(9, 1, fields.source_id, fields.boot_counter, fields.sequence, STATUS_ACCEPTED)
        )
        peer_lines = pair.a.on_event(one_event(wrong_peer), 11).lines
        self.assertIn("不是预期对端", peer_lines[0])
        self.assertEqual(pair.a.outbound[0].state, "waiting")
        wrong_seq = encode_ack(
            AckFields(2, 1, fields.source_id, fields.boot_counter, 99, STATUS_ACCEPTED)
        )
        seq_lines = pair.a.on_event(one_event(wrong_seq), 12).lines
        self.assertIn("没有匹配", seq_lines[0])
        self.assertEqual(pair.a.outbound[0].state, "waiting")

    def test_content_conflict_is_not_a_success_ack(self) -> None:
        engine = NodeEngine(2, 1, 1, FAST)
        first = push(engine, direct(1, "hello"), 0)
        self.assertIn("当地应用交付", first.lines[0])
        conflict = encode_data(
            DataFields(
                sender_id=1, receiver_id=2, source_id=1, destination_id=2,
                boot_counter=1, sequence=1, priority=0, age_ms=0,
                lifetime_ms=FAST.lifetime_ms, hop_count=1, hop_limit=1,
                payload_type=1, payload=b"other",
            )
        )
        second = push(engine, conflict, 1)
        self.assertIsNone(second.ack)
        self.assertIn("编号冲突", second.lines[0])
        self.assertEqual(engine.held[(1, 1, 1)].payload, b"hello")
        self.assertEqual(len(engine.accepted_ids), 1)

    def test_cache_full_is_busy_and_expired_is_distinct(self) -> None:
        limits = ExperimentLimits(
            ack_timeout_ms=100, max_retries=1, retry_backoff_ms=10,
            busy_backoff_ms=10, cache_limit=1, lifetime_ms=1000, hop_limit=1,
        )
        engine = NodeEngine(2, 1, 1, limits)
        first = push(engine, direct(1, "one"), 0)
        self.assertIn("当地应用交付", first.lines[0])
        busy = push(engine, direct(2, "two"), 1)
        busy_ack = one_event(busy.ack or b"").ack
        assert busy_ack is not None
        self.assertEqual(busy_ack.status, STATUS_BUSY)
        self.assertEqual(len(engine.held), 1)
        expired = push(engine, direct(3, "old", age=1000), 2)
        expired_ack = one_event(expired.ack or b"").ack
        assert expired_ack is not None
        self.assertEqual(expired_ack.status, STATUS_EXPIRED)
        self.assertNotIn((1, 1, 3), engine.held)

    def test_restart_boot_is_unique_and_failed_store_sends_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            store = BootStore(directory)
            first = store.open_boot()
            second = BootStore(directory).open_boot()
            self.assertEqual((first, second), (1, 2))
            left = NodeEngine(1, 2, first, FAST)
            right = NodeEngine(1, 2, second, FAST)
            left_id = one_event(left.submit_smoke("a", 0).frame).fields
            right_id = one_event(right.submit_smoke("a", 0).frame).fields
            assert left_id is not None and right_id is not None
            self.assertEqual(left_id.sequence, right_id.sequence)
            self.assertNotEqual(left_id.boot_counter, right_id.boot_counter)
            issued: list[int] = []
            original = os.replace

            def fail(*_args, **_kwargs):
                raise OSError("full")

            os.replace = fail
            try:
                issued.append(store.open_boot())
            except IdentityError:
                pass
            finally:
                os.replace = original
            self.assertEqual(issued, [])
            self.assertEqual(store._read(), 2)
            self.assertFalse(store.lock_path.exists())
            store.file.unlink()
            with self.assertRaises(IdentityError):
                store.open_boot()
            store.file.write_text("01\n", encoding="ascii")
            with self.assertRaises(IdentityError):
                BootStore(directory).open_boot()

    def test_short_write_and_exception_are_not_success(self) -> None:
        engine = NodeEngine(1, 2, 1, FAST)
        request = engine.submit_text("hello", 0)
        assert request is not None
        short = ScriptPort([3, 0])
        outcome = write_exact(short.write, request.frame)
        lines = engine.note_write(request, outcome.accepted, outcome.complete, outcome.error, 0)
        self.assertFalse(outcome.complete)
        self.assertEqual(outcome.accepted, 3)
        self.assertIn("complete=no", lines[0])
        self.assertNotEqual(engine.outbound[0].state, "hop_cached")
        request2 = engine.poll(FAST.retry_backoff_ms)[0]
        broken = ScriptPort([2, OSError("reset")])
        failed = write_exact(broken.write, request2.frame)
        failed_lines = engine.note_write(
            request2, failed.accepted, failed.complete, failed.error, FAST.retry_backoff_ms
        )
        self.assertIn("OSError", failed_lines[0])
        self.assertNotEqual(engine.outbound[0].state, "hop_cached")

    def test_cancel_stops_retries_and_late_ack(self) -> None:
        pair = Pair()
        request, _, _ = pair.send_reliable("hello", 0)
        pair.a.cancel()
        self.assertEqual(pair.a.poll(10_000), [])
        received = push(pair.b, request.frame, 5)
        late = pair.a.on_event(one_event(received.ack or b""), 6)
        self.assertIn("不作为成功", late.lines[0])
        self.assertEqual(pair.a.outbound[0].state, "cancelled")
        pair.a.resume()
        self.assertEqual(pair.a.poll(10_000), [])

    def test_relay_sample_is_not_accepted_by_this_direct_tool(self) -> None:
        from v1frame import DOC_SOS_FRAME
        engine = NodeEngine(2, 1, 1, FAST)
        result = push(engine, DOC_SOS_FRAME, 0)
        self.assertIsNone(result.ack)
        self.assertIn("不转发", result.lines[0])
        self.assertEqual(engine.accepted_ids, [])

    def test_holes_do_not_cross_boots_or_count_bad_crc_as_loss(self) -> None:
        engine = NodeEngine(2, 1, 1, FAST)
        push(engine, direct(1, "a", boot=1), 0)
        push(engine, bad_crc(direct(2, "bad", boot=1)), 1)
        push(engine, direct(3, "c", boot=1), 2)
        push(engine, direct(1, "next", boot=2), 3)
        spans, omitted = engine.hole_spans()
        self.assertEqual(omitted, 0)
        self.assertEqual([(item.start, item.end, item.count) for item in spans], [(2, 2, 1)])
        self.assertEqual(spans[0].source, 1)
        self.assertEqual(spans[0].boot, 1)
        self.assertEqual(engine.bad_crc, 1)
        self.assertNotIn("丢包率", engine.summary())
        self.assertIn("不是无线丢包", engine.summary())

    def test_age_does_not_wrap(self) -> None:
        self.assertEqual(age_at(0xFFFFFFFF, 0, 5), 0xFFFFFFFF)

    def test_full_queue_does_not_allocate_a_sequence(self) -> None:
        limits = ExperimentLimits(
            ack_timeout_ms=100, max_retries=0, retry_backoff_ms=10,
            busy_backoff_ms=10, cache_limit=1, lifetime_ms=1000, hop_limit=1,
        )
        engine = NodeEngine(1, 2, 1, limits)
        self.assertIsNotNone(engine.submit_text("a", 0))
        sequence = engine.sequence
        with self.assertRaises(ValueError):
            engine.submit_text("b", 0)
        self.assertEqual(engine.sequence, sequence)

    def test_experiment_defaults_are_explicit(self) -> None:
        self.assertEqual(LIMITS.ack_timeout_ms, 3000)
        self.assertEqual(LIMITS.max_retries, 2)
        self.assertEqual(LIMITS.retry_backoff_ms, 1000)
        self.assertEqual(LIMITS.busy_backoff_ms, 2000)
        self.assertEqual(LIMITS.cache_limit, 16)
        self.assertEqual(LIMITS.lifetime_ms, 60000)
        self.assertEqual(LIMITS.hop_limit, 1)

    def test_large_hole_summary_stays_bounded(self) -> None:
        engine = NodeEngine(2, 1, 1, FAST)
        engine.accepted_ids = [(1, 1, 5), (1, 1, 1), (1, 1, 3)]
        spans, omitted = engine.hole_spans()
        self.assertEqual(omitted, 0)
        self.assertEqual(
            [(item.start, item.end, item.count) for item in spans],
            [(2, 2, 1), (4, 4, 1)],
        )
        engine.accepted_ids = [(1, 1, 1), (1, 1, 0xFFFFFFFF)]
        started = time.perf_counter()
        text = engine.summary()
        self.assertLess(time.perf_counter() - started, 0.05)
        self.assertLess(len(text), 400)
        self.assertIn("缺2..4294967294共4294967293", text)
        self.assertNotIn("缺2,3,4", text)
        engine.accepted_ids = [(1, 1, seq) for seq in range(1, 40, 2)]
        shown, hidden = engine.hole_spans()
        self.assertEqual(len(shown), 8)
        self.assertGreater(hidden, 0)
        self.assertLess(len(engine.summary()), 500)
        limits = ExperimentLimits(
            ack_timeout_ms=10, max_retries=0, retry_backoff_ms=1,
            busy_backoff_ms=1, cache_limit=2, lifetime_ms=1000, hop_limit=1,
        )
        trimmed = NodeEngine(2, 1, 1, limits)
        trimmed.accepted_ids = [(1, 1, 1), (1, 1, 100)] + [(1, 1, seq) for seq in range(200, 220)]
        trimmed._trim_history()
        self.assertEqual(len(trimmed.accepted_ids), 8)
        self.assertNotIn((1, 1, 1), trimmed.accepted_ids)
        self.assertNotIn("缺2..", trimmed.summary())

    def test_boot_lock_conflict_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            store = BootStore(directory)
            self.assertEqual(store.open_boot(), 1)
            self.assertFalse(any(
                path.name == "boot.tmp" or path.name.endswith(".tmp") for path in directory.iterdir()
            ))
            held = os.open(store.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            try:
                with self.assertRaises(IdentityError):
                    store.open_boot()
                self.assertEqual(store._read(), 1)
            finally:
                os.close(held)
                os.unlink(store.lock_path)
            holder = BootStore(directory)
            entered = threading.Event()
            release = threading.Event()

            def pause() -> None:
                entered.set()
                self.assertTrue(release.wait(2))

            holder._after_acquire = pause
            outcome: dict[str, int] = {}

            def run() -> None:
                outcome["boot"] = holder.open_boot()

            worker = threading.Thread(target=run)
            worker.start()
            self.assertTrue(entered.wait(2))
            with self.assertRaises(IdentityError):
                BootStore(directory).open_boot()
            self.assertEqual(store._read(), 1)
            release.set()
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(outcome["boot"], 2)
            self.assertFalse(holder.lock_path.exists())

    def test_history_stays_bounded_for_active_done_and_cancel(self) -> None:
        limits = ExperimentLimits(
            ack_timeout_ms=10, max_retries=0, retry_backoff_ms=1,
            busy_backoff_ms=1, cache_limit=16, lifetime_ms=100000, hop_limit=1,
        )
        engine = NodeEngine(1, 2, 1, limits)
        for index in range(5):
            request = engine.submit_text(f"f{index}", index * 100)
            assert request is not None
            engine.note_write(request, len(request.frame), True, None, index * 100)
            engine.poll(index * 100 + 10)
        self.assertGreater(sum(item.state == "failed" for item in engine.outbound), 0)
        for index in range(16):
            engine.submit_text(f"a{index}", 10000 + index)
        active = {"queued", "armed", "waiting", "backoff", "busy_wait"}
        self.assertEqual(sum(item.state in active for item in engine.outbound), 16)
        self.assertEqual(sum(item.state == "failed" for item in engine.outbound), 0)
        self.assertLessEqual(len(engine.outbound), 16)
        failures = NodeEngine(1, 2, 1, limits)
        for index in range(40):
            request = failures.submit_text(f"x{index}", index * 100)
            assert request is not None
            failures.note_write(request, len(request.frame), True, None, index * 100)
            failures.poll(index * 100 + 10)
            self.assertLessEqual(len(failures.outbound), 16)
        self.assertLessEqual(len(failures.lines), 64)
        cancelled = NodeEngine(1, 2, 1, limits)
        for index in range(30):
            cancelled.resume()
            cancelled.submit_text(f"c{index}", index)
            cancelled.cancel()
            self.assertLessEqual(len(cancelled.outbound), 16)
            self.assertTrue(all(item.state == "cancelled" for item in cancelled.outbound))

    def test_ack_matches_only_a_completed_write(self) -> None:
        pair = Pair()
        pair.send_reliable("one", 0)
        self.assertIsNone(pair.a.submit_text("two", 1))
        queued = next(item for item in pair.a.outbound if item.state == "queued")
        early = encode_ack(AckFields(
            2, 1, queued.source_id, queued.boot_counter, queued.sequence, STATUS_ACCEPTED
        ))
        self.assertIn("没有匹配", pair.a.on_event(one_event(early), 2).lines[0])
        self.assertEqual(queued.state, "queued")
        self.assertIsNone(queued.full_write_ms)
        self.assertTrue(any(item.state == "waiting" for item in pair.a.outbound))

        short = NodeEngine(1, 2, 1, FAST)
        request = short.submit_text("s", 0)
        assert request is not None
        outcome = write_exact(ScriptPort([2, 0]).write, request.frame)
        short.note_write(request, outcome.accepted, outcome.complete, outcome.error, 0)
        message = short.outbound[0]
        self.assertIsNone(message.full_write_ms)
        ack = encode_ack(AckFields(2, 1, 1, 1, message.sequence, STATUS_ACCEPTED))
        self.assertIn("没有匹配", short.on_event(one_event(ack), 1).lines[0])
        self.assertNotEqual(message.state, "hop_cached")

        late = Pair()
        sent, _, _ = late.send_reliable("late", 0)
        late.a.poll(100)
        self.assertEqual(late.a.outbound[0].state, "backoff")
        received = push(late.b, sent.frame, 5)
        done = late.a.on_event(one_event(received.ack or b""), 120)
        self.assertIn("本跳缓存确认", done.lines[0])
        self.assertEqual(late.a.poll(500), [])


def bad_crc(frame: bytes) -> bytes:
    return frame[:-2] + struct.pack("<H", struct.unpack("<H", frame[-2:])[0] ^ 0x00FF)


if __name__ == "__main__":
    unittest.main()
