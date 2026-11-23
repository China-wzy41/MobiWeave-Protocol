#include "mw_protocol.h"

#include <cstring>

namespace mw {

namespace {

constexpr uint8_t kMagic0 = 0xA5;
constexpr uint8_t kMagic1 = 0x5A;

void put16(uint8_t* buf, size_t& pos, uint16_t value) {
  buf[pos++] = static_cast<uint8_t>(value & 0xFF);
  buf[pos++] = static_cast<uint8_t>((value >> 8) & 0xFF);
}

void put32(uint8_t* buf, size_t& pos, uint32_t value) {
  for (int i = 0; i < 4; ++i) {
    buf[pos++] = static_cast<uint8_t>((value >> (8 * i)) & 0xFF);
  }
}

uint16_t get16(const uint8_t* buf) {
  return static_cast<uint16_t>(buf[0]) |
         static_cast<uint16_t>(static_cast<uint16_t>(buf[1]) << 8);
}

uint32_t get32(const uint8_t* buf) {
  return static_cast<uint32_t>(buf[0]) |
         (static_cast<uint32_t>(buf[1]) << 8) |
         (static_cast<uint32_t>(buf[2]) << 16) |
         (static_cast<uint32_t>(buf[3]) << 24);
}

// 时间比较：允许 millis() 回绕。
bool reached(uint32_t nowMs, uint32_t deadlineMs) {
  return static_cast<int32_t>(nowMs - deadlineMs) >= 0;
}

}  // namespace

// ---------------------------------------------------------------- CRC
uint16_t crc16(const uint8_t* data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit) {
      if (crc & 0x8000) {
        crc = static_cast<uint16_t>((crc << 1) ^ 0x1021);
      } else {
        crc = static_cast<uint16_t>(crc << 1);
      }
    }
  }
  return crc;
}

// ---------------------------------------------------------------- 编解码
size_t encodeData(const DataFrame& frame, uint8_t* out, size_t capacity) {
  if (out == nullptr || frame.payloadLen > kPayloadMax) {
    return 0;
  }
  const size_t bodyLength = kDataFixed + frame.payloadLen;
  const size_t total = kFrameOverhead + bodyLength;
  if (capacity < total) {
    return 0;
  }

  size_t pos = 0;
  out[pos++] = kMagic0;
  out[pos++] = kMagic1;
  out[pos++] = kVersion;
  out[pos++] = kTypeData;
  put16(out, pos, static_cast<uint16_t>(bodyLength));

  put16(out, pos, frame.sender);
  put16(out, pos, frame.receiver);
  put16(out, pos, frame.id.source);
  put16(out, pos, frame.destination);
  put32(out, pos, frame.id.boot);
  put32(out, pos, frame.id.seq);
  out[pos++] = frame.priority;
  put32(out, pos, frame.ageMs);
  put32(out, pos, frame.lifetimeMs);
  out[pos++] = frame.hopCount;
  out[pos++] = frame.hopLimit;
  out[pos++] = frame.payloadType;
  for (size_t i = 0; i < frame.payloadLen; ++i) {
    out[pos++] = frame.payload[i];
  }

  put16(out, pos, crc16(out + 2, pos - 2));
  return pos;
}

size_t encodeAck(const AckFrame& frame, uint8_t* out, size_t capacity) {
  if (out == nullptr) {
    return 0;
  }
  const size_t total = kFrameOverhead + kAckBodyLen;
  if (capacity < total) {
    return 0;
  }

  size_t pos = 0;
  out[pos++] = kMagic0;
  out[pos++] = kMagic1;
  out[pos++] = kVersion;
  out[pos++] = kTypeAck;
  put16(out, pos, static_cast<uint16_t>(kAckBodyLen));

  put16(out, pos, frame.sender);
  put16(out, pos, frame.receiver);
  put16(out, pos, frame.id.source);
  put32(out, pos, frame.id.boot);
  put32(out, pos, frame.id.seq);
  out[pos++] = static_cast<uint8_t>(frame.status);

  put16(out, pos, crc16(out + 2, pos - 2));
  return pos;
}

const char* parseResultName(ParseResult result) {
  switch (result) {
    case ParseResult::Ok: return "OK";
    case ParseResult::NeedMore: return "NEED_MORE";
    case ParseResult::BadMagic: return "BAD_MAGIC";
    case ParseResult::BadVersion: return "UNSUPPORTED_VERSION";
    case ParseResult::BadType: return "UNSUPPORTED_TYPE";
    case ParseResult::BadLength: return "BAD_LENGTH";
    case ParseResult::BadCrc: return "BAD_CRC";
  }
  return "UNKNOWN";
}

ParseResult decodeFrame(const uint8_t* buf, size_t length, Frame& out,
                        size_t& consumed) {
  consumed = 0;
  if (length < kFrameOverhead) {
    return length >= 2 ? ParseResult::NeedMore : ParseResult::NeedMore;
  }
  if (buf[0] != kMagic0 || buf[1] != kMagic1) {
    return ParseResult::BadMagic;
  }
  if (buf[2] != kVersion) {
    return ParseResult::BadVersion;
  }
  const uint8_t type = buf[3];
  if (type != kTypeData && type != kTypeAck) {
    return ParseResult::BadType;
  }
  const uint16_t bodyLength = get16(buf + 4);
  size_t limit = 0;
  if (type == kTypeData) {
    if (bodyLength < kDataFixed || bodyLength > kDataBodyMax) {
      return ParseResult::BadLength;
    }
    limit = kDataBodyMax;
  } else {
    if (bodyLength != kAckBodyLen) {
      return ParseResult::BadLength;
    }
    limit = kAckBodyLen;
  }
  (void)limit;

  const size_t total = kFrameOverhead + bodyLength;
  if (length < total) {
    return ParseResult::NeedMore;
  }
  if (get16(buf + total - 2) != crc16(buf + 2, total - 4)) {
    return ParseResult::BadCrc;
  }

  const uint8_t* body = buf + 6;
  out.type = type;
  if (type == kTypeData) {
    DataFrame& d = out.data;
    d.sender = get16(body);
    d.receiver = get16(body + 2);
    d.id.source = get16(body + 4);
    d.destination = get16(body + 6);
    d.id.boot = get32(body + 8);
    d.id.seq = get32(body + 12);
    d.priority = body[16];
    d.ageMs = get32(body + 17);
    d.lifetimeMs = get32(body + 21);
    d.hopCount = body[25];
    d.hopLimit = body[26];
    d.payloadType = body[27];
    d.payloadLen = bodyLength - kDataFixed;
    if (d.payloadLen > kPayloadMax) {
      return ParseResult::BadLength;
    }
    std::memcpy(d.payload, body + kDataFixed, d.payloadLen);
  } else {
    AckFrame& a = out.ack;
    a.sender = get16(body);
    a.receiver = get16(body + 2);
    a.id.source = get16(body + 4);
    a.id.boot = get32(body + 6);
    a.id.seq = get32(body + 10);
    a.status = static_cast<AckStatus>(body[14]);
  }

  consumed = total;
  return ParseResult::Ok;
}

// ---------------------------------------------------------------- 流式分帧
size_t StreamParser::feed(const uint8_t* bytes, size_t length, Frame& out) {
  for (size_t i = 0; i < length; ++i) {
    if (used_ == sizeof(buffer_)) {
      // 缓冲区满仍凑不齐，丢掉最早一字节重新同步
      std::memmove(buffer_, buffer_ + 1, used_ - 1);
      --used_;
      lastResult_ = ParseResult::BadLength;
    }
    buffer_[used_++] = bytes[i];

    while (true) {
      // 找帧头
      while (used_ > 0 && buffer_[0] != kMagic0) {
        std::memmove(buffer_, buffer_ + 1, --used_);
      }
      if (used_ < 2) {
        break;
      }
      if (buffer_[1] != kMagic1) {
        std::memmove(buffer_, buffer_ + 1, --used_);
        continue;
      }
      if (used_ < 6) {
        break;
      }

      const uint8_t type = buffer_[3];
      const uint16_t bodyLength = get16(buffer_ + 4);
      const bool headerOk =
          buffer_[2] == kVersion &&
          ((type == kTypeData && bodyLength >= kDataFixed && bodyLength <= kDataBodyMax) ||
           (type == kTypeAck && bodyLength == kAckBodyLen));
      if (!headerOk) {
        lastResult_ = (buffer_[2] != kVersion) ? ParseResult::BadVersion
                      : (type != kTypeData && type != kTypeAck) ? ParseResult::BadType
                                                                : ParseResult::BadLength;
        std::memmove(buffer_, buffer_ + 1, --used_);
        continue;
      }

      const size_t total = kFrameOverhead + bodyLength;
      if (used_ < total) {
        break;   // 半帧，等后续字节
      }

      size_t consumed = 0;
      const ParseResult result = decodeFrame(buffer_, used_, out, consumed);
      if (result != ParseResult::Ok) {
        lastResult_ = result;
        std::memmove(buffer_, buffer_ + 1, --used_);
        continue;
      }

      // 成功：吃掉这一帧，返回给调用方
      std::memmove(buffer_, buffer_ + consumed, used_ - consumed);
      used_ -= consumed;
      lastResult_ = ParseResult::Ok;
      return consumed;
    }
  }
  return 0;
}

// ---------------------------------------------------------------- 接收侧
AckStatus ReceiverCache::admit(const DataFrame& frame, uint32_t nowMs) {
  // 调用方应保证编号合法；这里再守一次，非法编号不进入缓存。
  if (!frame.id.valid()) {
    return AckStatus::Busy;
  }
  if (frame.lifetimeMs == 0 || frame.ageMs >= frame.lifetimeMs) {
    return AckStatus::Expired;
  }
  if (holds(frame.id)) {
    return AckStatus::AlreadyHave;
  }

  Entry* slot = nullptr;
  for (Entry& entry : slots_) {
    if (!entry.used) {
      slot = &entry;
      break;
    }
  }
  if (slot == nullptr) {
    return AckStatus::Busy;
  }

  slot->used = true;
  slot->id = frame.id;
  slot->storedAtMs = nowMs;
  slot->ageMsAtStore = frame.ageMs;
  slot->lifetimeMs = frame.lifetimeMs;
  slot->destination = frame.destination;
  slot->priority = frame.priority;
  return AckStatus::Accepted;
}

bool ReceiverCache::holds(const MessageId& id) const {
  for (const Entry& entry : slots_) {
    if (entry.used && entry.id == id) {
      return true;
    }
  }
  return false;
}

size_t ReceiverCache::count() const {
  size_t n = 0;
  for (const Entry& entry : slots_) {
    if (entry.used) {
      ++n;
    }
  }
  return n;
}

void ReceiverCache::clear() {
  for (Entry& entry : slots_) {
    entry = Entry{};
  }
}

size_t ReceiverCache::expiredCount(uint32_t nowMs) const {
  size_t n = 0;
  for (const Entry& entry : slots_) {
    if (!entry.used) {
      continue;
    }
    const uint32_t age = entry.ageMsAtStore + (nowMs - entry.storedAtMs);
    if (age >= entry.lifetimeMs) {
      ++n;
    }
  }
  return n;
}

// ---------------------------------------------------------------- 发送侧
const char* txStateName(TxState state) {
  switch (state) {
    case TxState::Idle: return "IDLE";
    case TxState::WaitingAck: return "WAITING_ACK";
    case TxState::Done: return "DONE";
    case TxState::Failed: return "FAILED";
    case TxState::Deferred: return "DEFERRED";
    case TxState::Rejected: return "REJECTED";
  }
  return "UNKNOWN";
}

void OutboundTx::load(const DataFrame& frame, uint32_t nowMs) {
  frame_ = frame;
  state_ = TxState::WaitingAck;
  attempt_ = 0;
  deadlineMs_ = nowMs;   // 立即可以发
}

void OutboundTx::reset() {
  state_ = TxState::Idle;
  attempt_ = 0;
  deadlineMs_ = 0;
}

bool OutboundTx::poll(uint32_t nowMs, uint8_t* out, size_t capacity,
                      size_t& frameLength) {
  frameLength = 0;
  if (state_ != TxState::WaitingAck && state_ != TxState::Deferred) {
    return false;
  }
  if (!reached(nowMs, deadlineMs_)) {
    return false;
  }
  if (attempt_ >= kMaxAttempts) {
    state_ = TxState::Failed;
    return false;
  }

  ++attempt_;
  frameLength = encodeData(frame_, out, capacity);
  if (frameLength == 0) {
    state_ = TxState::Failed;
    return false;
  }
  state_ = TxState::WaitingAck;
  deadlineMs_ = nowMs + kAckTimeoutMs;
  return true;
}

void OutboundTx::onAck(const AckFrame& ack, uint32_t nowMs) {
  if (state_ != TxState::WaitingAck && state_ != TxState::Deferred) {
    return;
  }
  // 必须同时匹配：来自预期的本跳接收节点、发给本节点、编号一致。
  if (ack.sender != frame_.receiver) {
    return;
  }
  if (ack.receiver != frame_.sender) {
    return;
  }
  if (!(ack.id == frame_.id)) {
    return;
  }

  switch (ack.status) {
    case AckStatus::Accepted:
    case AckStatus::AlreadyHave:
      state_ = TxState::Done;
      break;
    case AckStatus::Busy:
      // 结束本轮立即重试，保留消息，等下一次机会
      state_ = TxState::Deferred;
      deadlineMs_ = nowMs + kAckTimeoutMs;
      break;
    case AckStatus::Expired:
      state_ = TxState::Rejected;
      break;
    default:
      break;   // 未知状态不得据此确认成功
  }
}

}  // namespace mw
