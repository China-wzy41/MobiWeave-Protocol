// 协议核心的主机端测试。不需要开发板，g++ 直接编译运行。
//
// 覆盖：样例逐字节、流式分帧、ACK 四状态、超时重传、去重、超时用尽。
#include <cstdio>
#include <cstring>
#include <vector>

#include "mw_protocol.h"

static int gPass = 0;
static int gFail = 0;

static void check(const char* name, bool ok, const char* detail = "") {
  if (ok) {
    ++gPass;
    std::printf("PASS  %s\n", name);
  } else {
    ++gFail;
    std::printf("FAIL  %s %s\n", name, detail);
  }
}

static const uint8_t kDocData[] = {
    0xA5, 0x5A, 0x01, 0x01, 0x1F, 0x00, 0x01, 0x00, 0x02, 0x00, 0x01, 0x00,
    0x03, 0x00, 0x07, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x00, 0x00, 0x02, 0x00,
    0x00, 0x00, 0x00, 0x60, 0xEA, 0x00, 0x00, 0x01, 0x03, 0x01, 0x53, 0x4F,
    0x53, 0xBA, 0xD0};

static const uint8_t kDocAck[] = {
    0xA5, 0x5A, 0x01, 0x02, 0x0F, 0x00, 0x02, 0x00, 0x01, 0x00, 0x01, 0x00,
    0x07, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x00, 0x00, 0x00, 0xF0, 0x82};

static mw::DataFrame sampleData() {
  mw::DataFrame f;
  f.sender = 1;
  f.receiver = 2;
  f.id = {1, 7, 12};
  f.destination = 3;
  f.priority = 2;
  f.ageMs = 0;
  f.lifetimeMs = 60000;
  f.hopCount = 1;
  f.hopLimit = 3;
  f.payloadType = 1;
  f.payload[0] = 'S';
  f.payload[1] = 'O';
  f.payload[2] = 'S';
  f.payloadLen = 3;
  return f;
}

// ---------------------------------------------------------------- 编解码
static void testCodec() {
  uint8_t buf[mw::kFrameMax];
  const size_t n = mw::encodeData(sampleData(), buf, sizeof(buf));
  check("DATA 编码与文档样例逐字节一致",
        n == sizeof(kDocData) && std::memcmp(buf, kDocData, n) == 0);

  mw::AckFrame ack;
  ack.sender = 2;
  ack.receiver = 1;
  ack.id = {1, 7, 12};
  ack.status = mw::AckStatus::Accepted;
  const size_t m = mw::encodeAck(ack, buf, sizeof(buf));
  check("ACK 编码与文档样例逐字节一致",
        m == sizeof(kDocAck) && std::memcmp(buf, kDocAck, m) == 0);

  mw::Frame frame;
  size_t consumed = 0;
  const mw::ParseResult r = mw::decodeFrame(kDocData, sizeof(kDocData), frame, consumed);
  check("DATA 解码成功", r == mw::ParseResult::Ok && consumed == sizeof(kDocData));
  check("DATA 字段还原", frame.data.payloadLen == 3 &&
                             frame.data.destination == 3 &&
                             frame.data.id.source == 1 &&
                             frame.data.id.boot == 7 &&
                             frame.data.id.seq == 12);

  const mw::ParseResult ra = mw::decodeFrame(kDocAck, sizeof(kDocAck), frame, consumed);
  check("ACK 解码成功且状态为 ACCEPTED",
        ra == mw::ParseResult::Ok && frame.ack.status == mw::AckStatus::Accepted &&
            frame.ack.id.seq == 12);

  uint8_t damaged[sizeof(kDocData)];
  std::memcpy(damaged, kDocData, sizeof(kDocData));
  damaged[36] = 0x54;   // SOS -> SOT
  check("坏 CRC 被拒绝",
        mw::decodeFrame(damaged, sizeof(damaged), frame, consumed) == mw::ParseResult::BadCrc);

  check("帧太短返回 NeedMore",
        mw::decodeFrame(kDocData, 5, frame, consumed) == mw::ParseResult::NeedMore);

  uint8_t big[256];
  mw::DataFrame full = sampleData();
  full.payloadLen = mw::kPayloadMax;
  const size_t bigLen = mw::encodeData(full, big, sizeof(big));
  check("最大载荷 132 → 整帧 168", bigLen == 168);
  check("168 字节帧可解码",
        mw::decodeFrame(big, bigLen, frame, consumed) == mw::ParseResult::Ok &&
            frame.data.payloadLen == mw::kPayloadMax);

  full.payloadLen = mw::kPayloadMax + 1;
  check("超长载荷拒绝编码", mw::encodeData(full, big, sizeof(big)) == 0);
}

// ---------------------------------------------------------------- 流式分帧
static void testStream() {
  mw::StreamParser parser;
  mw::Frame frame;

  check("半帧不输出", parser.feed(kDocData, 10, frame) == 0 && parser.pendingBytes() == 10);
  check("补齐后输出一帧", parser.feed(kDocData + 10, sizeof(kDocData) - 10, frame) == sizeof(kDocData));

  parser.reset();
  uint8_t twice[sizeof(kDocData) * 2];
  std::memcpy(twice, kDocData, sizeof(kDocData));
  std::memcpy(twice + sizeof(kDocData), kDocData, sizeof(kDocData));
  size_t got = parser.feed(twice, sizeof(twice), frame);
  check("粘包先出一帧", got == sizeof(kDocData));
  got = parser.feed(nullptr, 0, frame);
  check("剩余半帧待补齐（同一次喂入已处理完）", got == 0);

  parser.reset();
  size_t count = 0;
  for (size_t i = 0; i < sizeof(kDocData); ++i) {
    if (parser.feed(&kDocData[i], 1, frame) == sizeof(kDocData)) {
      ++count;
    }
  }
  check("逐字节输入得到一帧", count == 1);

  const uint8_t noise[] = {0x00, 0xFF, 0xA5, 0x11, 0xA5};
  parser.reset();
  parser.feed(noise, sizeof(noise), frame);
  check("噪声后恢复", parser.feed(kDocData, sizeof(kDocData), frame) == sizeof(kDocData));

  uint8_t damaged[sizeof(kDocData)];
  std::memcpy(damaged, kDocData, sizeof(kDocData));
  damaged[36] = 0x54;
  parser.reset();
  parser.feed(damaged, sizeof(damaged), frame);
  check("坏帧被丢弃并记录原因", parser.lastResult() == mw::ParseResult::BadCrc);
  check("坏帧后恢复", parser.feed(kDocData, sizeof(kDocData), frame) == sizeof(kDocData));

  // 正文里带帧头
  mw::DataFrame tricky = sampleData();
  tricky.payload[0] = 0xA5;
  tricky.payload[1] = 0x5A;
  tricky.payload[2] = 0xA5;
  uint8_t trickyBuf[mw::kFrameMax];
  const size_t trickyLen = mw::encodeData(tricky, trickyBuf, sizeof(trickyBuf));
  parser.reset();
  size_t frames = 0;
  for (size_t i = 0; i < trickyLen; ++i) {
    if (parser.feed(&trickyBuf[i], 1, frame) == trickyLen) {
      ++frames;
    }
  }
  check("正文含 A5 5A 不误判", frames == 1);
}

// ---------------------------------------------------------------- 接收缓存
static void testReceiverCache() {
  mw::ReceiverCache cache;
  mw::DataFrame f = sampleData();

  check("首次接收 ACCEPTED", cache.admit(f, 1000) == mw::AckStatus::Accepted);
  check("重复接收 ALREADY_HAVE", cache.admit(f, 1100) == mw::AckStatus::AlreadyHave);
  check("缓存计数为 1", cache.count() == 1);

  mw::DataFrame expired = sampleData();
  expired.id.seq = 13;
  expired.ageMs = 60000;
  expired.lifetimeMs = 60000;
  check("已过期 EXPIRED", cache.admit(expired, 1200) == mw::AckStatus::Expired);

  mw::DataFrame invalid = sampleData();
  invalid.id.seq = 0;
  check("编号非法不接收", cache.admit(invalid, 1300) != mw::AckStatus::Accepted);

  cache.clear();
  mw::DataFrame filler = sampleData();
  for (size_t i = 0; i < mw::kCacheSlots; ++i) {
    filler.id.seq = 100 + i;
    cache.admit(filler, 2000);
  }
  mw::DataFrame overflow = sampleData();
  overflow.id.seq = 999;
  check("缓存满回 BUSY", cache.admit(overflow, 2001) == mw::AckStatus::Busy);

  mw::ReceiverCache timed;
  mw::DataFrame shortLife = sampleData();
  shortLife.ageMs = 0;
  shortLife.lifetimeMs = 1000;
  timed.admit(shortLife, 5000);
  check("本地计时到期的条目可统计", timed.expiredCount(6001) == 1);
}

// ---------------------------------------------------------------- 发送状态机
static void testSender() {
  uint8_t buf[mw::kFrameMax];
  size_t len = 0;

  // 正常收到 ACCEPTED
  {
    mw::OutboundTx tx;
    tx.load(sampleData(), 0);
    check("首次 poll 立即发送", tx.poll(0, buf, sizeof(buf), len) && tx.attempt() == 1);
    check("未到超时不重发", !tx.poll(999, buf, sizeof(buf), len));

    mw::AckFrame ack;
    ack.sender = 2;
    ack.receiver = 1;
    ack.id = {1, 7, 12};
    ack.status = mw::AckStatus::Accepted;
    tx.onAck(ack, 1000);
    check("ACCEPTED → DONE", tx.state() == mw::TxState::Done);
    check("DONE 后不再发送", !tx.poll(5000, buf, sizeof(buf), len));
  }

  // 超时重传，三次用尽
  {
    mw::OutboundTx tx;
    tx.load(sampleData(), 0);
    tx.poll(0, buf, sizeof(buf), len);
    check("1000ms 后重传第 2 次", tx.poll(1000, buf, sizeof(buf), len) && tx.attempt() == 2);
    check("2000ms 后重传第 3 次", tx.poll(2000, buf, sizeof(buf), len) && tx.attempt() == 3);
    check("第三次后超时置 FAILED", !tx.poll(3000, buf, sizeof(buf), len) &&
                                       tx.state() == mw::TxState::Failed);
  }

  // ALREADY_HAVE 也算本跳完成
  {
    mw::OutboundTx tx;
    tx.load(sampleData(), 0);
    tx.poll(0, buf, sizeof(buf), len);
    mw::AckFrame ack;
    ack.sender = 2;
    ack.receiver = 1;
    ack.id = {1, 7, 12};
    ack.status = mw::AckStatus::AlreadyHave;
    tx.onAck(ack, 500);
    check("ALREADY_HAVE → DONE", tx.state() == mw::TxState::Done);
  }

  // BUSY：保留消息，延后重试
  {
    mw::OutboundTx tx;
    tx.load(sampleData(), 0);
    tx.poll(0, buf, sizeof(buf), len);
    mw::AckFrame ack;
    ack.sender = 2;
    ack.receiver = 1;
    ack.id = {1, 7, 12};
    ack.status = mw::AckStatus::Busy;
    tx.onAck(ack, 400);
    check("BUSY → DEFERRED", tx.state() == mw::TxState::Deferred);
    check("DEFERRED 期间不立即重发", !tx.poll(900, buf, sizeof(buf), len));
    check("延后到点重发", tx.poll(1400, buf, sizeof(buf), len) && tx.attempt() == 2);
  }

  // EXPIRED：结束本轮，不标记送达
  {
    mw::OutboundTx tx;
    tx.load(sampleData(), 0);
    tx.poll(0, buf, sizeof(buf), len);
    mw::AckFrame ack;
    ack.sender = 2;
    ack.receiver = 1;
    ack.id = {1, 7, 12};
    ack.status = mw::AckStatus::Expired;
    tx.onAck(ack, 300);
    check("EXPIRED → REJECTED", tx.state() == mw::TxState::Rejected);
  }

  // 不匹配的 ACK 不得确认
  {
    mw::OutboundTx tx;
    tx.load(sampleData(), 0);
    tx.poll(0, buf, sizeof(buf), len);

    mw::AckFrame wrongPeer;
    wrongPeer.sender = 9;
    wrongPeer.receiver = 1;
    wrongPeer.id = {1, 7, 12};
    wrongPeer.status = mw::AckStatus::Accepted;
    tx.onAck(wrongPeer, 100);
    check("编号对但来源不对的 ACK 被忽略", tx.state() == mw::TxState::WaitingAck);

    mw::AckFrame wrongId;
    wrongId.sender = 2;
    wrongId.receiver = 1;
    wrongId.id = {1, 7, 13};
    wrongId.status = mw::AckStatus::Accepted;
    tx.onAck(wrongId, 100);
    check("来源对但编号不对的 ACK 被忽略", tx.state() == mw::TxState::WaitingAck);

    mw::AckFrame wrongTarget;
    wrongTarget.sender = 2;
    wrongTarget.receiver = 7;
    wrongTarget.id = {1, 7, 12};
    wrongTarget.status = mw::AckStatus::Accepted;
    tx.onAck(wrongTarget, 100);
    check("发给他人的 ACK 被忽略", tx.state() == mw::TxState::WaitingAck);

    mw::AckFrame unknown;
    unknown.sender = 2;
    unknown.receiver = 1;
    unknown.id = {1, 7, 12};
    unknown.status = static_cast<mw::AckStatus>(9);
    tx.onAck(unknown, 100);
    check("未知状态不确认", tx.state() == mw::TxState::WaitingAck);
  }
}

// ---------------------------------------------------------------- 端到端
// A 发 → B 收 → B 回 ACK → A 收到后停止重试
static void testLoopback() {
  mw::StreamParser aRx;
  mw::StreamParser bRx;
  mw::ReceiverCache bCache;
  mw::OutboundTx tx;
  mw::Frame frame;
  uint8_t wire[mw::kFrameMax];
  size_t len = 0;

  tx.load(sampleData(), 0);
  check("A 发出首帧", tx.poll(0, wire, sizeof(wire), len) && len == 39);

  // B 侧：收帧
  check("B 解析出 DATA", bRx.feed(wire, len, frame) == len && frame.type == mw::kTypeData);

  // B 侧：判重并入缓存，回 ACCEPTED
  const mw::AckStatus status = bCache.admit(frame.data, 10);
  check("B 判定 ACCEPTED", status == mw::AckStatus::Accepted);

  mw::AckFrame reply;
  reply.sender = 2;
  reply.receiver = 1;
  reply.id = frame.data.id;
  reply.status = status;
  uint8_t ackWire[mw::kFrameMax];
  const size_t ackLen = mw::encodeAck(reply, ackWire, sizeof(ackWire));
  check("B 发出 ACK，23 字节", ackLen == 23);

  // A 侧：收 ACK
  mw::Frame ackFrame;
  check("A 解析出 ACK", aRx.feed(ackWire, ackLen, ackFrame) == ackLen &&
                            ackFrame.type == mw::kTypeAck);
  tx.onAck(ackFrame.ack, 100);
  check("A 收到 ACCEPTED 后结束本跳", tx.state() == mw::TxState::Done);

  // 再来一次同样内容：B 应回 ALREADY_HAVE，且不重复交付
  mw::OutboundTx tx2;
  tx2.load(sampleData(), 2000);
  tx2.poll(2000, wire, sizeof(wire), len);
  bRx.feed(wire, len, frame);
  const mw::AckStatus again = bCache.admit(frame.data, 2010);
  check("重传时 B 回 ALREADY_HAVE", again == mw::AckStatus::AlreadyHave);
  check("B 缓存没增加", bCache.count() == 1);
}

int main() {
  std::printf("=== MobiWeave 协议核心测试 ===\n\n");
  testCodec();
  testStream();
  testReceiverCache();
  testSender();
  testLoopback();
  std::printf("\n%d passed, %d failed\n", gPass, gFail);
  return gFail == 0 ? 0 : 1;
}
