#include <Arduino.h>

// CRC-16/IBM-3740，也称 CRC-16/CCITT-FALSE。
// poly=0x1021, init=0xFFFF,
// refin=false, refout=false, xorout=0x0000。
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

void checkCrc(const char* name,
              const uint8_t* data,
              size_t length,
              uint16_t expected) {
  uint16_t actual = crc16(data, length);

  Serial.printf(
    "%s: actual=0x%04X expected=0x%04X %s\n",
    name,
    static_cast<unsigned int>(actual),
    static_cast<unsigned int>(expected),
    actual == expected ? "PASS" : "FAIL"
  );
}

void runTests() {
  // 标准算法测试，不包括字符串结尾的零字节。
  const uint8_t reference[] = {
    '1', '2', '3', '4', '5', '6', '7', '8', '9'
  };

  // 完整 DATA 帧，包含帧头和 CRC。
  const uint8_t dataFrame[] = {
    0xA5, 0x5A, 0x01, 0x01, 0x1F, 0x00,
    0x01, 0x00, 0x02, 0x00, 0x01, 0x00,
    0x03, 0x00, 0x07, 0x00, 0x00, 0x00,
    0x0C, 0x00, 0x00, 0x00, 0x02, 0x00,
    0x00, 0x00, 0x00, 0x60, 0xEA, 0x00,
    0x00, 0x01, 0x03, 0x01, 0x53, 0x4F,
    0x53, 0xBA, 0xD0
  };

  const uint8_t ackFrame[] = {
    0xA5, 0x5A, 0x01, 0x02, 0x0F, 0x00,
    0x02, 0x00, 0x01, 0x00, 0x01, 0x00,
    0x07, 0x00, 0x00, 0x00, 0x0C, 0x00,
    0x00, 0x00, 0x00, 0xF0, 0x82
  };

  Serial.println("\n=== MobiWeave CRC tests ===");

  checkCrc("REFERENCE", reference, sizeof(reference), 0x29B1);

  // 跳过前两个帧头字节；
  // 长度减去帧头 2 字节和末尾 CRC 2 字节。
  checkCrc(
    "DATA",
    dataFrame + 2,
    sizeof(dataFrame) - 4,
    0xD0BA
  );

  checkCrc(
    "ACK",
    ackFrame + 2,
    sizeof(ackFrame) - 4,
    0x82F0
  );

  // 将 SOS 改成 SOT，检查原 CRC 能否发现变化。
  uint8_t damagedFrame[sizeof(dataFrame)];
  memcpy(damagedFrame, dataFrame, sizeof(dataFrame));
  damagedFrame[36] = 0x54;

  uint16_t damagedCrc = crc16(
    damagedFrame + 2,
    sizeof(damagedFrame) - 4
  );

  Serial.printf(
    "CORRUPTED: %s\n",
    damagedCrc != 0xD0BA ? "PASS" : "FAIL"
  );

  Serial.println("Send t to run again.");
}
// 按小端序写入整数，并移动写入位置。
void writeU16(uint8_t* buffer, size_t& pos, uint16_t value) {
  buffer[pos++] = value & 0xFF;
  buffer[pos++] = (value >> 8) & 0xFF;
}

void writeU32(uint8_t* buffer, size_t& pos, uint32_t value) {
  for (uint8_t i = 0; i < 4; ++i) {
    buffer[pos++] = (value >> (8 * i)) & 0xFF;
  }
}

// 生成固定测试消息，不代表正式发送接口。
// 返回生成的字节数；空间不足时返回 0。
size_t encodeSosTest(uint8_t* output, size_t capacity) {
  const uint8_t payload[] = {'S', 'O', 'S'};

  const uint16_t bodyLength = 28 + sizeof(payload);
  const size_t frameLength = 8 + bodyLength;

  if (output == nullptr || capacity < frameLength) {
    return 0;
  }

  size_t pos = 0;

  // 公共帧头。
  output[pos++] = 0xA5;
  output[pos++] = 0x5A;
  output[pos++] = 1;  // version
  output[pos++] = 1;  // DATA
  writeU16(output, pos, bodyLength);

  // DATA 正文。
  writeU16(output, pos, 1);      // sender_id
  writeU16(output, pos, 2);      // receiver_id
  writeU16(output, pos, 1);      // source_id
  writeU16(output, pos, 3);      // destination_id
  writeU32(output, pos, 7);      // boot_counter
  writeU32(output, pos, 12);     // sequence
  output[pos++] = 2;            // priority
  writeU32(output, pos, 0);      // age_ms，固定测试值
  writeU32(output, pos, 60000);  // lifetime_ms
  output[pos++] = 1;            // hop_count
  output[pos++] = 3;            // hop_limit
  output[pos++] = 1;            // payload_type：UTF-8

  for (size_t i = 0; i < sizeof(payload); ++i) {
    output[pos++] = payload[i];
  }

  // 从 version 开始计算，排除帧头。
  uint16_t checksum = crc16(output + 2, pos - 2);
  writeU16(output, pos, checksum);

  return pos;
}

void runEncodeTest() {
  const uint8_t expected[] = {
    0xA5, 0x5A, 0x01, 0x01, 0x1F, 0x00,
    0x01, 0x00, 0x02, 0x00, 0x01, 0x00,
    0x03, 0x00, 0x07, 0x00, 0x00, 0x00,
    0x0C, 0x00, 0x00, 0x00, 0x02, 0x00,
    0x00, 0x00, 0x00, 0x60, 0xEA, 0x00,
    0x00, 0x01, 0x03, 0x01, 0x53, 0x4F,
    0x53, 0xBA, 0xD0
  };

  uint8_t actual[168] = {};
  size_t length = encodeSosTest(actual, sizeof(actual));

  Serial.println("\n=== DATA encode test ===");
  Serial.printf("Frame length: %u\n",
                static_cast<unsigned int>(length));

  for (size_t i = 0; i < length; ++i) {
    Serial.printf("%02X ", static_cast<unsigned int>(actual[i]));
  }
  Serial.println();

  bool matches =
    length == sizeof(expected) &&
    memcmp(actual, expected, sizeof(expected)) == 0;

  Serial.printf("ENCODE: %s\n", matches ? "PASS" : "FAIL");

  // 空间不足时必须拒绝，避免越界写入。
  uint8_t smallBuffer[10] = {};
  bool rejected =
    encodeSosTest(smallBuffer, sizeof(smallBuffer)) == 0;

  Serial.printf("SMALL_BUFFER: %s\n",
                rejected ? "PASS" : "FAIL");
}
uint16_t readU16(const uint8_t* data) {
  return static_cast<uint16_t>(data[0]) |
         (static_cast<uint16_t>(data[1]) << 8);
}

uint32_t readU32(const uint8_t* data) {
  return static_cast<uint32_t>(data[0]) |
         (static_cast<uint32_t>(data[1]) << 8) |
         (static_cast<uint32_t>(data[2]) << 16) |
         (static_cast<uint32_t>(data[3]) << 24);
}

// 这里只检查完整 DATA 帧的结构与 CRC，并打印字段。
// 暂不实现缓存、ACK、去重或全部业务合法性检查。
bool decodeDataFrame(const uint8_t* frame, size_t length) {
  if (frame == nullptr || length < 8) {
    Serial.println("REJECT: too short");
    return false;
  }

  if (frame[0] != 0xA5 || frame[1] != 0x5A) {
    Serial.println("REJECT: bad magic");
    return false;
  }

  if (frame[2] != 1 || frame[3] != 1) {
    Serial.println("REJECT: unsupported version/type");
    return false;
  }

  uint16_t bodyLength = readU16(frame + 4);

  if (bodyLength < 28 || bodyLength > 160) {
    Serial.println("REJECT: invalid body length");
    return false;
  }

  if (length != static_cast<size_t>(bodyLength) + 8) {
    Serial.println("REJECT: frame length mismatch");
    return false;
  }

  uint16_t receivedCrc = readU16(frame + length - 2);
  uint16_t calculatedCrc = crc16(frame + 2, length - 4);

  if (receivedCrc != calculatedCrc) {
    Serial.println("REJECT: bad CRC");
    return false;
  }

  const uint8_t* body = frame + 6;
  size_t payloadLength = bodyLength - 28;

  Serial.printf(
    "sender=%u receiver=%u source=%u destination=%u\n",
    static_cast<unsigned int>(readU16(body)),
    static_cast<unsigned int>(readU16(body + 2)),
    static_cast<unsigned int>(readU16(body + 4)),
    static_cast<unsigned int>(readU16(body + 6))
  );

  Serial.printf(
    "boot=%lu sequence=%lu priority=%u\n",
    static_cast<unsigned long>(readU32(body + 8)),
    static_cast<unsigned long>(readU32(body + 12)),
    static_cast<unsigned int>(body[16])
  );

  Serial.printf(
    "age_ms=%lu lifetime_ms=%lu hop=%u/%u type=%u\n",
    static_cast<unsigned long>(readU32(body + 17)),
    static_cast<unsigned long>(readU32(body + 21)),
    static_cast<unsigned int>(body[25]),
    static_cast<unsigned int>(body[26]),
    static_cast<unsigned int>(body[27])
  );

  // 指定长度输出，不依赖字符串结尾零字节。
  Serial.print("payload=");
  Serial.write(body + 28, payloadLength);
  Serial.println();

  return true;
}

void runDecodeTest() {
  uint8_t frame[168] = {};
  size_t length = encodeSosTest(frame, sizeof(frame));

  Serial.println("\n=== DATA decode tests ===");

  if (length != 39) {
    Serial.println("SETUP: FAIL");
    return;
  }

  bool normalAccepted = decodeDataFrame(frame, length);
  Serial.printf("DECODE: %s\n",
                normalAccepted ? "PASS" : "FAIL");

  // 正文变了，但不更新 CRC，应拒绝。
  frame[36] ^= 0x01;
  bool corruptRejected = !decodeDataFrame(frame, length);
  Serial.printf("BAD_CRC: %s\n",
                corruptRejected ? "PASS" : "FAIL");

  // 恢复原字节。
  frame[36] ^= 0x01;

  // 少输入一个字节，应拒绝。
  bool truncatedRejected = !decodeDataFrame(frame, length - 1);
  Serial.printf("TRUNCATED: %s\n",
                truncatedRejected ? "PASS" : "FAIL");

  // 声明正文长度为 161，超过上限，应拒绝。
  frame[4] = 0xA1;
  frame[5] = 0x00;

  bool oversizedRejected = !decodeDataFrame(frame, length);
  Serial.printf("OVERSIZED: %s\n",
                oversizedRejected ? "PASS" : "FAIL");
}
// 当前只解析 DATA。
// 168 = 公共外壳 8 字节 + 最大正文 160 字节。
uint8_t streamBuffer[168];
size_t streamUsed = 0;
unsigned int streamAccepted = 0;

void resetStream() {
  streamUsed = 0;
  streamAccepted = 0;
}

// 删除缓冲区开头的 count 个字节。
void dropStreamBytes(size_t count) {
  if (count >= streamUsed) {
    streamUsed = 0;
    return;
  }

  memmove(streamBuffer,
          streamBuffer + count,
          streamUsed - count);

  streamUsed -= count;
}

void processStreamBuffer() {
  while (true) {
    // 搜索帧头；保留末尾可能成为下一帧开头的 A5。
    while (streamUsed > 0) {
      if (streamBuffer[0] != 0xA5) {
        dropStreamBytes(1);
        continue;
      }

      if (streamUsed == 1) {
        return;
      }

      if (streamBuffer[1] == 0x5A) {
        break;
      }

      dropStreamBytes(1);
    }

    // 固定头部需要 6 字节。
    if (streamUsed < 6) {
      return;
    }

    uint16_t bodyLength = readU16(streamBuffer + 4);

    // 当前版本只接受 version=1、DATA=1。
    bool headerValid =
      streamBuffer[2] == 1 &&
      streamBuffer[3] == 1 &&
      bodyLength >= 28 &&
      bodyLength <= 160;

    if (!headerValid) {
      dropStreamBytes(1);
      continue;
    }

    size_t totalLength = 8 + bodyLength;

    // 半帧：保留数据，等待后续字节。
    if (streamUsed < totalLength) {
      return;
    }

    uint16_t receivedCrc =
      readU16(streamBuffer + totalLength - 2);

    uint16_t calculatedCrc =
      crc16(streamBuffer + 2, totalLength - 4);

    if (receivedCrc != calculatedCrc) {
      // 只跳过候选帧起点，重新搜索后续帧头。
      dropStreamBytes(1);
      continue;
    }

    if (decodeDataFrame(streamBuffer, totalLength)) {
      ++streamAccepted;
    }

    dropStreamBytes(totalLength);
  }
}

// 将一段数据按字节交给解析器。
void feedStream(const uint8_t* data, size_t length) {
  if (data == nullptr) {
    return;
  }

  for (size_t i = 0; i < length; ++i) {
    // 防御性容量检查，避免越界。
    if (streamUsed == sizeof(streamBuffer)) {
      dropStreamBytes(1);
    }

    streamBuffer[streamUsed++] = data[i];
    processStreamBuffer();
  }
}

void printStreamResult(const char* name, bool passed) {
  Serial.printf("%s: %s\n", name, passed ? "PASS" : "FAIL");
}

void runStreamTests() {
  uint8_t frame[168] = {};
  size_t length = encodeSosTest(frame, sizeof(frame));

  Serial.println("\n=== DATA stream tests ===");

  if (length != 39) {
    Serial.println("SETUP: FAIL");
    return;
  }

  // 测试1：半帧不能提前输出。
  resetStream();
  feedStream(frame, 10);

  bool noEarlyOutput =
    streamAccepted == 0 && streamUsed == 10;

  feedStream(frame + 10, length - 10);

  printStreamResult(
    "SPLIT_FRAME",
    noEarlyOutput &&
    streamAccepted == 1 &&
    streamUsed == 0
  );

  // 测试2：两帧放进同一段输入。
  uint8_t twoFrames[78];
  memcpy(twoFrames, frame, length);
  memcpy(twoFrames + length, frame, length);

  resetStream();
  feedStream(twoFrames, sizeof(twoFrames));

  printStreamResult(
    "TWO_FRAMES",
    streamAccepted == 2 && streamUsed == 0
  );

  // 测试3：逐字节输入。
  resetStream();

  for (size_t i = 0; i < length; ++i) {
    feedStream(frame + i, 1);
  }

  printStreamResult(
    "BYTE_BY_BYTE",
    streamAccepted == 1 && streamUsed == 0
  );

  // 测试4：杂乱数据后接正常帧。
  // 末尾 A5 与正常帧开头 A5 相邻，
  // 检查解析器能否找到正确的 A5 5A。
  const uint8_t noise[] = {
    0x00, 0xFF, 0xA5, 0x11, 0xA5
  };

  resetStream();
  feedStream(noise, sizeof(noise));
  feedStream(frame, length);

  printStreamResult(
    "NOISE_RECOVERY",
    streamAccepted == 1 && streamUsed == 0
  );

  // 测试5：坏 CRC 帧后接正常帧。
  uint8_t damaged[39];
  memcpy(damaged, frame, length);
  damaged[36] ^= 0x01;

  resetStream();
  feedStream(damaged, sizeof(damaged));
  feedStream(frame, length);

  printStreamResult(
    "BAD_FRAME_RECOVERY",
    streamAccepted == 1 && streamUsed == 0
  );

  resetStream();
}
const uint32_t STREAM_IDLE_TIMEOUT_MS = 1000;
uint32_t streamLastByteMs = 0;

// 检查半帧是否长时间没有收到后续字节。
// nowMs 由调用方提供，方便做可重复的模拟时间测试。
void checkStreamTimeout(uint32_t nowMs) {
  if (streamUsed == 0) {
    return;
  }

  // 无符号减法可处理 millis() 的正常回绕。
  uint32_t idleMs = nowMs - streamLastByteMs;

  if (idleMs < STREAM_IDLE_TIMEOUT_MS) {
    return;
  }

  Serial.println("STREAM: idle timeout");

  // 放弃超时的候选起点，继续搜索缓冲区内的后续帧。
  // 如果重新找到的候选仍不完整，也已超过空闲期限，
  // 则继续放弃，直到缓冲区没有残留。
  while (streamUsed > 0) {
    dropStreamBytes(1);
    processStreamBuffer();
  }
}

// 正式接收数据时使用这个入口。
// 收新数据前先处理旧半帧超时，避免将旧残留与新帧混合。
void feedStreamTimed(const uint8_t* data,
                     size_t length,
                     uint32_t nowMs) {
  checkStreamTimeout(nowMs);

  if (data == nullptr || length == 0) {
    return;
  }

  streamLastByteMs = nowMs;
  feedStream(data, length);
}

void runTimeoutTests() {
  uint8_t frame[168] = {};
  size_t length = encodeSosTest(frame, sizeof(frame));

  Serial.println("\n=== Stream timeout tests ===");

  if (length != 39) {
    Serial.println("SETUP: FAIL");
    return;
  }

  // 测试1：没到期限，保留半帧。
  resetStream();
  feedStreamTimed(frame, 10, 100);
  checkStreamTimeout(1099);

  printStreamResult(
    "BEFORE_TIMEOUT",
    streamAccepted == 0 && streamUsed == 10
  );

  // 测试2：达到空闲期限，清理未完成的候选帧。
  checkStreamTimeout(1100);

  printStreamResult(
    "PARTIAL_TIMEOUT",
    streamAccepted == 0 && streamUsed == 0
  );

  // 测试3：超时后收到新完整帧，仍可正常解析。
  feedStreamTimed(frame, length, 1200);

  printStreamResult(
    "AFTER_TIMEOUT_RECOVERY",
    streamAccepted == 1 && streamUsed == 0
  );

  // 测试4：期限以内补齐半帧，正常完成。
  resetStream();
  feedStreamTimed(frame, 10, 2000);
  feedStreamTimed(frame + 10, length - 10, 2500);

  printStreamResult(
    "PARTIAL_COMPLETED_IN_TIME",
    streamAccepted == 1 && streamUsed == 0
  );

  resetStream();
}
void setup() {
  Serial.begin(115200);
  delay(1500);
  runTests();
}

void loop() {
  if (Serial.available()) {
    char command = Serial.read();

    if (command == 't' || command == 'T') {
      runTests();
      runEncodeTest();
      runDecodeTest();
      runStreamTests();
      runTimeoutTests();
    }
  }
}



