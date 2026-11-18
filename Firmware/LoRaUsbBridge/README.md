# LoRa USB 桥

两块 ESP32-S3 烧这同一个程序。它只把电脑串口和 LoRa 串口的字节原样双向转发，不进 AT、不改射频、不切换 SWITCH，也不加回显、换行或 ACK。

上次 AT 测试已经用过的接法保持不变：LoRa TXD → GPIO18，LoRa RXD → GPIO17，LoRa 为 9600 8N1，电脑 `Serial` 为 115200。PJ15 只给本节点的 LoRa 供电，它的 TX/RX 断开。ESP32 用自己的 USB。只在本节点内共地。两节点之间不接线。M0、M1、AUX 不接。

## 烧录菜单

开发板选 ESP32S3 Dev Module。已保存的 `初次连接测试` 注释写的是 USB CDC On Boot disabled。若烧那份程序时菜单没改过，本桥同样选 Disabled，并继续用当时能看到 AT 菜单的那个口。当时具体是哪一个 USB 座没有单独核实，不要因此改口。

- 板载 USB 转串口（UART0）那个口：USB CDC On Boot 选 **Disabled**。这时 `Serial` 是 `HardwareSerial`（UART0）。
- 原生 USB 口：USB CDC On Boot 选 **Enabled**。USB Mode 为 Hardware CDC and JTAG 时 `Serial` 是 `HWCDC`；为 USB-OTG (TinyUSB) 时 `Serial` 是 `USBCDC`。口和菜单要配套，否则监视器没有字节。
- 程序不使用 `while (!Serial)`，监视器没打开时也不会停在 `setup`。

以上四种菜单组合都已用 esp32 核心 3.3.13 编译通过。`setRxBufferSize` 在这三种 `Serial` 上都有，并在 `begin` 之前调用。

波特率写在 `LoRaUsbBridge.ino` 开头的 `kUsbBaud` 和 `kLoraBaud`。引脚是 `kLoraRxPin`、`kLoraTxPin`。

## 先看文字

两个模块都要已经退出 AT、处在透明传输，并且 LEVEL 和信道相同。用户说节点已经配置好，但这次没有新的 `AT+HELP` 回显，所以程序不读取、也不改这些值。若模块仍停在 AT，键入的字会被模块当成 AT 命令，不会从空中发出。

1. 两板都打开串口监视器，115200。
2. 先只让 A 发短 ASCII，例如 `A1`、`A2`。B 的屏幕上应出现同样的字。
3. 这个桥没有本地回显。A 自己的屏幕不显示 `A1` 是正常的，不能当成失败。
4. B 能稳定看到之后，再让 B 发 `B1`、`B2`，到 A 的屏幕上查看。
5. 一次只发很短的一句，用手发。电脑是 115200，模块串口和空口慢得多，不要连续粘贴大段文字。

监视器的行结束符会在你发送的内容后面额外加上字节，桥会原样送出。选 NL 和 CR 时，每次发送会多 `0D 0A`。看短文字可以接受。它不是程序自己加的换行。

## 以后传协议字节

同一程序可以原样转发 v1 的二进制，包括 `00` 和 `FF`。它不认识帧，一次 `read` 读到多少字节也不代表一帧的边界。

传二进制时不要用串口监视器的行结束符，否则 CRLF 会插进帧里。用能发送原始字节的工具。屏幕上出现一段 HEX 文字，只说明字节到了，不是协议已经验收。本程序没有 ACK，也没有重传。

无线是否通，要以两端实际收到的字节为准。这里还没有上板，也没有做无线测试。
