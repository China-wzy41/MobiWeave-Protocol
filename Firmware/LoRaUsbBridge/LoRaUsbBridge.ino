#include <Arduino.h>

// USB <-> LoRa transparent byte bridge.
// Same sketch on both nodes. Does not enter AT, change RF, or add bytes.
// LoRa TXD -> GPIO18 (RX). LoRa RXD -> GPIO17 (TX). 9600 8N1.
// PC Serial is 115200 on the UART USB port used for the earlier AT test.

static constexpr uint32_t kUsbBaud = 115200;
static constexpr uint32_t kLoraBaud = 9600;
static constexpr int kLoraRxPin = 18;
static constexpr int kLoraTxPin = 17;
static constexpr int kChunk = 64;
static constexpr size_t kRxBufferBytes = 1024;

static HardwareSerial LoRaSerial(1);

// Move at most kChunk bytes, and never more than the destination can accept
// right now. 0x00 and 0xFF are forwarded. Nothing is added or echoed.
static void pump(HardwareSerial &from, HardwareSerial &to) {
  int pending = from.available();
  if (pending <= 0) {
    return;
  }
  int room = to.availableForWrite();
  if (room <= 0) {
    return;
  }
  int count = pending < room ? pending : room;
  if (count > kChunk) {
    count = kChunk;
  }
  for (int i = 0; i < count; ++i) {
    int value = from.read();
    if (value < 0) {
      break;
    }
    to.write(static_cast<uint8_t>(value));
  }
}

void setup() {
  Serial.setRxBufferSize(kRxBufferBytes);
  LoRaSerial.setRxBufferSize(kRxBufferBytes);
  Serial.begin(kUsbBaud);
  LoRaSerial.begin(kLoraBaud, SERIAL_8N1, kLoraRxPin, kLoraTxPin);
}

void loop() {
  pump(LoRaSerial, Serial);
  pump(Serial, LoRaSerial);
}
