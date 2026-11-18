#include <Arduino.h>

// ESP32-S3 COM USB connector, USB CDC On Boot disabled.
// Module TXD -> GPIO18; module RXD -> GPIO17.
// Module powered separately at 5V; ESP32 and module share GND.
// PJ15 TX/RX must NOT be connected to the module for this test.
HardwareSerial LoRaSerial(1);
constexpr int RX_PIN = 18;
constexpr int TX_PIN = 17;
uint32_t rxTotal = 0;
uint32_t rxAtRequest = 0;
uint32_t requestTime = 0;
bool waiting = false;

void showMenu() {
  Serial.println("\r\n=== LoRa AT test V2: ESP32-S3 ===");
  Serial.println("PC:115200  Module:9600 8N1  RX:18 TX:17");
  Serial.println("Send ONE digit in the PC serial monitor:");
  Serial.println("1 : send +++ (no CR/LF; toggles AT mode)");
  Serial.println("2 : send AT with CR/LF");
  Serial.println("3 : send AT+HELP with CR/LF");
  Serial.println("4 : send +++ with CR/LF (comparison test)");
  Serial.println("? : show this menu");
  Serial.println("Module bytes are printed directly below.");
}

void sendRequest(const char *data, size_t len, const char *label) {
  Serial.printf("\r\n[TX] %s\r\n", label);
  rxAtRequest = rxTotal;
  size_t queued = LoRaSerial.write((const uint8_t *)data, len);
  LoRaSerial.flush();
  Serial.printf("[UART accepted %u/%u bytes; NOT a module ACK]\r\n",
                (unsigned)queued, (unsigned)len);
  requestTime = millis();
  waiting = true;
}

void setup() {
  Serial.begin(115200);
  LoRaSerial.begin(9600, SERIAL_8N1, RX_PIN, TX_PIN);
  delay(1000);
  showMenu();
}

void loop() {
  while (LoRaSerial.available() > 0) {
    int c = LoRaSerial.read();
    if (c >= 0) {
      Serial.write((uint8_t)c);
      ++rxTotal;
    }
  }

  // A 2-second observation window, NOT a manufacturer's timeout rule.
  if (waiting && (uint32_t)(millis() - requestTime) >= 2000) {
    Serial.printf("\r\n[RX in observation window: %lu bytes; total: %lu]\r\n",
                  (unsigned long)(rxTotal - rxAtRequest),
                  (unsigned long)rxTotal);
    waiting = false;
  }

  while (Serial.available() > 0) {
    int c = Serial.read();
    // Ignore line endings chosen in the PC serial monitor.
    if (c == '\r' || c == '\n' || c == ' ') continue;
    if (c == '?') {
      showMenu();
    } else if (c == '1' || c == '2' || c == '3' || c == '4') {
      if (waiting) {
        Serial.println("\r\n[Busy: wait for RX summary, then send ONE digit.]");
        continue;
      }
      if (c == '1') sendRequest("+++", 3, "+++ (no CR/LF)");
      if (c == '2') sendRequest("AT\r\n", 4, "AT + CR/LF");
      if (c == '3') sendRequest("AT+HELP\r\n", 9, "AT+HELP + CR/LF");
      if (c == '4') sendRequest("+++\r\n", 5, "+++ + CR/LF");
    } else {
      Serial.println("\r\n[Use 1, 2, 3, 4 or ?. Input is NOT forwarded verbatim.]");
    }
  }
  delay(1);
}
