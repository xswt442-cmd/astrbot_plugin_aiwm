"""字段名与量纲的核对规则。

构造数据里代表「字段名与量纲」的那些字段，真实响应与它对不上就说明接口改版了。
`test/verify_wmpvp.py` 打真实接口后调这里核对，`test/test_verify_rules.py`
拿构造出来的响应验核对规则本身——包括「接口改版时它会不会报出来」。

单独放一个模块而不是塞在脚本里，是因为脚本末尾会 `sys.exit`，import 进来
会直接退出，没法测。
"""

from __future__ import annotations

from typing import Any

__all__ = ["核对", "构造数据"]

# 只挑量纲明确的字段。`nickName`、`avatar`、`hours` 这类具体值本来就因人而异，
# 拿来比会一直报差异，所以它们的缺失靠 `_必填字段` 单独盯。
_要比量纲 = {
    "cnt": 100,
    "winRate": 0.48,
    # `kast` 给的是 74 而不是 0.74，是上次照着名字想当然踩出来的。
    # 接口哪天把它改成小数，这里会报出来。
    "kast": 74,
    "kd": 1.24,
    "headShotRatio": 0.547,
    "entryKillRatio": 0.17,
    "awpKillRatio": 0.05,
    "flashSuccessRatio": 0.57,
}

_必填字段 = ("nickName", "hotMaps", "hotWeapons", "historyRatings", "historyDates", "rank")

# 构造数据与录快照时那个号不同，值不必相等，只要求同一量级（十倍以内）。
_同量级倍数 = 10


def 构造数据() -> dict[str, Any]:
    """一份字段名与量纲都与真实接口一致的样例响应。

    和 `test/test_stats.py` 里的 `_完整响应` 是同一套量纲——那两处要一起改。
    """
    return {
        "steamId": "76561198000000000",
        "nickName": "示例昵称",
        "cnt": 100,
        "historyWinCount": 679,
        "winRate": 0.48,
        "kd": 1.24,
        "rating": 1.21,
        "adr": 95.64,
        "kast": 74,
        "rws": 12.07,
        "headShotRatio": 0.547,
        "entryKillRatio": 0.17,
        "awpKillRatio": 0.05,
        "flashSuccessRatio": 0.57,
        "rank": 20620,
        "endingWin": 44,
        "hours": 1188,
        "hotMaps": [{"map": "de_ancient", "mapName": "远古遗迹", "totalMatch": 24}],
        "hotWeapons": [{"weaponName": "AK47", "weaponKill": 753, "weaponHeadShot": 444}],
        "historyRatings": [2.19, 0.94, 0.66, 1.24, 1.58],
        "historyDates": ["2026-10-01 20:00:00"] * 100,
    }


def _是同量级(真实: float, 构造: float) -> bool:
    if 构造 == 0:
        return 真实 == 0
    比 = abs(真实 / 构造)
    return 1 / _同量级倍数 <= 比 <= _同量级倍数


def 核对(响应: dict[str, Any]) -> list[str]:
    """返回问题清单，空列表表示一切正常。"""
    问题: list[str] = []

    for 键, 构造 in _要比量纲.items():
        真实 = 响应.get(键)
        if 真实 is None:
            问题.append(f"{键}：接口没返回这个字段了")
            continue
        # 数字变成字符串是改版的迹象，别让它蒙混过关。`float("1.24")` 会成功，
        # 所以只在 isinstance 判一下就够，不用真去转。
        if isinstance(真实, bool) or not isinstance(真实, int | float):
            问题.append(f"{键}：期望数字，接口给的是 {真实!r}")
            continue
        真实值 = float(真实)
        if not _是同量级(真实值, 构造):
            问题.append(
                f"{键}：量纲变了。构造数据按 {构造} 写的，接口现在给 {真实值}\n"
                f"    → 改 test/test_stats.py 的 _完整响应，并核对 {键} 的换算"
            )

    for 键 in _必填字段:
        if not 响应.get(键):
            问题.append(f"{键}：接口没返回，或返回了空值")

    # 这两个字段的语义互换了是个真会发生的坑：拿 historyWinCount 去减 cnt
    # 算负场会得到 0，而 cnt 乘胜率反推是对的。所以单独盯住它们的关系。
    场次 = 响应.get("cnt")
    生涯胜场 = 响应.get("historyWinCount")
    if isinstance(场次, int) and isinstance(生涯胜场, int) and 生涯胜场 < 场次:
        问题.append(
            f"historyWinCount({生涯胜场}) 小于 cnt({场次})。\n"
            "    → 两个字段的语义可能互换了，负场的算法要重新核"
        )

    return 问题
