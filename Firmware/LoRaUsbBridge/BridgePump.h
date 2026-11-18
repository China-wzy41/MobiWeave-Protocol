#pragma once

// Arduino's sketch preprocessor drops template lines in a .ino file.
// HardwareSerial, HWCDC, and USBCDC all provide available, availableForWrite,
// read, and write(uint8_t). 0x00 and 0xFF are forwarded. Nothing is added.

static constexpr int kPumpChunk = 64;

template <typename From, typename To>
static void pump(From &from, To &to) {
  int pending = from.available();
  if (pending <= 0) {
    return;
  }
  int room = to.availableForWrite();
  if (room <= 0) {
    return;
  }
  int count = pending < room ? pending : room;
  if (count > kPumpChunk) {
    count = kPumpChunk;
  }
  for (int i = 0; i < count; ++i) {
    int value = from.read();
    if (value < 0) {
      break;
    }
    to.write(static_cast<uint8_t>(value));
  }
}
