# 2026-11-25 iPhone 与 ESP32-S3 BLE 双向通信

## 当日成果

- 打通 **iPhone 上的 nRF Connect ↔ BLE ↔ ESP32-S3** 的双向数据通信。电脑串口用于观察板端日志，手机通过蓝牙与板子通信。
- 手机向写入特征发送内容后，ESP32 串口出现 `Received Value: 10`、`Received Value: 1234`。手机界面的 `Last Write` 也显示 `1234`，证明本次手机到 ESP32 的数据已到达板端接收回调。
- ESP32 串口持续输出 `Notifying Value: …`；wzy 随后明确反馈手机 Notify 特征下的 **`Last Read` 确实持续变化**，确认 ESP32 到手机的通知已到达。不是只凭板端打印就判定通知成功。
- 串口截图中出现 `Device disconnected`、`Started advertising again...`、`Device connected`，重连后又收到 `1234`，说明本轮观察到一次断开、恢复广播和重连后的写入成功。未据此宣称自动重连或多轮稳定性已通过。
- 手机截图显示设备名为 `UART Service`、状态为 `Connected`；已发现 UART 服务及 Write、Notify 两个特征。

证据来自 2026-11-25 本次会话的两张截图（电脑串口、iPhone 服务页面）和 wzy 的文字反馈。串口截图可见 19:54 左右，手机状态栏显示 19:55；没有核对两端时钟，不据此计算单向延迟。日志日期按北京时间记录。截图原件及完整串口、手机导出日志尚未归档到仓库；本文记录观察结论，不把转述当作完整原始数据。

**验收范围：**本轮完成单部 iPhone 与单块 ESP32-S3 的 BLE 基础双向收发。没有完成 BLE↔LoRa 转发、另一部手机显示、真实定位、地图、应用命令回执或长期稳定性测试。既有两节点无线成果见原记录，本轮不重复验收。`PING/PONG`、`STREAM ON/OFF` 仍是后续建议，没有实现或实测。

## 注意事项

**设备和软件记录边界**

| 项目 | 本次已知情况／待补内容 |
|---|---|
| 手机 | iPhone、iOS；具体机型与系统版本待补 |
| 手机 App | nRF Connect for Mobile；实际版本待补 |
| 主控 | ESP32-S3；具体板号、模组丝印和 Flash/PSRAM 容量待补，不能自动对应为此前板1、板2或新买的芯路城板 |
| 固件行为 | BLE UART 风格服务；写入打印到串口，向手机周期发送计数；实际烧录源码尚未归档 |
| Arduino 环境 | 此前建议使用 esp32 板卡包 3.3.4 及其配套 UART 示例，但用户没有明确确认实际版本；不能写成已核验的烧录配置 |
| USB 与供电 | 实际所用 USB 口、USB CDC On Boot 和供电接法待补；下文按接口列出复现方法 |

**手机与 ESP32 的连接方法**

1. 准备一块能稳定启动的 ESP32-S3、一根 USB 数据线和电脑。单板 BLE 初测建议只接 USB；若移除外设，先断电。手机不需要通过 USB 接板子。
2. 电脑使用 Arduino IDE 和 Espressif 的 esp32 板卡包。可参考 [3.3.4 配套 UART 示例](https://github.com/espressif/arduino-esp32/blob/3.3.4/libraries/BLE/examples/UART/UART.ino)，菜单一般位于“文件 → 示例 → 对应 ESP32 开发板示例 → BLE → UART”。另存为 `BLE_FirstConnect` 后上传；示例代码和板卡包版本要配套，不混用最新开发分支与旧版库。
3. 开发板可按仓库说明选择 `ESP32S3 Dev Module`，Flash/PSRAM 按实物核对。芯路城资料中的 USB-ISP／CH340 转串口口对应 `USB CDC On Boot: Disabled`；USB-OTG 原生 USB 口对应 `Enabled`。电脑串口监视器设为示例中的 115200。以上是复现指导，不代表本次所有菜单已被截图确认。详见 [开发环境与烧录](../../../Firmware/hardware/开发环境与烧录.md) 和 [芯路城板资料](../../../Firmware/hardware/vendor/xinlu-esp32s3/README.md)。
4. iPhone 安装 [nRF Connect for Mobile](https://apps.apple.com/cn/app/nrf-connect-for-mobile/id1054362403)，开启蓝牙并授予 App 蓝牙权限；兼容系统版本以商店当前“兼容性”栏为准。
5. 在 nRF Connect 内扫描，选择 `UART Service` 并连接，不需要先在 iOS 系统蓝牙设置中配对。多块同名板同时出现时逐块上电确认身份，不能只凭同名自动选板。
6. 打开服务列表，找到下面的 UART 服务。对 Write 特征点 `↑`，按文本／UTF-8 写入 `1234`；若使用 Hex，发送 `31 32 33 34` 才是四个文本字符 `1234`，不能把 Hex 输入 `12 34` 当成同一内容。
7. 检查串口收到 `Received Value: 1234`。在 Notify 特征右侧开启通知订阅，观察手机 `Last Read` 持续更新。重连后确认订阅状态，必要时重新开启。
8. 保持 App 在前台进行首轮验证。能扫描不能连接时检查是否被其他客户端占用；能连接但收不到通知时先检查订阅；串口无输出时检查实际 USB 口、CDC 设置和波特率。

| 对象 | 完整 UUID | 数据方向／作用 |
|---|---|---|
| UART 服务 | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` | 将收发特征组织在同一个服务中 |
| RX 特征 | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` | 手机 Write → ESP32；RX 是从板子的角度命名 |
| TX 特征 | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` | ESP32 Notify → 手机；TX 是从板子的角度命名 |

ESP32-S3 使用 BLE，不能直接套用普通 ESP32 的 `BluetoothSerial` 经典蓝牙串口教程。[乐鑫说明](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/bluetooth.html)。仓库原有 [初次连接测试](../../../Firmware/初次连接测试/README.md) 是 LoRa AT 菜单程序，不具备本轮手机 BLE 收发功能。

**GATT 与页面中的服务**

GATT（Generic Attribute Profile，通用属性配置文件）规定 BLE 数据的组织和访问方式。在本轮方案中，ESP32 是提供服务的 GATT 服务端，手机是访问服务的 GATT 客户端；“服务端”就是板子，不依赖公网。Service 是一组功能，Characteristic 是可读、可写或可订阅的数据入口，Property 表示允许的操作，Descriptor 是附加配置，UUID 用于标识这些对象。GATT 传递字节，字节代表什么业务命令要由应用协议约定。[蓝牙官方介绍](https://www.bluetooth.com/bluetooth-resources/intro-to-bluetooth-gap-gatt/)

| 页面文字 | 含义 |
|---|---|
| `CONNECTED SERVICES` | 已连接设备的服务列表 |
| `1800` | Generic Access 基础服务，通常包含设备名称等信息 |
| `1801` | Generic Attribute 基础服务，用于 GATT 服务结构相关功能 |
| `PRIMARY SERVICE` | 主服务类型说明，不是操作按钮 |
| `Notify` | 支持由板子向已订阅的手机推送数据 |
| `Write` | 支持手机向板子写入数据 |
| `Last Read` | 最近一次接收／读取后显示的值；在本例中可来自通知，不代表手动读取或累计包数 |
| `Last Write` | 最近一次写入的值；截图为 `1234` |

**手机截图中各按钮的用途**

下表按本次截图位置记录。收发方向由示例和本次结果确认；辅助按钮按界面含义解释，未逐项操作验收。顶部两个入口仅凭静态截图不能确定，保留待确认标记，不把先前会话中的推测写成实测事实。

| 位置／按钮 | 用途及本轮使用方式 |
|---|---|
| 左上角蓝色 `⌄` | 收起设备详情，返回外层视图；与 `Disconnect` 的断开动作区分 |
| 顶部天线图标 | 广播信息页面，查看名称、广播数据、信号强度等 |
| 顶部三行列表，截图中白底选中 | 服务与特征页面；本轮收发就在这里进行 |
| 顶部圆柱体图标 | **入口名称待确认**。会话中按布局推测为 Server／手机本机 GATT 服务页面；需点击核对标题后再作确定说明，本轮不需要使用 |
| 顶部记事本图标 | 通信日志入口，用于检查连接、写入、通知和错误等事件 |
| 顶部双循环箭头 | **入口名称待确认**。会话中按布局推测为 DFU 固件升级页；不能仅凭形状当成刷新按钮。本轮 UART 示例未实现对应升级服务 |
| 右上角 `Disconnect` | 断开手机与当前 ESP32 的 BLE 连接 |
| 各数据项下方两张重叠纸张 | 复制对应项的数据，用于粘贴或记录 |
| 各数据项下方双引号 | 数据解析／显示格式入口，用于选择文本、Hex、数值等；具体选项以实际版本为准，切换显示不会改变已收到的字节 |
| `6E400003…` 的 Notify 区右侧带底线 `↓` | 通知订阅开关；开启后自动接收板子的通知，不需要每次点读取 |
| `6E400002…` 的 Write 区右下角 `↑` | 打开写入窗口，选择输入格式，发送数据给板子 |
| `2902` 内的复制、双引号 | 分别用于对应描述符数据的复制、显示格式选择 |
| `2902` 内普通 `↓` | 读取描述符；与 Notify 旁的订阅按钮不是同一操作 |
| `2902` 内普通 `↑` | 写入描述符的入口；实际可操作性受 iOS 和 App 限制，正常订阅不应依赖手动写入这里 |
| 底部左右三角形 | 切换查看其他已打开的设备；截图呈灰色，表示当前无可切换项。不是播放、暂停或发包按钮 |
| 底部 `UART Service`、`Connected` | 当前设备名称与已连接状态显示 |

`2902` 是客户端特征配置描述符（CCCD），用于通知／指示订阅配置。正常操作使用 Notify 特征的订阅按钮，由 App 和 iOS 管理，不需要手动填写 CCCD。界面功能参考 [Nordic 官方功能说明](https://github.com/nordicsemi/IOS-nRF-Connect#features)；底部设备切换行为见 [官方导航说明](https://devzone.nordicsemi.com/nordic/nordic-blog/b/blog/posts/announcing-nrf-connect-2-0-for-ios)。这些资料不替代对当前版本两个未确认图标的实际核对。

**计数通知和写入的解释**

- 参考示例的通知载荷是一个递增字节，按 `uint8_t` 从 255 回到 0。推荐按 Hex 或 UInt8（若 App 提供）观察；按文本解析时可能看到字符或不可打印内容。手机截图的 `3` 不能直接解释为“第 3 包”，也不能在不知道解析格式时断定原始数值就是十进制 3。
- 当前周期通知不是对手机输入的自动回显；收到 `1234` 后，计数仍按自己的节奏变化。要实现回显、命令确认或远端收妥，需要增加应用逻辑。
- 手机的 GATT 写入完成、板端程序处理完成、LoRa 远端收妥是不同阶段，不能混称同一个 ACK。

## 待办

**先补齐复现材料。** 记录板子标签及模组丝印、实际 USB 接口、Arduino IDE／esp32 板卡包版本、Flash／PSRAM／CDC 菜单、iPhone 型号／iOS 版本和 nRF Connect 版本；保存实际烧录源码。按 [工程日志约定](../README.md)，截图、完整串口和手机导出日志归档到 `Tests/raw/<run_id>/`，统计放 `Tests/analysis/<run_id>/`，再从本日志链接。核对圆柱体和循环箭头入口的实际标题，补充按钮说明。

**第一步：继续使用 nRF Connect，实现板端命令处理。** 保留现有 UART 服务及两个特征，先约定以下仅用于 BLE 联调的命令；不将它们宣称为已冻结的 LoRa 协议或另立一套 v1。

| 待实现命令 | 板端动作 | 预期通知响应 |
|---|---|---|
| `PING 1` | 检查请求能否被应用处理 | `PONG 1` |
| `STREAM OFF` | 停止周期计数通知 | `OK STREAM OFF` |
| `STREAM ON` | 恢复周期计数通知 | `OK STREAM ON` |

起步约定一次 GATT 写入是一条命令，每条不超过 20 字节，先用 ASCII 文本；20 字节是本轮起步约束，不是 BLE 的永久上限。板端流程为 `onWrite → 校验长度/格式 → 有界命令队列 → loop/任务执行 → TX 特征 setValue/notify`。较长的 LoRa 等待、重试等不放在蓝牙回调中阻塞执行；未知命令、过长输入、队列满和断连应有明确处理。将后续命令回复与计数通知区分，便于手机解析。

待验收：手机发送 `PING 1` 后收到匹配的 `PONG 1`；`STREAM OFF` 后收到确认且停止周期通知，`STREAM ON` 后收到确认并恢复。保留结果日志。应用回执只确认约定阶段，不能表示尚未接入的远端 LoRa 已收到。

**第二步：准备自有 iOS App。** 建议 SwiftUI 做界面、CoreBluetooth 做通信。需要可用的 Mac／Xcode、应用签名配置和真实 iPhone；本次没有确认这些开发条件已经具备。没有 Mac 时可先做板端命令并用 nRF Connect 验证。

- 首版界面：扫描设备、选择并连接、连接状态、命令输入、发送按钮和接收日志。
- 配置 `NSBluetoothAlwaysUsageDescription`，说明蓝牙用于连接织网节点、收发文字与位置；用户允许且蓝牙状态为可用后再扫描。
- 正确流程：等待蓝牙可用 → 扫描／选择设备 → 连接 → 发现服务 → 发现 RX/TX 特征 → 订阅 TX 并确认成功 → 启用发送。每一步等待对应回调，不把这些异步调用连续执行后就假定准备完成。
- 手机用 `CBCentralManager` 管理扫描和连接；用 `discoverServices`、`discoverCharacteristics` 查找完整 UUID；用 `setNotifyValue(true, for: txCharacteristic)` 订阅；向 RX 调用 `writeValue(data, for: rxCharacteristic, type: .withResponse)`；在 `peripheral(_:didUpdateValueFor:error:)` 中处理收到的数据。根据写入回调推进发送队列，处理错误、断连后重新发现与订阅。
- 参考的 3.3.4 UART 示例没有显式将服务 UUID 加入广播。初测可在前台不按服务 UUID 过滤扫描，连接后检查服务；或在板端明确添加服务广播，再按 UUID 扫描。避免出现调试 App 看得到而自己的 App 扫不到的情况。
- 查询 `maximumWriteValueLength(for:)` 等实际容量后设计发送长度；较长文字、中文 UTF-8 和位置报文需明确定界、分包与重组。接收通知长度也应服从实际协商和库的限制。
- 第一轮以 App 前台收发为验收目标。锁屏／后台行为、自动重连、超时与长期稳定性后续单独验证，不由本次结果推定。

开发参考：[Apple 中心设备流程](https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/PerformingCommonCentralRoleTasks/PerformingCommonCentralRoleTasks.html)、[蓝牙权限说明](https://developer.apple.com/documentation/bundleresources/information-property-list/nsbluetoothalwaysusagedescription)。

**第三步：接入项目链路。** 单板命令闭环通过后实现 BLE↔LoRa 转发，先测短文字，再测真实定位和手机显示。仅一部手机时可先用远端电脑串口收发，完整手机到手机验收需要第二部手机及第二套兼容节点。LoRa 接线和供电参照 [成功板记录](../../../Firmware/hardware/2026-11-17-ESP32-LoRa成功板记录.md)：模块 TXD→GPIO18、RXD→GPIO17，9600/8N1，独立 5V 供电、ESP USB 供电并共地，两路 5V 不并联；模式和射频配置以当次读回与核对结果为准。真实定位由 iOS CoreLocation 获取并处理权限；nRF Connect 不会自动替代定位和地图 App。接入时遵循 [项目协议基线](../../protocol/README.md)，外场前完成 [现行计划](../../planning/长期计划.md) 要求的无线电核对。
