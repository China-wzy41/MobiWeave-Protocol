"""mwlog —— 日志 V1 的读取与聚合（纯逻辑，不依赖界面）。

界面、自检、以后的串口实时输入都复用这里的两个函数：
    load_file(path)  -> LoadResult   # 文件 → 记录 + 问题行
    build(loaded)    -> ViewState    # 记录 → 节点 / 消息 / 链路
"""

from .records import (LogError, Issue, LoadResult, MessageId, Record, load_file,
                      load_lines, parse_line)
from .state import (DEFAULT_T_DOWN_MS, LinkView, MessageView, NodeView, TimelineRow,
                    ViewState, build)

__all__ = [
    "LogError", "Issue", "LoadResult", "MessageId", "Record",
    "load_file", "load_lines", "parse_line",
    "DEFAULT_T_DOWN_MS", "LinkView", "MessageView", "NodeView", "TimelineRow",
    "ViewState", "build",
]
