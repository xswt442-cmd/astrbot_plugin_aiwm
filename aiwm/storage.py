"""绑定信息的本地存储。

一个 Bot 用户绑一个 steamid64。完美接口查战绩不需要登录态，所以存的就只有
这个 id 与绑定时记下的平台显示名。

文件内容不进日志、不进异常消息。解绑时删文件，不保留。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

__all__ = ["凭据仓库", "校验steamid", "取有效steamid", "提取steamid", "怎么找steamid"]

_文件名后缀 = ".json"

# steamid64 是 17 位十进制，首位固定为 7（Steam 的 64 位账号空间）。
# 不要对中间的数字位做额外限制：`76561198` 是所有 64 位账号的共同前缀，
# 后面那一位是账号编号本身，取值本就多样。
_steamid格式 = re.compile(r"^7\d{16}$")

# 从一段文本里捞 steamid64。两侧各留一位边界，免得把 18 位以上的长数字
# 从中间截出一段 17 位来——那会是个看起来合法、实际是别人的号。
# 前边界排除数字与小数点，后边界同理。
_文本里的steamid = re.compile(r"(?<![\d.])7\d{16}(?![\d.])")

_怎么找 = (
    "在 Steam 客户端点开你的个人资料，浏览器地址栏最后那串数字就是。\n"
    "或者直接把你 Steam 个人资料页的网址发我，我从里面取。"
)


def 校验steamid(候选: str) -> bool:
    """判断一个字符串是不是形式上合法的 steamid64。

    只做形式校验：位数与首位。它挡得住「手打少一位」「贴了个昵称」这类
    常见错误，但挡不住格式合法却不存在的号——那种要等接口回应才知道。
    """
    文本 = (候选 or "").strip()
    return bool(_steamid格式.fullmatch(文本))


def 提取steamid(原文: str) -> list[str]:
    """从任意文本里找出所有 steamid64，按出现顺序、去重。

    用户手上本来就有含这串数字的东西——Steam 个人资料页网址、启动器
    参数 `-login 76561198…`、聊天记录里提过的号。让他自己从里面挑出 17 位
    数字抄一遍容易抄错，让他把原文贴过来更省事。
    """
    找到 = _文本里的steamid.findall(原文 or "")
    去重: list[str] = []
    for 号 in 找到:
        if 号 not in 去重:
            去重.append(号)
    return 去重


def 怎么找steamid() -> str:
    """提取不到时给用户的指引。"""
    return _怎么找


def 取有效steamid(候选: str) -> str:
    """从用户给的内容里取出 steamid64，取不到或有多个时抛错。

    接受任意文本，不要求用户自己从里面挑出那 17 位数字：Steam 个人资料页
    网址、启动器参数、含这串数字的聊天记录都能直接粘过来。

    找到多个时不猜——那多半是用户粘了一堆东西，让他说清要哪个。
    """
    文本 = (候选 or "").strip()
    if 校验steamid(文本):
        return 文本

    找到 = 提取steamid(文本)
    if len(找到) == 1:
        return 找到[0]
    if len(找到) > 1:
        可选 = "、".join(找到[:5])
        raise ValueError(
            f"你给的内容里有好几个 steamid：{可选}\n只发一个就行，比如只发 Steam 个人资料页的网址。"
        )

    显示 = 文本 if len(文本) <= 40 else f"{文本[:40]}…"
    raise ValueError(
        f"「{显示}」里没找到 steamid64。\n"
        "它是一串 17 位数字、以 7 开头，例如 76561198159976336。\n"
        f"{_怎么找}"
    )


class 凭据仓库:
    def __init__(self, 目录: Path) -> None:
        self.目录 = 目录

    def 路径(self, 用户: str) -> Path:
        """用户标识不直接当文件名——QQ 号可能带@和斜杠。取摘要即可。"""
        摘要 = hashlib.sha256(用户.encode("utf-8")).hexdigest()[:32]
        return self.目录 / f"{摘要}{_文件名后缀}"

    def 读取(self, 用户: str) -> dict[str, Any] | None:
        路径 = self.路径(用户)
        try:
            载荷 = json.loads(路径.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(载荷, dict):
            return None
        if not 校验steamid(str(载荷.get("steamid", ""))):
            return None
        return 载荷

    def 写入(self, 用户: str, steamid: str, *, 昵称: str = "") -> None:
        self.目录.mkdir(parents=True, exist_ok=True)
        路径 = self.路径(用户)
        # 顺手把用户标识与昵称一起存下来。文件名是标识的哈希，反推不回去，
        # 而 PK 要按昵称找人、再拿 steamid 去查战绩，两样都得在文件里。
        载荷 = {"steamid": steamid, "昵称": 昵称, "用户": 用户}
        路径.write_text(json.dumps(载荷, ensure_ascii=False), encoding="utf-8")
        if os.name == "posix":
            路径.chmod(0o600)

    def 全部(self) -> list[dict[str, Any]]:
        """所有已绑定的记录。损坏或字段不全的文件直接跳过。"""
        try:
            文件们 = sorted(self.目录.glob(f"*{_文件名后缀}"))
        except OSError:
            return []

        结果 = []
        for 路径 in 文件们:
            try:
                载荷 = json.loads(路径.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(载荷, dict) and 校验steamid(str(载荷.get("steamid", ""))):
                结果.append(载荷)
        return 结果

    def 按昵称找(self, 昵称: str) -> list[dict[str, Any]]:
        """按平台显示名找人。完全命中优先，其次是不区分大小写的子串。

        走这条路是因为 QQ 官方平台拿不到被 @ 的人的标识：适配器只把「@机器人」
        转成组件，@别人在事件里连痕迹都没有（实测组件与正文都为空）。所以群里
        PK 只能靠名字点人。
        """
        目标 = (昵称 or "").strip().lower()
        if not 目标:
            return []
        记录们 = self.全部()
        精确 = [记录 for 记录 in 记录们 if str(记录.get("昵称", "")).strip().lower() == 目标]
        if 精确:
            return 精确
        return [记录 for 记录 in 记录们 if 目标 in str(记录.get("昵称", "")).strip().lower()]

    def 删除(self, 用户: str) -> dict[str, Any] | None:
        记录 = self.读取(用户)
        if 记录 is None:
            return None
        try:
            self.路径(用户).unlink()
        except OSError:
            return None
        return 记录
