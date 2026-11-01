"""PK 的目标解析。

对手标识从消息里捡，两处按可靠性排：

1. `At` 组件 —— 多数平台会把 @ 转成组件，`qq` 就是用户标识。
2. 正文里的 `<@!openid>` —— QQ 官方适配器只把「@机器人」转成组件，@别人
   会原样留在正文里，只能从文本里抠。

QQ 官方平台上这两处都拿不到别人的标识：适配器只把「@机器人」转成组件，而
被 @ 的人的 mention 留在平台的 `mentions` 里适配器根本不读。所以 `main.py`
里还有一条按昵称找记录的路径，那条才是实际能走通的。

没有第三种兜底：`main.py` 传进来的文本是命令参数与消息正文的拼接，结果总
带空格，与标识的正则永远不匹配。
"""

from __future__ import annotations

import re

__all__ = ["find_opponent", "FAKE_MENTION_IDS"]

# `<@1234>` 与 `<@!1234>` 两种写法都存在。长度下限用来滤掉 `<@1>` 这类噪声。
_MENTION_IN_TEXT = re.compile(r"<@!?([A-Za-z0-9_-]{6,})>")

# 这些值在 At.qq 里出现过，都不是真实用户。
FAKE_MENTION_IDS = frozenset({"qq_official", "all", "unknown_selfid"})


def _usable(candidate: str, excluded: set[str]) -> bool:
    return bool(candidate) and candidate not in FAKE_MENTION_IDS and candidate not in excluded


def find_opponent(components, text: str, *, me: str = "", bot_id: str = "") -> str | None:
    """从消息里找出 PK 的对手标识，找不到返回 None。

    `自己` 与 `机器人` 都得排掉：群里 @机器人 同样会生成一个 At 组件，
    不排掉的话「@机器人 PK @小明」会把机器人当成 PK 对象。
    """
    excluded = {value for value in (me, bot_id) if value}

    for component in components or []:
        candidate = getattr(component, "qq", None)
        if candidate is None:
            continue
        candidate = str(candidate)
        if _usable(candidate, excluded):
            return candidate

    for hit in _MENTION_IN_TEXT.finditer(text or ""):
        candidate = hit.group(1)
        if _usable(candidate, excluded):
            return candidate

    return None
