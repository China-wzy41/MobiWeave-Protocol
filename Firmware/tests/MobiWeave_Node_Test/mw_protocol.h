// MobiWeave 协议 V1 核心实现：组帧、解析、ACK、重传、去重。
//
// 这个文件不依赖 Arduino，可以在电脑上用 g++ 直接跑测试。
// 帧格式以 docs/protocol/protocol-v1.md 第 0 节冻结版本为准：
//   A5 5A | version | frame_type | body_length(LE) | body | crc(LE)
//   CRC 覆盖 version 到 body 末尾，不含帧头和 CRC 本身。
#ifndef MW_PROTOCOL_H
#define MW_PROTOCOL_H

#include <cstddef>
#include <cstdint>

namespace mw {

// ---------------------------------------------------------------- 常量
constexpr uint8_t kVersion = 1;
constexpr uint8_t kTypeData = 1;
constexpr uint8_t kTypeAck = 2;

constexpr size_t kFrameOverhead = 8;   // 帧头 2 + ver 1 + type 1 + len 2 + crc 2
constexpr size_t kDataFixed = 28;      // DATA 正文固定部分
constexpr size_t kDataBodyMax = 160;   // M1 目标值，允许仅下调
constexpr size_t kAckBodyLen = 15;
constexpr size_t kFrameMax = kFrameOverhead + kDataBodyMax;   // 168
constexpr size_t kPayloadMax = kDataBodyMax - kDataFixed;     // 132

// ACK 状态（冻结取值）
enum class AckStatus : uint8_t {
  Accepted = 0,     // 首次收到，已放内存缓存
  AlreadyHave = 1,  // 已持有，不重复交付
  Busy = 2,         // 无可用缓存，本次未接收
  Expired = 3,      // 已过期，拒绝
};

// 非冻结参数（第 0.2 节），代码里做成常量
constexpr uint32_t kAckTimeoutMs = 1000;
constexpr uint8_t kMaxAttempts = 3;      // 首发 + 重传 2 次
constexpr size_t kCacheSlots = 8;        // 接收缓存条数

// ---------------------------------------------------------------- 消息编号
struct MessageId {
  uint16_t source = 0;
  uint32_t boot = 0;
  uint32_t seq = 0;

  bool operator==(const MessageId& other) const {
    return source == other.source && boot == other.boot && seq == other.seq;
  }
  bool valid() const { return source != 0 && boot != 0 && seq != 0; }
};

// ---------------------------------------------------------------- 帧
struct DataFrame {
  uint16_t sender = 0;
  uint16_t receiver = 0;
  MessageId id;
  uint16_t destination = 0;
  uint8_t priority = 0;
  uint32_t ageMs = 0;
  uint32_t lifetimeMs = 0;
  uint8_t hopCount = 0;
  uint8_t hopLimit = 0;
  uint8_t payloadType = 1;
  uint8_t payload[kPayloadMax] = {};
  size_t payloadLen = 0;
};

struct AckFrame {
  uint16_t sender = 0;
  uint16_t receiver = 0;
  MessageId id;
  AckStatus status = AckStatus::Accepted;
};

struct Frame {
  uint8_t type = 0;
  DataFrame data;
  AckFrame ack;
};

// ---------------------------------------------------------------- 编解码
uint16_t crc16(const uint8_t* data, size_t length);

size_t encodeData(const DataFrame& frame, uint8_t* out, size_t capacity);
size_t encodeAck(const AckFrame& frame, uint8_t* out, size_t capacity);

enum class ParseResult {
  Ok,
  NeedMore,       // 缓冲区里还没有完整帧
  BadMagic,
  BadVersion,
  BadType,
  BadLength,
  BadCrc,
};

const char* parseResultName(ParseResult result);

// 解析一条完整帧；要求长度与声明一致。consumed 返回该帧占用的字节数。
ParseResult decodeFrame(const uint8_t* buf, size_t length, Frame& out,
                        size_t& consumed);

// ---------------------------------------------------------------- 流式分帧
// 处理半帧、粘包、正文里出现 A5 5A 的情况。
class StreamParser {
 public:
  // 喂入字节，返回 0 表示还没凑成一帧；>0 表示 out 里有一帧，
  // 返回值是帧长。出错时返回 0 并通过 lastResult() 说明原因。
  size_t feed(const uint8_t* bytes, size_t length, Frame& out);

  ParseResult lastResult() const { return lastResult_; }
  bool hasPartial() const { return used_ > 0; }
  size_t pendingBytes() const { return used_; }
  void reset() { used_ = 0; }

 private:
  uint8_t buffer_[kFrameMax];
  size_t used_ = 0;
  ParseResult lastResult_ = ParseResult::NeedMore;
};

// ---------------------------------------------------------------- 接收侧
// 内存缓存 + 去重。M1 不做持久化。
class ReceiverCache {
 public:
  // 收到一条 DATA 后按第三轮规则给出应当回复的状态。
  // 若判定为 Accepted，会把消息存入缓存。
  AckStatus admit(const DataFrame& frame, uint32_t nowMs);

  bool holds(const MessageId& id) const;
  size_t count() const;
  void clear();

  // 缓存里是否有已过期条目可清理（M1 只统计，不实现淘汰策略）
  size_t expiredCount(uint32_t nowMs) const;

 private:
  struct Entry {
    bool used = false;
    MessageId id;
    uint32_t storedAtMs = 0;
    uint32_t ageMsAtStore = 0;
    uint32_t lifetimeMs = 0;
    uint16_t destination = 0;
    uint8_t priority = 0;
  };
  Entry slots_[kCacheSlots];
};

// ---------------------------------------------------------------- 发送侧
enum class TxState {
  Idle,
  WaitingAck,   // 已发出，等 ACK
  Done,         // 本跳确认完成
  Failed,       // 重试用尽
  Deferred,     // 对方回 BUSY，保留消息等下一次机会
  Rejected,     // 对方回 EXPIRED
};

const char* txStateName(TxState state);

// 单消息发送状态机：负责尝试计数、超时判定和 ACK 匹配。
// 不负责排队，调用方一次只塞一条消息。
class OutboundTx {
 public:
  void load(const DataFrame& frame, uint32_t nowMs);
  bool active() const { return state_ == TxState::WaitingAck || state_ == TxState::Deferred; }

  // 到点该发就发出：返回 true 表示 out 里有要发送的帧。
  bool poll(uint32_t nowMs, uint8_t* out, size_t capacity, size_t& frameLength);

  // 收到一条 ACK（尚未判定是否匹配）
  void onAck(const AckFrame& ack, uint32_t nowMs);

  TxState state() const { return state_; }
  uint8_t attempt() const { return attempt_; }
  const DataFrame& frame() const { return frame_; }
  void reset();

 private:
  void scheduleNext(uint32_t nowMs);

  DataFrame frame_;
  TxState state_ = TxState::Idle;
  uint8_t attempt_ = 0;
  uint32_t deadlineMs_ = 0;
};

}  // namespace mw

#endif  // MW_PROTOCOL_H
