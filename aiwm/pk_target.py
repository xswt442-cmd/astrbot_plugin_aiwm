"""PK 的对手从参数里怎么来。

对手有三种给法，从省事到麻烦：

1. **直接给 steamid 或含它的东西**——网址、启动器参数、纯数字都能用。
   对方不用绑定、也不用设 PK 名字。
2. **@ 组件** —— 多数平台会把 @ 转成组件。
3. **绑定时记下的 PK 名字** —— QQ 官方平台上 @ 别人拿不到标识（适配器只把
   「@机器人」转成组件，被 @ 的人的 mention 留在平台 `mentions` 里适配器
   根本不读），所以昵称那条是实际能走通的路径。

第 1 条是关键：实测用户发了 Steam 个人资料页链接想 PK，但当时对方必须先
绑定才行，于是整件事没成。现在从参数里直接抠 steamid，抠到就直接查。
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["OpponentSource", "looks_like_steamid", "resolve_opponent", "looks_like_id_text"]

# steamid64 是 17 位数字、以 7 开头。两侧留边界，免得从更长的数字里截一段。
_STEAMID = re.compile(r"(?<![\d.])7\d{16}(?![\d.])")

# 至少一个数字，且不是纯中文昵称。用来区分「这是不是个 id 之类的东西」。
_LOOKS_LIKE_ID = re.compile(r"[0-9A-Za-z:/\\._-]")


class OpponentSource:
    """对手是怎么指定的。给日志与测试看，不影响行为。"""

    FROM_ARG = "参数"
    FROM_AT = "At组件"
    FROM_NICKNAME = "昵称"
    NOT_FOUND = "没找到"


def looks_like_steamid(arg: str) -> str | None:
    """参数里有没有 steamid64，有就返回，没有返回 `None`。

    用户发来的东西五花八门：纯数字、Steam 个人资料页网址、启动器参数、
    也可能是一句「跟老王比」混着数字。只认得其中藏着的 steamid，其余交给
    昵称那条路。
    """
    text = (arg or "").strip()
    if not text:
        return None

    found = _STEAMID.findall(text)
    if len(found) == 1:
        return found[0]
    # 多个 id 时不猜——那多半是粘了一堆东西，让用户说清要哪个。
    return None


def resolve_opponent(
    arg: str,
    at_id: str | None,
    find_by_nickname,
) -> tuple[str, str, dict[str, Any] | None]:
    """定出 PK 的对手，返回 (steamid, 来源, 用到的记录)。

    `按昵称找` 是个函数：吃昵称、返回 (命中数, 记录)。传进来是为了这个模块
    不依赖 `storage`，能单独跑测试。

    返回的记录只在走昵称那条路时非空——那时记着对方绑定的用户标识，用来判
    「是不是跟自己 PK」。
    """
    steamid = looks_like_steamid(arg)
    if steamid:
        return steamid, OpponentSource.FROM_ARG, None

    if at_id:
        return at_id, OpponentSource.FROM_AT, None

    hit_count, record = find_by_nickname(arg or "")
    if record:
        return str(record["steamid"]), OpponentSource.FROM_NICKNAME, record

    return "", OpponentSource.NOT_FOUND, None


def looks_like_id_text(arg: str) -> bool:
    """参数里有没有数字、字母这类字符。

    用户发「跟小明比」是昵称那条路，发「76561198829920790」是 id 那条路。
    报错时要说清该发什么，靠的就是这个判断。
    """
    return bool(_LOOKS_LIKE_ID.search(arg or ""))
