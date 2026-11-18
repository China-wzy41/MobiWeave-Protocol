# 工程日志

这个目录只放工程日志。实验方法在 [method](../method/README.md)。原始实验数据仍放 `Tests/raw` 和 `Tests/analysis`，不要写进这里。

每人一个文件夹，名字是角色字母加姓名缩写。这是暂时分工，以后可以改。角色职责来自仓库 [README](../../README.md) 的「五人分工」和 [11 月首轮计划](../planning/first-month.md)。称呼是团队确认的叫法。账号列是在本仓库直接共创者里核对后的登录名。

| 目录 | 角色 | 职责 | 称呼 | 仓库账号 |
|---|---|---|---|---|
| [A_wzy](A_wzy/) | A | 硬件与集成 | wzy | [@China-wzy41](https://github.com/China-wzy41) |
| [B_hsr](B_hsr/) | B | 通信协议 | yanis | [@Yanis0118](https://github.com/Yanis0118) |
| [C_ygh](C_ygh/) | C | 数据／孪生／实验 | 2439 | [@2439345776-create](https://github.com/2439345776-create) |
| [D_wzx](D_wzx/) | D | 上位机／可视化 | sisimoean | [@Sisimoean](https://github.com/Sisimoean) |
| [E_wyc](E_wyc/) | E | 项目／场景／市场 | StevenWu | [@Stevenwu312](https://github.com/Stevenwu312) |

只把自己的日志放进自己的目录。不知道是谁写的日志不要猜人，先留在 `ProjectLog` 根下并注明原位置和归属待确认。

## 团队日志

[TeamLog](TeamLog/Readme) 放当天共同实验，和上面的成员目录分开。同一篇不复制到个人目录。2026-11-18：[双节点 LoRa 互传与 DATA/CRC 验证](TeamLog/2026-11-18-双节点LoRa互传与DATA-CRC验证.md)。

## 怎么写

文件名：`YYYY-MM-DD-当日工作简述.md`。

一级标题写日期加当日工作简述。正文只用这三节：

```md
# YYYY-MM-DD 当日工作简述

## 当日成果

已验证的事实。没测过的不要写成完成。

## 注意事项

以后还能用的接法、命令和限制。

## 待办

还没做完的事。
```

当日成果只写已经核对过的结果。注意事项写可以重复使用的经验。待办写未完成项。不要按分钟记开工和排查流水。未测和已测分开写。
