# 芯路城 ESP32-S3 开发板资料

访问日期：2026-11-18（北京时间）。这里只归档普通 ESP32-S3 开发板用得上的原始文件。用户说明新买了两块 ESP32-S3 N16R8，到货未确认，也没有上电测试记录。这两块不是 2026-11-17 的板1、板2，也不能说明第三套重启已经修好。

## 来源

1. 普通开发板客户资料：<https://www.xinlucity.com/?s=resourcedetail/index/id/61.html>
2. 8MB PSRAM 问答：<https://www.xinlucity.com/?s=plugins/index/pluginsname/ask/pluginscontrol/index/pluginsaction/detail/id/110.html>
3. CAM 客户资料。用户未说明购买 CAM，CAM 设置不套用普通板。未整包下载：<https://www.xinlucity.com/?s=resourcedetail/index/id/555.html>

## 已保存

| 文件 | 类型 | 字节 | SHA256 | 原始 URL |
|---|---|---:|---|---|
| [ESP32S3开发板原理图.pdf](ESP32S3开发板原理图.pdf) | PDF，1 页 | 251405 | `9e222daf4ecf01f7261564ae2c1765de1882d664e4f5b564ecfb69ea07453e58` | <https://testxinlu.oss-cn-beijing.aliyuncs.com/static/upload/file/warehouse/2026/05/15/1778810837723945.pdf> |
| [引脚定义图.jpg](引脚定义图.jpg) | JPEG | 6998349 | `5d12205c5317305f8a20ce9e7142e9afbb1a77fdbd8e767b1531bd208abdf396` | <https://testxinlu.oss-cn-beijing.aliyuncs.com/static/upload/file/warehouse/2026/06/24/1782280329828194.jpg> |
| [尺寸图.png](尺寸图.png) | PNG | 134385 | `54614394136ebf3f0c8bc94219ebafa980bf70d6aced498b05c0c73a995c3541` | <https://testxinlu.oss-cn-beijing.aliyuncs.com/static/upload/file/warehouse/2026/06/24/1782263870271423.png> |
| [esp32-s3_datasheet_cn.pdf](esp32-s3_datasheet_cn.pdf) | PDF，83 页 | 1635642 | `adee5f18f1b565cf386f0b3feed7c437bcc1a8e57619e922198da2d47f96b400` | <https://testxinlu.oss-cn-beijing.aliyuncs.com/static/upload/file/warehouse/2026/07/13/1783913303242785.pdf> |
| [PSRAM.zip](PSRAM.zip) | ZIP，内有 `PSRAM.ino` | 348 | `381eda1bade224716a5178c74e8b71ea4f6550c290882c591966c5c58df3667d` | <https://testxinlu.oss-cn-beijing.aliyuncs.com/static/upload/file/plugins_ask/ask/20/2026/09/04/1788486836395541.zip> |
| [PSRAM填充测试（MicroPython）.zip](PSRAM填充测试（MicroPython）.zip) | ZIP，内有 `main.py` | 2863 | `2ebccf5d9cc5f9d6d0c2a13b111c65fc7de05c05cd84eda5fb6ecfa6203fcdc8` | <https://testxinlu.oss-cn-beijing.aliyuncs.com/static/upload/file/plugins_ask/ask/20/2026/09/04/1788484615602701.zip> |

资料页上还有一份同名 MicroPython 压缩包，SHA256 为 `aed8509841e76937b65ea912ce467849da62aeb64fd37d42762a9c896c03f5d5`，URL 是 <https://testxinlu.oss-cn-beijing.aliyuncs.com/static/upload/file/warehouse/2026/07/22/1784692837335580.zip>。压缩包本身不同，里面的 `main.py` 与上面这份相同，SHA256 `adcf63fc3cf2719b8fad9af1cb4f9fd514092d30fb0316a53da60ac693883574`。仓库只留问答页这一份。

## 页面写了什么

以下是商家页面正文，不是实测。

- 电脑口选名称里带 CH340 的 COM。原理图上有 CH340C，接在标为 USB-ISP 的 Type-C；另一个 Type-C 标为 USB-OTG，数据线在 GPIO19、GPIO20。
- GPIO26 到 GPIO32 是板载 Flash/PSRAM 专用，页面写没有引出，不能当普通 IO。GPIO0、GPIO45、GPIO46 是启动配置脚，GPIO0 拉低进入下载；页面写板子有一键下载。
- 页面建议外部模块使用一组串口，并在例程里把 GPIO17 写成 TX、GPIO18 写成 RX。UART0（GPIO43/44）留给调试和下载。GPIO17/18 是本项目选定的映射，不是 ESP32-S3 上 UART1 唯一可用的引脚。
- 页面写 N16R8 自带 8MB PSRAM，Arduino 里选 **OPI PSRAM**。同一页没有写要选 OPI Flash，也没有写 Flash 容量或 QIO/DIO。原理图符号印的是 `ESP32-S3-WROOM-1-N16R8`，这只说明图纸按这个模组名来画，不能代替新板屏蔽罩丝印。
- 3V3 被写成板载稳压输出，最大约 1A。这是商家声称，新板没有实测，不作为供电承诺。
- 5V-IN 被写成默认不向外供电；需要对外 5V 时短接 IN-OUT 焊盘。引脚图和尺寸图上有这个焊盘。原理图能看到 5V、VBUS、三只 B5819W 和稳压器 U12，抽出的文字没有自己证明“默认不输出”。这不能用来宣布昨天那块板的 5V 口已经修好。

芯片规格书是商家标成 `esp32-s3_datasheet_cn.pdf` 的 83 页 PDF，页脚是乐鑫 ESP32-S3 规格书 v2.2。正文用了特殊字体，文本抽取读不出订购表，所以不从这份 PDF 引用 Flash/PSRAM 容量。

问答页两种查 PSRAM 的方法都是商家例程，没有改昨天的 `初次连接测试`：MicroPython 的 `main.py`，以及 `PSRAM.ino` 里 `psramFound()` 后打印 `ESP.getPsramSize()`。PSRAM 不是 LoRa 串口通信所必需。

CAM 页另写了 Flash 16MB、QIO 80MHz、摄像头和 SD 卡引脚。用户未说明购买 CAM，CAM 设置不套用普通板。

## 没有保存的链接

- 百度网盘离线包：<https://pan.baidu.com/s/1teLKfDVP9NXphiU6RN3Ecw?pwd=1234>，提取码 `1234`。打开后是百度分享页，没有登录，没有拿到文件。
- Flash 下载工具 `flash_download_tool_3.9.3.7z`，约 23MB：<https://www.xinlucity.com/public/static/upload/file/warehouse/2026/04/11/1775887294194252.7z>。是烧录工具，未保存。
- CH340 驱动 zip：<https://testxinlu.oss-cn-beijing.aliyuncs.com/static/upload/file/warehouse/2026/04/25/1777106877446285.zip>。未保存。
- `wifi.zip`：<https://testxinlu.oss-cn-beijing.aliyuncs.com/static/upload/file/warehouse/2026/10/29/1793254741278442.zip>。是 Wi-Fi 示例，未保存。
- CAM 页上的 `ESP32S3_CAM.zip`、`ESP32S3_TF.zip` 和 `SCH_DC-DC版本_2026-11-09(1).pdf` 未下载。

## 编译速度

这三页正文里没有“编译”“缓存”或“杀毒”。下面是用户转述的商家问答，不是从这三页抄出的原文。

商家认为示例很短也会首次编译偏慢，因为 ESP32 的 Arduino 框架会加载完整 SDK；建议用 Arduino IDE 2.x，它有编译缓存，改完代码后的第二次会快一些；同时清理不用的库，工程放在固态硬盘。商家还提到关闭杀毒软件对编译目录的扫描。不把关杀毒当成操作建议。防护保持开着，先查 IDE 2.x 缓存、硬盘和多余的库。不要理解成 IDE 1 完全没有缓存，或每次编译都必然重编整个 SDK。

## 参考例程注意

资料页例程 4 写的是 `myUART.begin(9600, SERIAL_8N1, GPIO_NUM_19, GPIO_NUM_20); // TX, RX`。乐鑫 Arduino 的 `begin` 参数顺序是波特率、配置、RX、TX，见 <https://docs.espressif.com/projects/arduino-esp32/en/latest/api/serial.html>。商家注释把 TX、RX 写反了；按官方声明，这行实际是 RX19、TX20，而且 GPIO19/20 与原生 USB 重叠。不要原样照搬。项目继续用已经测通的 RX18、TX17，北斗另选不冲突的 GPIO。17/18 只是本项目选定的映射，不是 S3 上 UART1 的唯一引脚。这不是昨天通信问题的原因，成功源码不改。来源：资料页例程 4，以及上面的乐鑫串口文档。

## 对本项目的用途

1. LoRa 继续用已经测通的接法：模块 RXD 接 GPIO17，模块 TXD 接 GPIO18。这是项目选定的 UART 映射，不是芯片规定 UART1 只能用这两脚。北斗不要再占这两脚。参数顺序以乐鑫文档为准，不要照搬例程 4 的注释。来源：资料页例程 4，以及 <https://docs.espressif.com/projects/arduino-esp32/en/latest/api/serial.html>。
2. 北斗仍按现有计划用 3.3V，并找空闲 UART。原理图把头上的 GPIO15、GPIO16 引了出来；GPIO19/20 是原生 USB，GPIO43/44 是 CH340 调试口，GPIO26–32 商家写明没有引出。来源：原理图模块引脚、资料页【4】和【5】。
3. 这张原理图证明的是芯路城这版图纸上有 WROOM-1-N16R8、CH340、双 Type-C 和 IN-OUT 焊盘。新买的两块到货未确认，图纸也没有证明昨天的 5V 掉压或第三套重启因此解决。5V 默认不输出是商家正文，不是这次对原理图网表的实测。
4. 若要确认 PSRAM，只把菜单设成 OPI PSRAM，再用商家的 `PSRAM.ino` 看 `psramFound()`。不要因为写着 N16R8 就改成 OPI Flash。PSRAM 不开也不影响已经测通的 LoRa AT。来源：资料页“PSRAM 支持”和问答页方法 2。
5. 编译慢先按商家说的 IDE 2.x 缓存、固态硬盘和少装库来查，杀毒保持开启。这是用户转述，三页上没有对应原文。
