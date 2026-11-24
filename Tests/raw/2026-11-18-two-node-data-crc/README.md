# 2026-11-18 两节点 DATA/CRC 原始包

两台电脑各一份用户附件，字节原样保存，没有解包再提交，也没有脱敏或改内容。解包内容需要时从 zip 读取。

| 入库文件 | 节点 | run_id | 大小 | SHA256 |
|---|---|---|---|---|
| [node1-original.zip](node1-original.zip) | node1 | `20261118-204843` | 1816 | `1d26071905b80095ce9d36404970fd46267a7ca887dfc00279424ed6880e2f19` |
| [node2-original.zip](node2-original.zip) | node2 | `20261118-210410` | 1876 | `7dddecfad0399c1cb5587113aeb93c6d24bba278198c7d76d733155be97244a1` |

来源是用户提交的原始附件。两个 run_id 不同，是两台电脑各自的会话，不是同一个捕获编号。

zip 内路径：

- `logs/20261118-204843/node1-events.txt`
- `logs/20261118-204843/node1-rx-chunks.txt`
- `logs/20261118-204843/node1-rx.bin`（41 字节）
- `logs/20261118-204843/node1-tx.bin`（126 字节）
- `logs/20261118-210410/node2-events.txt`
- `logs/20261118-210410/node2-rx-chunks.txt`
- `logs/20261118-210410/node2-rx.bin`（126 字节）
- `logs/20261118-210410/node2-tx.bin`（41 字节）

当天日志：[2026-11-18 双节点 LoRa 互传与 DATA/CRC 验证](../../../docs/ProjectLog/TeamLog/2026-11-18-双节点LoRa互传与DATA-CRC验证.md)。按这些字节重算的对照在[核算说明](../../analysis/2026-11-18-two-node-data-crc.md)。
