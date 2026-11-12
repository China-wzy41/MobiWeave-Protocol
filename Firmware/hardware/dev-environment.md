# Windows 与 Arduino IDE

更新：2026-11-12。主责 A。步骤来自乐鑫的 Arduino-ESP32 安装说明和当前 `boards.txt` 菜单名。**还没有在本项目的开发板上烧录成功**，下面每一项的实际版本号都留空。

板端业务程序待实现。这里只说明怎样把环境装到可以打开串口。不要把一次空草图上传写成串口协议已经通过。

对应 [#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2)。串口记录模板在 [Tests/serial-log.md](../../Tests/serial-log.md)。

## 安装

1. 用 Windows 笔记本。系统版本装好后写入记录，本文不猜。
2. 从 <https://www.arduino.cc/en/software> 安装当前的 Arduino IDE Windows 安装包。IDE 2 或 1.8.19 及以上都可以，乐鑫安装说明要求 1.8 级别或更新。把「关于」里的版本号写入记录。
3. 文件 → 首选项 → 附加开发板管理器网址，填稳定版索引，不要填 dev 索引。
   - 国际：`https://espressif.github.io/arduino-esp32/package_esp32_index.json`
   - 国内镜像：`https://jihulab.com/esp-mirror/espressif/arduino-esp32/-/raw/gh-pages/package_esp32_index_cn.json`
4. 工具 → 开发板 → 开发板管理器，搜索 `esp32`，安装 Espressif Systems 的稳定包。国内网络使用带 `-cn` 后缀的版本，并按乐鑫说明手动更新；自动更新不会走到 `-cn` 包。
5. 装完重启 IDE。把开发板管理器里显示的 esp32 版本写入记录。本文不指定某一个已验证版本。

安装说明：<https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html>

菜单文字核对自 <https://github.com/espressif/arduino-esp32/blob/master/boards.txt> 的 `esp32s3` 段（2026-11-12 读取的 master）。安装之后以 IDE 里的实际文字为准，文字变了就改本文件并记下板卡包版本。

## 开发板选项

工具 → 开发板 → esp32 → **ESP32S3 Dev Module**。品牌未知，不要选一个具体第三方板名。

先只插一块板。在板上贴 N16R8 或 N8R8，选项和贴纸一致。

|菜单|N16R8|N8R8|依据|
|---|---|---|---|
|Flash Size|16MB (128Mb)|8MB (64Mb)|订购码 N16 / N8。WROOM-1 手册同为 Quad SPI Flash|
|Flash Mode|QIO 80MHz|QIO 80MHz|WROOM-1 的 N8R8、N16R8 是 Quad SPI Flash，不是 WROOM-2 那种 Octal Flash|
|PSRAM|OPI PSRAM|OPI PSRAM|R8 为 Octal SPI PSRAM。不要选 QSPI PSRAM，也不要选 Disabled 来假装没有 PSRAM|
|Partition Scheme|16M Flash (3MB APP/9.9MB FATFS)|8M with spiffs (3MB APP/1.5MB SPIFFS)|与 Flash Size 同一档。IDE 第一项常是 4MB 方案，和这两块板的容量不一致|
|USB Mode|Hardware CDC and JTAG|同左|通用变体的默认方向。外置 USB 串口芯片待确认，见下一节|
|Upload Speed|先用 IDE 默认值|同左|失败再降到 115200。成功的那一档写入记录，本文没有已验证速度|
|USB CDC On Boot|见下一节|见下一节|取决于日志从原生 USB 还是从 UART0 出来|

其余菜单保持 IDE 默认，包括 CPU 频率。不要为了第一次上传去擦除整片 Flash。只有在错误的 PSRAM/Flash 选项导致无法启动、并且串口里已经留下失败日志之后，才擦除并在记录里写明。

若 QIO + OPI PSRAM 下串口持续报 PSRAM 未找到或无法启动：停下，把完整启动文字存进 `Tests/raw/`，核对屏蔽罩丝印。不要改成 OPI Flash，除非丝印表明它是 Octal Flash（例如 WROOM-2 或带 V 的 1.8 V 封装）。那种封装和 N16R8 的 WROOM-1 定义不同。

## USB、驱动、烧录

乐鑫串口说明：<https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/get-started/establish-serial-connection.html> 。该页写明：驱动一般会随系统安装；若没有自动出现端口，先认出 USB 转串口芯片再装驱动。乐鑫在该页列出的是 CP210x 和 FTDI。默认控制台速率是 115200、8 数据位、无校验、1 停止位。第一次用片内 USB 下载时，按住 BOOT，按一次 RESET，再松开 BOOT。

开发板品牌未知。可能是片内 USB（GPIO19 为 D−，GPIO20 为 D+），也可能是别的 USB 转串口芯片。CH340、CH9102 不在乐鑫该页的列表里，是否在板上待确认。先看丝印再装驱动，不要装来路不明的驱动包。

|现象|处理|
|---|---|
|设备管理器出现与片内 USB 或 USB Serial/JTAG 相关的 COM|优先用这个口。USB CDC On Boot 选 Enabled，使用户程序的 `Serial` 也从片内 USB 输出。GPIO19/20 仍不要当普通 GPIO|
|设备管理器出现 CP210x 或 FTDI 的 COM|USB CDC On Boot 选 Disabled，日志走 UART0（GPIO43/44）。驱动用乐鑫该页给出的厂商链接|
|设备管理器出现 CH340 或 CH9102|同样走 UART0，CDC On Boot 选 Disabled。驱动到沁恒 WCH 官网按芯片型号下载|
|插上后没有新的 COM|先换线（有的线只能充电）、换 USB 座。座子数量和丝印待确认。把设备管理器里的未知设备名称记下来，不要同时试多套驱动|

两块板不要一起插，除非 COM 口已经分别抄下来。

烧录：

1. 关掉串口监视器，否则 COM 被占用。
2. 工具 → 端口，选刚出现的那个 COM。
3. 文件 → 新建草图，保持空的 `setup` / `loop`，只用来确认端口。不要打开 Blink。通用 `ESP32S3 Dev Module` 变体把板载 RGB 的 `PIN_RGB_LED` 定义成 GPIO48，`LED_BUILTIN` 是在 GPIO 数量之上再加这个值，供 RGB 接口使用。这块板有没有灯、灯在哪一脚，待确认。
4. 上传。成功后打开串口监视器。
5. 若出现无法连接、无法进入下载：按住 BOOT，按一下 RESET，开始上传，再松开 BOOT。两个键的丝印待确认。有的板靠 USB 串口芯片的 DTR/RTS 自动进入下载，不一定需要按键。
6. 把使用的端口名称、要不要按 BOOT、板卡包版本、Flash/PSRAM 选项写入 [串口记录](../../Tests/serial-log.md) 的表头。

空草图上传成功只说明电脑能对这块芯片下载。它不是 [#2](https://github.com/China-wzy41/MobiWeave-Protocol/issues/2) 的「电脑发送、板端解析回传」。那个程序还没有写。

## 串口参数

两套速率不要混。

|链路|速率|格式|依据|
|---|---|---|---|
|电脑 ↔ ESP32 监视器|115200|8 数据位，无校验，1 停止位|ESP32 ROM 与 Arduino-ESP32 日志的常用速率。板端程序待实现，最终以固件里的 `Serial.begin` 为准，改了就要改本表|
|ESP32 ↔ DX-LR22|9600|8N1|串口应用指导 1.1，默认 `AT+BAUD` 序号 3。可选 2400 到 115200，改完要重启，两端一致|
|ESP32 ↔ 定位模块（以后）|115200|8N1|ATGM336H-6N 手册。型号丝印未核对前不要接|

监视器在向模块转发 AT 指令时，行尾用 CR 且 LF（`0x0D 0x0A`）。串口指导规定指令以回车换行结束，英文字母大写。`+++` 用来进入或退出 AT 模式，手册没有写保护时间；没有收到 `Entry AT` 就停，把实际发法记入待确认，不要连续猛发。

退出 AT 模式时模块会自动复位，这条在串口指导 5.1.1。`+++` 掉电不保存。

LoRa 暂按未到货。没有模块时，监视器里的 RSSI/SNR 写 `unknown`，不要填 0。
