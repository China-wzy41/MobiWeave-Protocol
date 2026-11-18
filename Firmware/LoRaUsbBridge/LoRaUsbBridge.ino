#include <Arduino.h>

#include "BridgePump.h"

// USB <-> LoRa transparent byte bridge.
// Same sketch on both nodes. Does not enter AT, change RF, or add bytes.
// LoRa TXD -> GPIO18 (RX). LoRa RXD -> GPIO17 (TX). 9600 8N1.
// Serial is UART0, HWCDC, or USBCDC depending on the USB CDC On Boot menu.

static constexpr uint32_t kUsbBaud = 115200;
static constexpr uint32_t kLoraBaud = 9600;
static constexpr int kLoraRxPin = 18;
static constexpr int kLoraTxPin = 17;
static constexpr size_t kRxBufferBytes = 1024;

static HardwareSerial LoRaSerial(1);

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
