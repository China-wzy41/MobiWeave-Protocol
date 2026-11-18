import struct
import unittest

from v1frame import (
    DOC_SOS_FRAME,
    MAX_FRAME,
    DataFields,
    StreamParser,
    business_reject,
    crc16_ibm3740,
    encode_data,
    payload_text,
    two_node_text,
)


def sos_fields() -> DataFields:
    return DataFields(
        sender_id=1,
        receiver_id=2,
        source_id=1,
        destination_id=3,
        boot_counter=7,
        sequence=12,
        priority=2,
        age_ms=0,
        lifetime_ms=60000,
        hop_count=1,
        hop_limit=3,
        payload_type=1,
        payload=b"SOS",
    )


class CodecTest(unittest.TestCase):
    def test_crc_reference_vector(self) -> None:
        self.assertEqual(crc16_ibm3740(b"123456789"), 0x29B1)

    def test_document_sos_sample(self) -> None:
        self.assertEqual(encode_data(sos_fields()), DOC_SOS_FRAME)
        parser = StreamParser()
        events = parser.feed(DOC_SOS_FRAME, 0.0)
        self.assertEqual(len(events), 1)
        fields = events[0].fields
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertEqual(fields.destination_id, 3)
        self.assertEqual(fields.payload, b"SOS")
        self.assertEqual(events[0].crc, 0xD0BA)
        self.assertIsNone(business_reject(fields, local_id=2))

    def test_two_node_addresses_are_not_the_sos_relay_sample(self) -> None:
        frame = two_node_text(1, 2, 1, "hi")
        events = StreamParser().feed(frame, 0.0)
        fields = events[0].fields
        assert fields is not None
        self.assertEqual(
            (fields.sender_id, fields.receiver_id, fields.source_id, fields.destination_id),
            (1, 2, 1, 2),
        )
        self.assertNotEqual(fields.destination_id, 3)
        self.assertIsNone(business_reject(fields, local_id=2))
        self.assertEqual(business_reject(fields, local_id=1), "本跳地址不是本节点")

    def test_chunks_coalescing_noise_and_resync(self) -> None:
        good = two_node_text(2, 1, 4, "B004")
        parser = StreamParser()
        seen = []
        blob = b"\x00\xff\x11" + good + good
        for index in range(0, len(blob), 3):
            seen.extend(parser.feed(blob[index : index + 3], float(index)))
        crc_ok = [event for event in seen if event.kind == "crc_ok"]
        self.assertEqual(len(crc_ok), 2)
        self.assertEqual(payload_text(crc_ok[0].fields), "B004")

    def test_bad_crc_then_valid_frame(self) -> None:
        bad = two_node_text(1, 2, 2, "nope", bad_crc=True)
        good = two_node_text(1, 2, 3, "yes")
        events = StreamParser().feed(bad + good, 0.0)
        kinds = [event.kind for event in events]
        self.assertIn("bad_crc", kinds)
        self.assertEqual(kinds[-1], "crc_ok")
        self.assertEqual(payload_text(events[-1].fields), "yes")

    def test_magic_inside_body_is_not_a_new_frame(self) -> None:
        fields = sos_fields()
        raw = encode_data(
            DataFields(
                sender_id=1,
                receiver_id=2,
                source_id=1,
                destination_id=2,
                boot_counter=1,
                sequence=1,
                priority=0,
                age_ms=0,
                lifetime_ms=60000,
                hop_count=1,
                hop_limit=1,
                payload_type=1,
                payload=b"\xA5\x5A",
            )
        )
        events = StreamParser().feed(raw[:8] + raw[8:], 0.0)
        crc_ok = [event for event in events if event.kind == "crc_ok"]
        self.assertEqual(len(crc_ok), 1)
        assert crc_ok[0].fields is not None
        self.assertEqual(crc_ok[0].fields.payload, b"\xA5\x5A")
        self.assertEqual(business_reject(crc_ok[0].fields, 2), "不是合法 UTF-8")
        self.assertIsNotNone(fields)

    def test_binary_00_and_ff_are_not_truncated(self) -> None:
        frame = encode_data(
            DataFields(
                sender_id=1,
                receiver_id=2,
                source_id=1,
                destination_id=2,
                boot_counter=1,
                sequence=8,
                priority=0,
                age_ms=0,
                lifetime_ms=60000,
                hop_count=1,
                hop_limit=1,
                payload_type=1,
                payload=b"\x00\xff",
            )
        )
        event = StreamParser().feed(frame, 0.0)[0]
        assert event.fields is not None
        self.assertEqual(event.fields.payload, b"\x00\xff")
        self.assertEqual(business_reject(event.fields, 2), "不是合法 UTF-8")
        self.assertEqual(payload_text(DataFields(
            sender_id=1, receiver_id=2, source_id=1, destination_id=2,
            boot_counter=1, sequence=1, priority=0, age_ms=0, lifetime_ms=1,
            hop_count=1, hop_limit=1, payload_type=1, payload="你".encode("utf-8"),
        )), "你")

    def test_utf8_length_limit(self) -> None:
        exact = "a" * 132
        self.assertEqual(len(two_node_text(1, 2, 1, exact)), 8 + 28 + 132)
        with self.assertRaises(ValueError):
            two_node_text(1, 2, 1, "a" * 133)
        with self.assertRaises(ValueError):
            two_node_text(1, 2, 1, "测" * 45)

    def test_oversized_header_stays_bounded_and_recovers(self) -> None:
        good = two_node_text(1, 2, 9, "after")
        blob = b"\x00" * 20000 + b"\xA5\x5A\x01\x01\xff\xff" + good
        parser = StreamParser()
        events = parser.feed(blob, 0.0)
        self.assertLessEqual(len(parser.buf), MAX_FRAME)
        crc_ok = [event for event in events if event.kind == "crc_ok"]
        self.assertEqual(len(crc_ok), 1)
        self.assertEqual(payload_text(crc_ok[0].fields), "after")
        self.assertTrue(any(event.kind == "bad_length" for event in events))

    def test_idle_timeout_is_a_tool_default(self) -> None:
        parser = StreamParser(idle_s=1.0)
        self.assertEqual(parser.idle_s, 1.0)
        parser.feed(b"\xA5\x5A\x01", 0.0)
        events = parser.feed(b"", 1.0)
        self.assertEqual(events[0].kind, "timeout")
        self.assertIn("不是冻结", events[0].reason)
        good = two_node_text(2, 1, 1, "later")
        recovered = parser.feed(good, 1.1)
        self.assertEqual(recovered[-1].kind, "crc_ok")

    def test_crc_is_little_endian_on_the_wire(self) -> None:
        frame = two_node_text(1, 2, 1, "x")
        covered = frame[2:-2]
        crc = crc16_ibm3740(covered)
        self.assertEqual(frame[-2:], struct.pack("<H", crc))


if __name__ == "__main__":
    unittest.main()
