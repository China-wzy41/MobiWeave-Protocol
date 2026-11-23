// MobiWeave M1 联调：ACK、有限重传、去重。
//
// 两块板烧同一份，只改 MW_ROLE：0 = A（发送端，node 1），1 = B（接收端，node 2）。
// 协议核心在 mw_protocol.h/.cpp（不依赖 Arduino，可在电脑上单测）。
//
// 命令：
//   1  手动发一条消息
//   2  每 3 秒自动发一条，再按一次停止
//   0  停止发送
//   r  打印统计
//   v  开关人类可读输出（关掉后串口只剩 JSONL）
//   RUN <id>  设置实验编号并开启新日志会话

#include <Arduino.h>
#if defined(ARDUINO)
#include <esp_system.h>
#endif

#include "mw_protocol.h"

// ---------------------------------------------------------------- 配置
#define MW_ROLE   1        // 0 = A 发送端，1 = B 接收端
#define LORA_BAUD 9600     // 必须等于模块串口波特率

#define PIN_LORA_TX 17     // ESP32 TX -> 模块 RXD
#define PIN_LORA_RX 18     // ESP32 RX <- 模块 TXD
#define PIN_M0       4
#define PIN_M1       5

#define USB_BAUD   115200

static const uint8_t kNodeId = (MW_ROLE == 0) ? 1 : 2;
static const uint8_t kPeerId = (MW_ROLE == 0) ? 2 : 1;
static const uint16_t kDestination = (MW_ROLE == 0) ? 2 : 1;

// ---------------------------------------------------------------- 日志 V1
static char gRunId[65] = "unset";
static char gSessionId[65] = "s0";
static uint32_t gEventSeq = 0;
static bool gVerbose = true;

static void logEvent(const char* event, const char* result, const char* reason,
                     const char* messageIdJson, const char* detailsJson,
                     const char* channel) {
  ++gEventSeq;
  Serial.printf(
    "{\"format_version\":1,\"run_id\":\"%s\",\"source_kind\":\"REAL\","
    "\"code_version\":null,\"config_version\":null,\"strategy_version\":null,"
    "\"node_id\":%u,\"session_id\":\"%s\",\"event_seq\":%lu,\"monotonic_ms\":%lu,"
    "\"clock_basis\":\"node_session\",\"message_id\":%s,\"event\":\"%s\","
    "\"result\":\"%s\",\"reason\":%s,\"details\":%s",
    gRunId, static_cast<unsigned int>(kNodeId), gSessionId,
    static_cast<unsigned long>(gEventSeq),
    static_cast<unsigned long>(millis()),
    messageIdJson, event, result, reason, detailsJson);
  if (channel != nullptr) {
    Serial.printf(",\"channel\":\"%s\"", channel);
  }
  Serial.println("}");
}

static void midJson(char* buf, size_t cap, const mw::MessageId& id) {
  snprintf(buf, cap, "{\"source_id\":%u,\"boot_counter\":%lu,\"sequence\":%lu}",
           static_cast<unsigned int>(id.source),
           static_cast<unsigned long>(id.boot),
           static_cast<unsigned long>(id.seq));
}

static void startSession() {
#if defined(ARDUINO)
  const uint32_t salt = esp_random();
#else
  const uint32_t salt = 1;
#endif
  snprintf(gSessionId, sizeof(gSessionId), "n%u-%08lX",
           static_cast<unsigned int>(kNodeId),
           static_cast<unsigned long>(salt));
  gEventSeq = 0;
  logEvent("BOOT", "INFO", "null", "null", "{}", nullptr);
}

// ---------------------------------------------------------------- 状态
static mw::StreamParser gParser;
static mw::ReceiverCache gCache;
static mw::OutboundTx gTx;
static mw::Frame gFrame;

static uint32_t gBootCounter = 7;      // M1 固定，持久化的启动计数还没做
static uint32_t gSequence = 100;
static uint32_t gSentFrames = 0;
static uint32_t gRetries = 0;
static uint32_t gAckIn = 0;
static uint32_t gAckOut = 0;
static uint32_t gBadFrames = 0;
static uint32_t gDuplicates = 0;

static bool gAuto = false;
static uint32_t gAutoIntervalMs = 3000;
static uint32_t gLastAutoMs = 0;
static mw::TxState gLastState = mw::TxState::Idle;

// ---------------------------------------------------------------- 工具
static const char* statusName(mw::AckStatus status) {
  switch (status) {
    case mw::AckStatus::Accepted: return "ACCEPTED";
    case mw::AckStatus::AlreadyHave: return "ALREADY_HAVE";
    case mw::AckStatus::Busy: return "BUSY";
    case mw::AckStatus::Expired: return "EXPIRED";
  }
  return "UNKNOWN";
}

static void printBanner() {
  Serial.println();
  Serial.println("=== MobiWeave M1 ack test ===");
  Serial.printf("ROLE=%s node=%u peer=%u dest=%u\n",
                MW_ROLE == 0 ? "A(sender)" : "B(receiver)",
                static_cast<unsigned int>(kNodeId),
                static_cast<unsigned int>(kPeerId),
                static_cast<unsigned int>(kDestination));
  Serial.printf("LoRa=%u TX=%u RX=%u ackTimeout=%lu maxAttempts=%u cacheSlots=%u\n",
                static_cast<unsigned int>(LORA_BAUD),
                static_cast<unsigned int>(PIN_LORA_TX),
                static_cast<unsigned int>(PIN_LORA_RX),
                static_cast<unsigned long>(mw::kAckTimeoutMs),
                static_cast<unsigned int>(mw::kMaxAttempts),
                static_cast<unsigned int>(mw::kCacheSlots));
  Serial.println("命令：1 发一条，2 自动每 3 秒，0 停止，r 统计，v 纯日志，RUN <id>");
}

// ---------------------------------------------------------------- 发送侧
static void sendOneMessage() {
  if (gTx.active()) {
    if (gVerbose) {
      Serial.println("BUSY_LOCAL 上一条还没结束");
    }
    return;
  }

  mw::DataFrame f;
  f.sender = kNodeId;
  f.receiver = kPeerId;
  f.id = {kNodeId, gBootCounter, ++gSequence};
  f.destination = kDestination;
  f.priority = 1;
  f.ageMs = 0;
  f.lifetimeMs = 60000;
  f.hopCount = 1;
  f.hopLimit = 3;
  f.payloadType = 1;
  const char* text = "SOS";
  f.payloadLen = 3;
  for (size_t i = 0; i < f.payloadLen; ++i) {
    f.payload[i] = static_cast<uint8_t>(text[i]);
  }

  gTx.load(f, millis());
  gLastState = gTx.state();

  char mid[80];
  midJson(mid, sizeof(mid), f.id);
  logEvent("MESSAGE_CREATED", "OK", "null", mid,
           "{\"destination_id\":2}", nullptr);
  if (gVerbose) {
    Serial.printf("QUEUED seq=%lu\n", static_cast<unsigned long>(f.id.seq));
  }
}

static void pumpSender() {
  uint8_t wire[mw::kFrameMax];
  size_t length = 0;
  const uint32_t now = millis();

  if (gTx.poll(now, wire, sizeof(wire), length)) {
    Serial1.write(wire, length);
    ++gSentFrames;
    if (gTx.attempt() > 1) {
      ++gRetries;
    }

    char mid[80];
    char details[128];
    midJson(mid, sizeof(mid), gTx.frame().id);
    snprintf(details, sizeof(details),
             "{\"peer_id\":%u,\"attempt\":%u,\"frame_bytes\":%u,"
             "\"tx_scope\":\"local_uart_queued\"}",
             static_cast<unsigned int>(kPeerId),
             static_cast<unsigned int>(gTx.attempt()),
             static_cast<unsigned int>(length));
    logEvent("DATA_TX", "OK", "null", mid, details, "uart1");

    if (gVerbose) {
      Serial.printf("TX  seq=%lu attempt=%u len=%u\n",
                    static_cast<unsigned long>(gTx.frame().id.seq),
                    static_cast<unsigned int>(gTx.attempt()),
                    static_cast<unsigned int>(length));
    }
    if (gTx.attempt() > 1) {
      char retryDetails[96];
      snprintf(retryDetails, sizeof(retryDetails),
               "{\"peer_id\":%u,\"attempt\":%u}",
               static_cast<unsigned int>(kPeerId),
               static_cast<unsigned int>(gTx.attempt()));
      logEvent("RETRY_SCHEDULED", "RETRY", "\"ACK_TIMEOUT\"", mid, retryDetails, nullptr);
    }
    return;
  }

  // 状态跳变
  const mw::TxState state = gTx.state();
  if (state == gLastState) {
    return;
  }
  gLastState = state;

  char mid[80];
  midJson(mid, sizeof(mid), gTx.frame().id);

  if (state == mw::TxState::Done) {
    logEvent("HOP_CONFIRMED", "OK", "null", mid,
             "{\"peer_id\":2,\"ack_status\":\"ACCEPTED\"}", nullptr);
    if (gVerbose) {
      Serial.println("HOP_CONFIRMED 本跳完成");
    }
  } else if (state == mw::TxState::Failed) {
    char details[96];
    snprintf(details, sizeof(details),
             "{\"peer_id\":%u,\"attempt\":%u}",
             static_cast<unsigned int>(kPeerId),
             static_cast<unsigned int>(gTx.attempt()));
    logEvent("TRANSFER_FAILED", "FAILED", "\"RETRY_LIMIT\"", mid, details, nullptr);
    if (gVerbose) {
      Serial.println("TRANSFER_FAILED 重试用尽");
    }
  } else if (state == mw::TxState::Rejected) {
    logEvent("TRANSFER_FAILED", "FAILED", "\"EXPIRED\"", mid,
             "{\"peer_id\":2,\"attempt\":1}", nullptr);
    if (gVerbose) {
      Serial.println("REJECTED 对方判定过期");
    }
  } else if (state == mw::TxState::Deferred) {
    if (gVerbose) {
      Serial.println("DEFERRED 对方忙，稍后重试");
    }
  }
}

// ---------------------------------------------------------------- 接收侧
static void handleIncoming(const mw::Frame& frame, size_t length) {
  if (frame.type == mw::kTypeData) {
    const mw::DataFrame& d = frame.data;
    if (d.receiver != kNodeId) {
      return;   // 不是给本节点的
    }

    char mid[80];
    char details[96];
    midJson(mid, sizeof(mid), d.id);
    snprintf(details, sizeof(details), "{\"peer_id\":%u,\"frame_bytes\":%u}",
             static_cast<unsigned int>(d.sender),
             static_cast<unsigned int>(length));
    logEvent("DATA_RX", "OK", "null", mid, details, "uart1");

    const mw::AckStatus status = gCache.admit(d, millis());
    if (status == mw::AckStatus::Accepted) {
      logEvent("MESSAGE_CACHED", "OK", "null", mid, "{\"storage\":\"RAM\"}", nullptr);
    } else if (status == mw::AckStatus::AlreadyHave) {
      ++gDuplicates;
    }

    mw::AckFrame reply;
    reply.sender = kNodeId;
    reply.receiver = d.sender;
    reply.id = d.id;
    reply.status = status;

    uint8_t wire[mw::kFrameMax];
    const size_t ackLen = mw::encodeAck(reply, wire, sizeof(wire));
    if (ackLen > 0) {
      Serial1.write(wire, ackLen);
      ++gAckOut;

      char ackDetails[128];
      snprintf(ackDetails, sizeof(ackDetails),
               "{\"peer_id\":%u,\"ack_status\":\"%s\",\"frame_bytes\":%u,"
               "\"tx_scope\":\"local_uart_queued\"}",
               static_cast<unsigned int>(d.sender),
               statusName(status),
               static_cast<unsigned int>(ackLen));
      logEvent("ACK_TX", "OK", "null", mid, ackDetails, "uart1");
    }

    if (gVerbose) {
      Serial.printf("RX seq=%lu -> %s\n",
                    static_cast<unsigned long>(d.id.seq), statusName(status));
    }
    return;
  }

  // ACK
  const mw::AckFrame& a = frame.ack;
  ++gAckIn;

  char mid[80];
  char details[128];
  midJson(mid, sizeof(mid), a.id);
  snprintf(details, sizeof(details),
           "{\"peer_id\":%u,\"ack_status\":\"%s\",\"frame_bytes\":%u}",
           static_cast<unsigned int>(a.sender),
           statusName(a.status),
           static_cast<unsigned int>(length));
  logEvent("ACK_RX", "OK", "null", mid, details, "uart1");

  if (gVerbose) {
    Serial.printf("ACK seq=%lu status=%s\n",
                  static_cast<unsigned long>(a.id.seq), statusName(a.status));
  }
  gTx.onAck(a, millis());
}

static void pumpReceiver() {
  while (Serial1.available()) {
    const uint8_t byte = static_cast<uint8_t>(Serial1.read());
    mw::Frame frame;
    const size_t got = gParser.feed(&byte, 1, frame);
    if (got > 0) {
      handleIncoming(frame, got);
    } else if (gParser.lastResult() != mw::ParseResult::Ok &&
               gParser.lastResult() != mw::ParseResult::NeedMore) {
      ++gBadFrames;
      if (gVerbose) {
        Serial.printf("DROP %s pending=%u\n",
                      mw::parseResultName(gParser.lastResult()),
                      static_cast<unsigned int>(gParser.pendingBytes()));
      }
      char details[64];
      snprintf(details, sizeof(details), "{\"frame_type\":\"UNKNOWN\"}");
      logEvent("FRAME_REJECTED", "REJECTED",
               gParser.lastResult() == mw::ParseResult::BadCrc ? "\"BAD_CRC\""
                                                               : "\"BAD_LENGTH\"",
               "null", details, "uart1");
      gParser.reset();
    }
  }
}

// ---------------------------------------------------------------- 命令
static char gCmd[80];
static size_t gCmdUsed = 0;

static void handleCommand() {
  gCmd[gCmdUsed] = '\0';
  gCmdUsed = 0;
  char* cmd = gCmd;
  while (*cmd == ' ') {
    ++cmd;
  }
  if (*cmd == '\0') {
    return;
  }

  if (strncmp(cmd, "RUN ", 4) == 0) {
    char* id = cmd + 4;
    while (*id == ' ') {
      ++id;
    }
    size_t n = strlen(id);
    while (n > 0 && (id[n - 1] == ' ' || id[n - 1] == '\t')) {
      id[--n] = '\0';
    }
    if (n == 0 || n > 64) {
      Serial.println("RUN_ERR");
      return;
    }
    strncpy(gRunId, id, sizeof(gRunId) - 1);
    gRunId[sizeof(gRunId) - 1] = '\0';
    startSession();
    if (gVerbose) {
      Serial.printf("RUN_OK %s\n", gRunId);
    }
    return;
  }

  switch (cmd[0]) {
    case '1':
      gAuto = false;
      sendOneMessage();
      break;
    case '2':
      gAuto = !gAuto;
      if (gVerbose) {
        Serial.printf("AUTO %s\n", gAuto ? "ON" : "OFF");
      }
      break;
    case '0':
      gAuto = false;
      if (gVerbose) {
        Serial.println("STOP");
      }
      break;
    case 'r':
    case 'R':
      if (gVerbose) {
        Serial.printf(
          "STAT sent=%lu retries=%lu ackIn=%lu ackOut=%lu dup=%lu bad=%lu "
          "cache=%u tx=%s attempt=%u\n",
          static_cast<unsigned long>(gSentFrames),
          static_cast<unsigned long>(gRetries),
          static_cast<unsigned long>(gAckIn),
          static_cast<unsigned long>(gAckOut),
          static_cast<unsigned long>(gDuplicates),
          static_cast<unsigned long>(gBadFrames),
          static_cast<unsigned int>(gCache.count()),
          mw::txStateName(gTx.state()),
          static_cast<unsigned int>(gTx.attempt()));
      }
      break;
    case 'v':
    case 'V':
      gVerbose = !gVerbose;
      break;
    default:
      break;
  }
}

// ---------------------------------------------------------------- 入口
void setup() {
  Serial.begin(USB_BAUD);
  delay(1200);

  pinMode(PIN_M0, OUTPUT);
  pinMode(PIN_M1, OUTPUT);
  digitalWrite(PIN_M0, LOW);
  digitalWrite(PIN_M1, LOW);

  Serial1.begin(LORA_BAUD, SERIAL_8N1, PIN_LORA_RX, PIN_LORA_TX);
  delay(100);

  printBanner();
  startSession();
}

void loop() {
  pumpReceiver();

#if MW_ROLE == 0
  pumpSender();
  if (gAuto && gTx.state() != mw::TxState::WaitingAck) {
    const uint32_t now = millis();
    if (now - gLastAutoMs >= gAutoIntervalMs) {
      gLastAutoMs = now;
      sendOneMessage();
    }
  }
#endif

  while (Serial.available()) {
    const int raw = Serial.read();
    if (raw == '\n' || raw == '\r') {
      handleCommand();
      continue;
    }
    if (gCmdUsed + 1 < sizeof(gCmd)) {
      gCmd[gCmdUsed++] = static_cast<char>(raw);
    }
  }
}
