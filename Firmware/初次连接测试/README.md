# 初次连接测试

2026-11-17 在板1、板2上做过串口实测的程序。从 `LoRa_AT_Test_v2.ino` 原样保存，只改了所在目录和文件名。

- ESP32-S3 + DX-LR22-433T22D。
- PJ15 只给 LoRa 独立 5V。ESP32 用自己的 USB。固定共地，不把两路 5V 输出并在一起。
- LoRa TXD → ESP GPIO18，LoRa RXD → ESP GPIO17。PJ15 的 TX/RX 断开。
- 电脑 115200；LoRa 9600、8N1。
- 输入数字 4 发送 `+++` 加 CR、LF，进入 AT；2 发送 `AT` 加 CR、LF，应返回 OK；3 发送 `AT+HELP` 加 CR、LF，读参数。
- 监视器的行结束符不影响这些硬编码命令。选 NL/CR 不会自动改变菜单 1；菜单 1 仍只发三个加号。
- 不改射频参数，不自动发送，不控制 M0/M1。
- UART 实测通过不等于无线通过。

官方草图名只允许基本拉丁字母、数字、下划线、点和短横线。下载后若 Arduino IDE 1.8.x 拒绝中文名称，把文件夹和 `.ino` 一起改成同一个 ASCII 名 `LoRa_FirstConnect` 即可；仓库里的中文路径不改。
