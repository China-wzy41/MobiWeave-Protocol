// MobiWeave 空口联调草图（第一版，未在实机验证）
//
// 全仓库只有这一个文件需要烧录。两块板烧同一份，只改 MW_ROLE：
//   MW_ROLE 0 = A 发送端
//   MW_ROLE 1 = B 接收端
//
// 烧录一次之后，用串口监视器发单字符切换阶段，不用重新上传：
//   1 = 裸透传（不谈协议，只验链路）
//   2 = 协议帧（发文档第六节的 39 字节 SOS 帧）
//   3 = 长度扫描（整帧 36..168 字节，测模块单包上限）
//   r = 打印统计
//   t = 再打印一次样例帧
//   v = 开关人类可读输出（关掉后串口只剩 JSONL，方便上位机抓包）
//   RUN <id> = 设置本次实验编号，同时开一个新日志会话
//
// 上电默认阶段由 MW_STAGE 决定，两块板设成同一个即可。

#include <Arduino.h>
#if defined(ARDUINO)
#include <esp_system.h>   // esp_random()，用来生成每次启动唯一的 session_id
#endif

// ---------------------------------------------------------------- 需要你改的
#define MW_ROLE   0        // 0 = A 发送端，1 = B 接收端

// 上电默认阶段，运行中可以按 1/2/3 覆盖。
// 1 = 裸透传，2 = 协议帧，3 = 长度扫描
#define MW_STAGE  1

// 必须和模块里配置的串口波特率一致。出厂常见是 9600，不是 115200。
#define LORA_BAUD 9600

// 按实际接线改。避开 GPIO0/3/45/46（strapping）与 GPIO19/20（USB）。
#define PIN_LORA_TX 17     // ESP32 的 TX -> 模块 RXD
#define PIN_LORA_RX 18     // ESP32 的 RX <- 模块 TXD
#define PIN_M0       4     // 模块没有 M0/M1 时这两根线空着，无副作用
#define PIN_M1       5

#define USB_BAUD   115200

// ---------------------------------------------------------------- 公共
static uint8_t gStage = MW_STAGE;

// ---------------------------------------------------------------- 日志 V1
// 现场只实现四个事件：BOOT、DATA_TX、DATA_RX、FRAME_REJECTED。
// 其余事件（ACK、重传、缓存、转发、过期、链路）等协议实现写出来再加。
// 人类可读行和 JSONL 共用 USB 串口；按 v 可以只留 JSONL。
static const uint8_t kNodeId = (MW_ROLE == 0) ? 1 : 2;
static char gRunId[65] = "unset";
static char gSessionId[65] = "s0";
static uint32_t gEventSeq = 0;
static bool gVerbose = true;

static void logEvent(const char* event, const char* result, const char* reason,
                     const char* messageIdJson, const char* detailsJson,
                     const char* channelOrNull) {
  ++gEventSeq;
  Serial.printf(
    "{\"format_version\":1,\"run_id\":\"%s\",\"source_kind\":\"REAL\","
    "\"code_version\":null,\"config_version\":null,\"strategy_version\":null,"
    "\"node_id\":%u,\"session_id\":\"%s\",\"event_seq\":%lu,\"monotonic_ms\":%lu,"
    "\"clock_basis\":\"node_session\",\"message_id\":%s,\"event\":\"%s\","
    "\"result\":\"%s\",\"reason\":%s,\"details\":%s",
    gRunId,
    static_cast<unsigned int>(kNodeId),
    gSessionId,
    static_cast<unsigned long>(gEventSeq),
    static_cast<unsigned long>(millis()),
    messageIdJson, event, result, reason, detailsJson);
  if (channelOrNull != nullptr) {
    Serial.printf(",\"channel\":\"%s\"", channelOrNull);
  }
  Serial.println("}");
}

// 生成 message_id 的 JSON 片段，返回传入缓冲区。
static const char* messageIdJson(char* buffer, size_t capacity,
                                 unsigned int sourceId, unsigned long bootCounter,
                                 unsigned long sequence) {
  snprintf(buffer, capacity,
           "{\"source_id\":%u,\"boot_counter\":%lu,\"sequence\":%lu}",
           sourceId, bootCounter, sequence);
  return buffer;
}

// 开一个新日志会话：换 session_id，event_seq 归零，重新记 BOOT。
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

static void printHex(const uint8_t* data, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    Serial.printf("%02X", static_cast<unsigned int>(data[i]));
    Serial.print(i + 1 == length ? '\n' : ' ');
  }
}

static const char* roleName() {
  return MW_ROLE == 0 ? "A(sender)" : "B(receiver)";
}

static const char* stageName(uint8_t stage) {
  switch (stage) {
    case 1: return "raw-ping";
    case 2: return "protocol-frame";
    case 3: return "length-sweep";
    default: return "unknown";
  }
}

// protocol-v1.md 第六节的样例，逐字节抄下来。改文档必须同步改这里。
static const uint8_t SOS_FRAME[] = {
  0xA5, 0x5A, 0x01, 0x01, 0x1F, 0x00,
  0x01, 0x00, 0x02, 0x00, 0x01, 0x00,
  0x03, 0x00, 0x07, 0x00, 0x00, 0x00,
  0x0C, 0x00, 0x00, 0x00, 0x02, 0x00,
  0x00, 0x00, 0x00, 0x60, 0xEA, 0x00,
  0x00, 0x01, 0x03, 0x01, 0x53, 0x4F,
  0x53, 0xBA, 0xD0
};

// ---------------------------------------------------------------- 编码
static uint16_t crc16(const uint8_t* data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x8000)
              ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
              : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

static void put16(uint8_t* buf, size_t& pos, uint16_t value) {
  buf[pos++] = value & 0xFF;
  buf[pos++] = (value >> 8) & 0xFF;
}

static void put32(uint8_t* buf, size_t& pos, uint32_t value) {
  for (uint8_t i = 0; i < 4; ++i) {
    buf[pos++] = (value >> (8 * i)) & 0xFF;
  }
}

static uint16_t get16(const uint8_t* buf) {
  return static_cast<uint16_t>(buf[0]) |
         (static_cast<uint16_t>(buf[1]) << 8);
}

static uint32_t get32(const uint8_t* buf) {
  return static_cast<uint32_t>(buf[0]) |
         (static_cast<uint32_t>(buf[1]) << 8) |
         (static_cast<uint32_t>(buf[2]) << 16) |
         (static_cast<uint32_t>(buf[3]) << 24);
}

// 生成一条 DATA 帧，载荷用可读字符填充，方便在 hex 里看边界。
static size_t buildDataFrame(uint8_t* out, size_t capacity,
                             uint32_t sequence, size_t payloadLength) {
  const size_t bodyLength = 28 + payloadLength;
  const size_t frameLength = 8 + bodyLength;
  if (capacity < frameLength || payloadLength > 132) {
    return 0;
  }

  size_t pos = 0;
  out[pos++] = 0xA5;
  out[pos++] = 0x5A;
  out[pos++] = 1;   // version
  out[pos++] = 1;   // DATA
  put16(out, pos, static_cast<uint16_t>(bodyLength));

  put16(out, pos, 1);        // sender_id
  put16(out, pos, 2);        // receiver_id
  put16(out, pos, 1);        // source_id
  put16(out, pos, 3);        // destination_id
  put32(out, pos, 7);        // boot_counter
  put32(out, pos, sequence);
  out[pos++] = 2;            // priority
  put32(out, pos, 0);        // age_ms
  put32(out, pos, 60000);    // lifetime_ms
  out[pos++] = 1;            // hop_count
  out[pos++] = 3;            // hop_limit
  out[pos++] = 1;            // payload_type

  for (size_t i = 0; i < payloadLength; ++i) {
    out[pos++] = static_cast<uint8_t>('a' + (i % 26));
  }

  put16(out, pos, crc16(out + 2, pos - 2));
  return pos;
}

// ---------------------------------------------------------------- 接收端
static uint8_t rxBuffer[176];
static size_t rxUsed = 0;
static uint32_t rxFrameCount = 0;
static uint32_t rxByteCount = 0;
static uint32_t rxBadCrc = 0;
static uint32_t rxCrcOk = 0;
static uint32_t lastByteMs = 0;

static void printFrame(const uint8_t* frame, size_t length) {
  const uint8_t* body = frame + 6;

  if (frame[3] == 1) {
    const size_t payloadLength = get16(frame + 4) - 28;

    char mid[80];
    char details[96];
    messageIdJson(mid, sizeof(mid),
                  get16(body + 4),              // source_id
                  get32(body + 8),              // boot_counter
                  get32(body + 12));            // sequence
    snprintf(details, sizeof(details),
             "{\"peer_id\":%u,\"frame_bytes\":%u}",
             static_cast<unsigned int>(get16(body)),          // 本跳发送者
             static_cast<unsigned int>(length));
    logEvent("DATA_RX", "OK", "null", mid, details, "uart1");

    if (!gVerbose) {
      return;
    }
    Serial.printf("RX  %u bytes: ", static_cast<unsigned int>(length));
    printHex(frame, length);
    Serial.printf(
      "    DATA sender=%u receiver=%u source=%u dest=%u\n",
      static_cast<unsigned int>(get16(body)),
      static_cast<unsigned int>(get16(body + 2)),
      static_cast<unsigned int>(get16(body + 4)),
      static_cast<unsigned int>(get16(body + 6)));
    Serial.printf(
      "         boot=%lu sequence=%lu pri=%u age=%lu life=%lu hop=%u/%u "
      "type=%u payloadLen=%u\n",
      static_cast<unsigned long>(get32(body + 8)),
      static_cast<unsigned long>(get32(body + 12)),
      static_cast<unsigned int>(body[16]),
      static_cast<unsigned long>(get32(body + 17)),
      static_cast<unsigned long>(get32(body + 21)),
      static_cast<unsigned int>(body[25]),
      static_cast<unsigned int>(body[26]),
      static_cast<unsigned int>(body[27]),
      static_cast<unsigned int>(payloadLength));
  } else {
    // ACK 正文：sender(2) receiver(2) source(2) boot(4) sequence(4) status(1)。
    // boot 在偏移 6、sequence 在 10，和 DATA 的 8/12 不同，别照抄。
    if (!gVerbose) {
      return;
    }
    Serial.printf("RX  %u bytes: ", static_cast<unsigned int>(length));
    printHex(frame, length);
    Serial.printf(
      "    ACK  sender=%u receiver=%u source=%u boot=%lu sequence=%lu status=%u\n",
      static_cast<unsigned int>(get16(body)),
      static_cast<unsigned int>(get16(body + 2)),
      static_cast<unsigned int>(get16(body + 4)),
      static_cast<unsigned long>(get32(body + 6)),
      static_cast<unsigned long>(get32(body + 10)),
      static_cast<unsigned int>(body[14]));
  }

  if (gStage == 2) {
    const bool matches = (length == sizeof(SOS_FRAME)) &&
                         (memcmp(frame, SOS_FRAME, sizeof(SOS_FRAME)) == 0);
    Serial.printf("    %s\n", matches ? "MATCH doc sample" : "DIFF from doc sample");
  }
}

static void flushRawLine() {
  if (rxUsed == 0) {
    return;
  }
  if (gVerbose) {
    Serial.printf("RX  %u bytes: ", static_cast<unsigned int>(rxUsed));
    printHex(rxBuffer, rxUsed);
    Serial.print("    text=\"");
    for (size_t i = 0; i < rxUsed; ++i) {
      const char c = static_cast<char>(rxBuffer[i]);
      Serial.print((c == '\r' || c == '\n') ? ' ' : c);
    }
    Serial.println("\"");
  }
  rxUsed = 0;
}

static void processRx() {
  while (true) {
    while (rxUsed > 0 && rxBuffer[0] != 0xA5) {
      memmove(rxBuffer, rxBuffer + 1, --rxUsed);
    }
    if (rxUsed < 2) {
      return;
    }
    if (rxBuffer[1] != 0x5A) {
      memmove(rxBuffer, rxBuffer + 1, --rxUsed);
      continue;
    }
    if (rxUsed < 6) {
      return;
    }

    const uint8_t version = rxBuffer[2];
    const uint8_t type = rxBuffer[3];
    const uint16_t bodyLength = get16(rxBuffer + 4);

    const bool headerOk =
      version == 1 && (type == 1 || type == 2) &&
      ((type == 1 && bodyLength >= 28 && bodyLength <= 160) ||
       (type == 2 && bodyLength == 15));

    if (!headerOk) {
      const char* reasonCode = "\"BAD_LENGTH\"";
      if (version != 1) {
        reasonCode = "\"UNSUPPORTED_VERSION\"";
      } else if (type != 1 && type != 2) {
        reasonCode = "\"UNSUPPORTED_TYPE\"";
      }
      const char* frameType = (type == 1) ? "DATA" : ((type == 2) ? "ACK" : "UNKNOWN");
      char details[48];
      snprintf(details, sizeof(details), "{\"frame_type\":\"%s\"}", frameType);
      logEvent("FRAME_REJECTED", "REJECTED", reasonCode, "null", details, "uart1");

      if (gVerbose) {
        Serial.printf("DROP  header v=%u type=%u len=%u\n",
                      static_cast<unsigned int>(version),
                      static_cast<unsigned int>(type),
                      static_cast<unsigned int>(bodyLength));
      }
      memmove(rxBuffer, rxBuffer + 1, --rxUsed);
      continue;
    }

    const size_t total = 8u + bodyLength;
    if (rxUsed < total) {
      return;   // 半帧，等后续字节
    }

    const uint16_t got = get16(rxBuffer + total - 2);
    const uint16_t want = crc16(rxBuffer + 2, total - 4);

    if (got != want) {
      ++rxBadCrc;
      char details[48];
      snprintf(details, sizeof(details), "{\"frame_type\":\"%s\"}",
               (type == 1) ? "DATA" : "ACK");
      logEvent("FRAME_REJECTED", "REJECTED", "\"BAD_CRC\"", "null", details, "uart1");

      if (gVerbose) {
        Serial.printf("DROP  crc got=%04X want=%04X\n",
                      static_cast<unsigned int>(got),
                      static_cast<unsigned int>(want));
      }
      memmove(rxBuffer, rxBuffer + 1, --rxUsed);
      continue;
    }

    ++rxCrcOk;
    ++rxFrameCount;
    printFrame(rxBuffer, total);
    memmove(rxBuffer, rxBuffer + total, rxUsed - total);
    rxUsed -= total;
  }
}

// ---------------------------------------------------------------- 发送端
static uint32_t lastSendMs = 0;
static uint32_t sendCounter = 0;

// 阶段 1：纯文本，用来排除接线和模块配置问题。
static void sendRawPing() {
  char text[24];
  const int n = snprintf(text, sizeof(text), "PING %lu\n",
                         static_cast<unsigned long>(++sendCounter));
  if (n <= 0) {
    return;
  }
  Serial1.write(reinterpret_cast<const uint8_t*>(text),
                static_cast<size_t>(n));
  if (gVerbose) {
    Serial.printf("TX  %d bytes: ", n);
    printHex(reinterpret_cast<const uint8_t*>(text), static_cast<size_t>(n));
  }
}

// 阶段 2：文档里那条 39 字节 SOS 帧。
static void sendDocFrame() {
  Serial1.write(SOS_FRAME, sizeof(SOS_FRAME));

  char mid[80];
  char details[112];
  messageIdJson(mid, sizeof(mid), 1, 7, 12);   // 样例帧的固定编号
  snprintf(details, sizeof(details),
           "{\"peer_id\":2,\"attempt\":1,\"frame_bytes\":%u,"
           "\"tx_scope\":\"local_uart_queued\"}",
           static_cast<unsigned int>(sizeof(SOS_FRAME)));
  logEvent("DATA_TX", "OK", "null", mid, details, "uart1");

  if (gVerbose) {
    Serial.printf("TX  %u bytes: ", static_cast<unsigned int>(sizeof(SOS_FRAME)));
    printHex(SOS_FRAME, sizeof(SOS_FRAME));
  }
}

// 阶段 3：载荷 0,12,...,132，对应整帧 36..168，每个长度发一次。
static void sendSweep() {
  const size_t payloadLength = (sendCounter % 12) * 12;
  uint8_t frame[168];
  const size_t length = buildDataFrame(frame, sizeof(frame),
                                       sendCounter + 1, payloadLength);
  if (length > 0) {
    Serial1.write(frame, length);

    char mid[80];
    char details[112];
    messageIdJson(mid, sizeof(mid), 1, 7,
                  static_cast<unsigned long>(sendCounter + 1));
    snprintf(details, sizeof(details),
             "{\"peer_id\":2,\"attempt\":1,\"frame_bytes\":%u,"
             "\"tx_scope\":\"local_uart_queued\"}",
             static_cast<unsigned int>(length));
    logEvent("DATA_TX", "OK", "null", mid, details, "uart1");

    if (gVerbose) {
      Serial.printf("TX  %u bytes (payload %u)\n",
                    static_cast<unsigned int>(length),
                    static_cast<unsigned int>(payloadLength));
    }
  }
  ++sendCounter;
}

// ---------------------------------------------------------------- 入口
static void printBanner() {
  Serial.println();
  Serial.println("=== MobiWeave link test ===");
  Serial.printf("ROLE=%s  STAGE=%u(%s)\n",
                roleName(),
                static_cast<unsigned int>(gStage),
                stageName(gStage));
  Serial.printf("USB=%u LoRa=%u TX=%u RX=%u M0=%u M1=%u\n",
                static_cast<unsigned int>(USB_BAUD),
                static_cast<unsigned int>(LORA_BAUD),
                static_cast<unsigned int>(PIN_LORA_TX),
                static_cast<unsigned int>(PIN_LORA_RX),
                static_cast<unsigned int>(PIN_M0),
                static_cast<unsigned int>(PIN_M1));
  Serial.print("DOC SAMPLE: ");
  printHex(SOS_FRAME, sizeof(SOS_FRAME));
  Serial.println("命令：1/2/3 切阶段，r 统计，t 样例，v 只留 JSONL，RUN <id> 设定实验编号");
}

// ---------------------------------------------------------------- 串口命令
static char gCmdBuf[80];
static size_t gCmdUsed = 0;

static bool validRunId(const char* id) {
  const size_t length = strlen(id);
  if (length < 1 || length > 64) {
    return false;
  }
  for (size_t i = 0; i < length; ++i) {
    const char c = id[i];
    const bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                    (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
    if (!ok) {
      return false;
    }
  }
  return true;
}

static void handleCommand() {
  gCmdBuf[gCmdUsed] = '\0';
  gCmdUsed = 0;

  char* cmd = gCmdBuf;
  while (*cmd == ' ' || *cmd == '\t') {
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
    size_t length = strlen(id);
    while (length > 0 && (id[length - 1] == ' ' || id[length - 1] == '\t')) {
      id[--length] = '\0';
    }
    if (!validRunId(id)) {
      Serial.println("RUN_ERR invalid run_id");
      return;
    }
    strncpy(gRunId, id, sizeof(gRunId) - 1);
    gRunId[sizeof(gRunId) - 1] = '\0';
    startSession();   // 换 run 就换会话，event_seq 从 1 重新开始
    if (gVerbose) {
      Serial.printf("RUN_OK %s\n", gRunId);
    }
    return;
  }

  const char c = cmd[0];
  if (c >= '1' && c <= '3') {
    gStage = static_cast<uint8_t>(c - '0');
    rxUsed = 0;   // 切阶段时丢掉残留，避免把旧半帧当成新数据
    sendCounter = 0;
    if (gVerbose) {
      Serial.printf("STAGE -> %u(%s)\n",
                    static_cast<unsigned int>(gStage),
                    stageName(gStage));
    }
  } else if (c == 'r' || c == 'R') {
    if (gVerbose) {
      Serial.printf("STAT stage=%u bytes=%lu frames=%lu crcOk=%lu badCrc=%lu pending=%u\n",
                    static_cast<unsigned int>(gStage),
                    static_cast<unsigned long>(rxByteCount),
                    static_cast<unsigned long>(rxFrameCount),
                    static_cast<unsigned long>(rxCrcOk),
                    static_cast<unsigned long>(rxBadCrc),
                    static_cast<unsigned int>(rxUsed));
    }
  } else if (c == 't' || c == 'T') {
    if (gVerbose) {
      Serial.print("SOS_FRAME: ");
      printHex(SOS_FRAME, sizeof(SOS_FRAME));
    }
  } else if (c == 'v' || c == 'V') {
    gVerbose = !gVerbose;
    if (gVerbose) {
      Serial.println("VERBOSE ON （人类可读行已打开）");
    }
  }
}

void setup() {
  Serial.begin(USB_BAUD);
  delay(1200);   // 等 USB CDC 枚举，否则前几行会丢

  pinMode(PIN_M0, OUTPUT);
  pinMode(PIN_M1, OUTPUT);
  digitalWrite(PIN_M0, LOW);   // 透传收发模式，若模块定义不同按手册改
  digitalWrite(PIN_M1, LOW);

  Serial1.begin(LORA_BAUD, SERIAL_8N1, PIN_LORA_RX, PIN_LORA_TX);
  delay(100);

  printBanner();
  startSession();
}

void loop() {
  // ---------------- 接收端 ----------------
#if MW_ROLE == 1
  while (Serial1.available()) {
    const uint8_t byte = static_cast<uint8_t>(Serial1.read());
    ++rxByteCount;
    lastByteMs = millis();

    if (gStage == 1) {
      if (rxUsed < sizeof(rxBuffer)) {
        rxBuffer[rxUsed++] = byte;
      } else {
        flushRawLine();
      }
      if (byte == '\n' || rxUsed >= 32) {
        flushRawLine();
      }
    } else {
      if (rxUsed == sizeof(rxBuffer)) {
        memmove(rxBuffer, rxBuffer + 1, --rxUsed);
      }
      rxBuffer[rxUsed++] = byte;
      processRx();
    }
  }

  // 阶段 1 里行没结束但已经停了 300ms，也打出来。
  if (gStage == 1 && rxUsed > 0 && (millis() - lastByteMs) > 300) {
    flushRawLine();
  }
#endif

  // ---------------- 发送端 ----------------
#if MW_ROLE == 0
  const uint32_t now = millis();
  if (now - lastSendMs >= 1000) {
    lastSendMs = now;
    if (gStage == 1) {
      sendRawPing();
    } else if (gStage == 2) {
      sendDocFrame();
    } else if (gStage == 3) {
      sendSweep();
    }
  }
#endif

  // ---------------- 串口命令 ----------------
  // 逐字符收，遇到回车/换行整行处理；支持 RUN <id> 这种带参数的命令。
  while (Serial.available()) {
    const int raw = Serial.read();
    if (raw == '\n' || raw == '\r') {
      handleCommand();
      continue;
    }
    if (gCmdUsed + 1 < sizeof(gCmdBuf)) {
      gCmdBuf[gCmdUsed++] = static_cast<char>(raw);
    }
  }
}
