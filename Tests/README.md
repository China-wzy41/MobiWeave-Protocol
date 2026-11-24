# 测试记录

整条手机链路还没有整段验证。ESP 与 LoRa 的实验台通信已经做过。实验台两节点无线通信另有记录，在 hsr 分支 `Yanis0118-patch-1`，不在 `main`：[2026-11-21 空口联调](https://github.com/China-wzy41/MobiWeave-Protocol/blob/ca128e3d88589a5ef82af96bcf9f2ea97a2768ec/Tests/hardware-bringup-2026-11-21.md)。其中只有裸透传 LoRa 为 PASS。原始日志仍待补入。协议帧、确认、重试、去重、转发和多跳没有验收。2026-11-18 在本仓库另有一次 4 帧 DATA/CRC 小样本，见下面的原始包；那天没有 ACK，批量无线统计仍然没有。已有记录和仍待执行的步骤：

- [2026-11-17 工程日志](../docs/ProjectLog/A_wzy/2026-11-17-电脑-ESP32-S3-LoRa串口联调.md)
- [板1、板2](../Firmware/hardware/2026-11-17-ESP32-LoRa成功板记录.md)
- [2026-11-16 协议自测](protocol-selftest-2026-11-16.md)：板上跑了帧解析自测，报文由程序内部构造，没有经过 LoRa。USB CDC On Boot 那次记的是 Enabled，与 11 月 17 日的 AT 测试不是同一次。
- [两节点无线测试步骤](两节点无线测试步骤.md)：页内的批量步骤仍待执行，不取消已经留下的实验台两节点记录。任何户外或外场使用前，先完成无线电核对，再配置 LoRa
- [串口记录模板](串口记录模板.md)：空白骨架
- [2026-11-18 原始包](raw/2026-11-18-two-node-data-crc/README.md) · [核算](analysis/2026-11-18-two-node-data-crc.md) · [团队日志](../docs/ProjectLog/TeamLog/2026-11-18-双节点LoRa互传与DATA-CRC验证.md)

产生数据时再使用：

```text
Tests/
  configs/
  raw/<run_id>/
  analysis/<run_id>/
```

每次写明 REAL、SIM 或 ESTIMATED。失败也保留，原始文件不覆盖。口径见 [怎么验证](../docs/method/README.md)。
