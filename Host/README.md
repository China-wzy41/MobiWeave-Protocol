# 上位机

当前要在队友手机上显示对方的位置和短文字，并在手机里预先下载的离线地图上看到集合点。地图瓦片不走 LoRa。这里还没有这个程序。

开放中的 [PR 27](https://github.com/China-wzy41/MobiWeave-Protocol/pull/27) 是 USB 与 LoRa 字节桥试验，未合并，不是队友手机上的显示。

日志校验、统计和回放由 C（ygh）负责，不在界面里另算一套指标。没有真实位置或测量时，不要画看起来像实测覆盖的图。

格式说明见 [协议](../docs/protocol/README.md)。v1 样例不在 `main`。方向见 [长期计划](../docs/planning/长期计划.md)。
