# 硬件清单

更新：2026-11-12。主责 A。这是核对记录，不是已经联调通过的硬件系统。数量来自 A 当日确认；没看到实物丝印的项目写待确认。

LoRa **暂按未到货**。到货日期：________（填写人 / 日期：________）。两套可用节点就绪日 T：待确认。第三套就绪日 T3：待确认。

对应 [#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)、[#3](https://github.com/China-wzy41/MobiWeave-Protocol/issues/3)、[#5](https://github.com/China-wzy41/MobiWeave-Protocol/issues/5)。接线见 [wiring.md](wiring.md)，环境见 [dev-environment.md](dev-environment.md)。

## 已确认实物

|物品|型号（记录口径）|数量|用途|资料|状态|
|---|---|---|---|---|---|
|主控开发板|ESP32-S3，N16R8|2|节点或网关主控。N16 按乐鑫订购码理解为 16 MB Flash，R8 为 8 MB Octal PSRAM|见下文乐鑫链接|2026-11-12 A 确认在手。品牌、板型、丝印待确认|
|主控开发板|ESP32-S3，N8R8|2|同上，Flash 容量按订购码理解为 8 MB|同上|同上|
|LoRa 模块|大夏龙雀 DX-LR22-433T22D|4|433 MHz 频段节点间无线|见下文大夏龙雀手册|**暂按未到货**。到货日期留空，见文首|
|定位模块|用户原文：「ATGM366H-6N74（四模）」。核对结果见下一节|4|后续定位。本月不作为验收重点|见下文中科微|2026-11-12 A 确认有 4 颗。包装丝印尚未对照|
|杜邦线、面包板|未指定|数量未知|临时接线|无|有无与数量待确认|
|开发电脑|Windows 笔记本，Arduino IDE|1|烧录与串口监视|见[开发环境](dev-environment.md)|操作系统版本、IDE 版本待安装后填写|

四块 ESP32 与四块 LoRa 够四个无线节点。本月软件验收不依赖无线。M1 两节点基线至少用两套，三节点携带（[#11](https://github.com/China-wzy41/MobiWeave-Protocol/issues/11)）还要第三套，就绪日仍待 LoRa 到货后填写。

## 型号核对

### ESP32-S3 N16R8 / N8R8

乐鑫《ESP32-S3-WROOM-1 & WROOM-1U Datasheet》订购码：N16R8、N8R8 均为 Quad SPI Flash + 8 MB Octal SPI PSRAM（芯片为带 R8 的封装）。手册写明：模组若内置 ESP32-S3R8，IO35、IO36、IO37 接 Octal PSRAM，不能再作别的用途。

开发板不一定就是 WROOM-1。品牌未提供，上表只采用这组容量含义。板上是否为该模组，等看到屏蔽罩丝印再改。

### DX-LR22-433T22D

芯片为 LLCC68，接口是 UART，不是 SPI。下列数字都来自手册，不是本项目实测。

|项目|手册记载|
|---|---|
|供电|3.3–5.5 V，典型 5 V；不低于 5 V 才保证标称输出功率。绝对最大 5.5 V|
|通信电平|典型 3.3 V。使用 5 V TTL 有烧毁风险。I/O 电压推荐 3–3.7 V|
|引脚|1 M0、2 M1、3 RX、4 TX、5 AUX、6 VCC、7 GND。插针|
|射频接口|SMA，外螺内孔。外接天线|
|频段|433–532 MHz。默认信道 00 = 433.15 MHz，步进 1 MHz，信道号 00–63（十六进制）|
|默认串口|9600 bps，8 数据位，无校验，1 停止位|
|默认射频|透明传输，LEVEL2（手册表：SF11、BW 500 kHz、CR 4/5、空中字符速率 2148 bps），功率 22 dBm，地址 ff ff，密钥 12345 且默认开启，高时效模式，分包 230 字节|
|模式脚|`AT+SWITCH=0`（默认）时 M0/M1 为输出，默认低电平，模式用 AT 改。`AT+SWITCH=1` 时改为输入，不能悬空|
|RSSI|`AT+DRSSI`，默认关闭。打开后，模块在交给 MCU 的接收数据末尾加 1 字节 RSSI|
|SNR|这两份手册的命令表没有 SNR|
|发射电流|高时效模式发射 173 mA；空中唤醒模式发射 174 mA。均为默认参数下的手册值|
|灵敏度|−134 dBm 对应 BW=125 kHz、SF=11，不是默认 LEVEL2 的指标|
|距离|8 km 是 LEVEL0、天线高 3 m、增益 3 dBi、晴朗空旷的参考值，手册要求以实测为准|

`AT+HELP` 示例把 LEVEL2 打成 2149 bps，速率表写 2148 bps。差 1 bps。到货后保存模块打印的原文，不取平均。示例里的 `Bandwidth:6` 是内部编号，不是 6 kHz；带宽以速率等级表的 kHz 为准。

### 定位模块

用户原文是「ATGM366H-6N74（四模）」。

杭州中科微电子官网产品列表写的是 **ATGM336H-6N74**，说明为单频多模，支持 BDS、GPS、Galileo、GLONASS。这与「四模」一致。《ATGM336H-6N 用户手册》选购表写作 **ATGM336H-6N-74**，卫星系统为 GPS+QZSS+BD2+BD3+GAL+GLO，频点 L1+B1I+B1C+E1+R1。QZSS 在手册里和 GPS 放在同一行。

未查到「ATGM366H」这一型号。也要和 ATGM332D-6N74 分开：332D 封装尺寸不同。以到货模块上的丝印为准，核对前两行写法都保留。

手册中的裸模块是 10.1 mm × 9.7 mm 焊盘，不是排针。若实物是转接板，排针顺序以板上丝印为准，不要按裸模块脚号往面包板上插。

手册串口：115200 bps，8N1，NMEA-0183。供电 2.7–3.6 V，典型 3.3 V，绝对最大 3.6 V。本月不要求读定位。

## 清单里还没有、测试却会用到的东西

|物品|为什么需要|状态|
|---|---|---|
|433 MHz 天线|模块是外接 SMA。没接天线不发射|数量、是否随模块到货、接头是否为 SMA 公头：待确认|
|100 µF 与 0.1 µF 电容|技术手册建议放在模块电源脚附近|本次确认的物料未包含，待确认|
|万用表|到货后看发射时 VCC 是否低于 3.3 V|有无待确认|

报价、预算上限由 E 在 [#5](https://github.com/China-wzy41/MobiWeave-Protocol/issues/5) 记。本文不填未核实的价格。

## 资料链接

大夏龙雀资料页（A 提供的入口）：<http://www.szdx-smart.com/zlxz/lymk.html>

2026-11-12 从该站产品资料页打开的两份 PDF：

- [DX-LR22-433T22D 技术手册 V2.0（2025-05-09）](http://www.szdx-smart.com/static/upload/2025/12/08/202512086979.pdf)
- [DX-LR22-433T22D 串口应用指导 V2.0（2025-05-12）](https://www.szdx-smart.com/static/upload/2025/12/11/202512113214.pdf)

页面若改版，从资料页重新进，不要沿用失效直链。手册里的电脑串口工具名为资料包中的 sscom5.13.1，本仓库不附带该软件。

乐鑫：

- [ESP32-S3 芯片手册](https://documentation.espressif.com/esp32-s3_datasheet_en.pdf)（strapping、USB、片内 Flash/PSRAM 脚）
- [ESP32-S3-WROOM-1 手册](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)（N8R8 / N16R8、IO35–IO37）
- [ESP32-S3 硬件设计指南](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html)（Octal 时 GPIO33–GPIO37）

中科微：

- 官网：<https://www.hzzkw.com/> 。产品列表中的名称是 ATGM336H-6N74。2026-11-12 未找到该型号的单独产品页，也未找到官网直接提供的 PDF。
- 引脚和电气参数来自公开的《ATGM336H-6N 用户手册》副本：<https://xonstorage.z8.web.core.windows.net/pdf/zhongkewei_atgm336h6n74_apr22_xonlink.pdf> 。这是转存，不是官网直链。版本记录到 1.1（2023-01-11）。与随货手册冲突时以随货手册和丝印为准。

实验地点能不能在 433.15 MHz 发射、允许的功率和占空比，本文没有核对，待确认。手册的 433–532 MHz 和 8 km 只说明模块能力。基线测试在确认之前只用默认信道 00。
