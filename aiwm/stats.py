"""战绩统计。

把完美接口的原始响应折成能直接交给模型的结论：什么段位、打什么地图、
什么打法风格、近期的表现。输出是紧凑文本而不是 JSON——模型读文本更省
token，也更容易从中得出有话说的评价。

与营地接口不同，这里的字段名稳定、缺失的维度直接整个键不存在，所以
缺字段一律不出现，不用候选键名挨个试。
"""

from __future__ import annotations

from typing import Any

__all__ = ["段位名", "统计战绩", "汇总文本", "对比要点", "对比文本", "占优项数"]

_保留一位小数 = 1


def _取数(响应: dict[str, Any], 键: str) -> float | None:
    """取一个数值字段，取不到或非数值时返回 None。

    返回 None 而不返回 0：0 是合法数据（「爆头率 0%」确实可能），
    「没有这个字段」不是。混起来模型会把「没这个字段」读成「这项就是 0」。
    """
    值 = 响应.get(键)
    if 值 is None or 值 == "":
        return None
    try:
        return float(值)
    except (TypeError, ValueError):
        return None


def _取整(值: float) -> float:
    return round(值, _保留一位小数)


# 段位分到段位名。
#
# 阈值是照着这个响应的 `rank` 试出来的，没有文档可抄。**这是官匹的分数段，
# 不是完美竞技平台的段位名**——见 `aiwm.来源`。加新的档位得先拿对应分数的
# 真实响应来验。
#
# 一千分以下的分数单独处理：实测同一条 `historyRanks` 序列里出现过 0、13、
# 14 三种小值，它们是未定级与定级赛的标记而不是段位分（这个号当时段位 20620，
# 序列里却夹着这三个值）。具体对应哪个定级赛区间没有依据可查，所以不编，
# 一律显示成「未定级」。
_段位区间 = (
    (1100, 1499, "白银"),
    (1500, 1899, "黄金"),
    (1900, 2299, "大地球"),
    (2300, 2699, "小地球"),
    (2700, 3199, "中地球"),
    (3200, 3999, "大地球精英"),
    (4000, 4999, "超凡大师"),
    (5000, 9999, "宗师"),
    (10000, None, "神话"),
)

# 低于这个分数的不是段位分，是未定级与定级赛的标记值。
_未定级上限 = 1000


def 段位名(分数: float | None) -> str:
    """段位分折成段位名。

    分数缺失或低于一分的返回空串，一千分以下返回「未定级」——照着显示等于
    告诉模型「这人段位 14 分」，而事实是他没定级。
    """
    if 分数 is None or 分数 < 1:
        return ""
    if 分数 < _未定级上限:
        return "未定级"
    for 下限, 上限, 名 in _段位区间:
        if 分数 >= 下限 and (上限 is None or 分数 <= 上限):
            return 名
    return ""


def _百分数(响应: dict[str, Any], 键: str) -> float | None:
    """接口用小数表示比率（0.547 是 54.7%），折成百分数。"""
    值 = _取数(响应, 键)
    return None if 值 is None else _取整(值 * 100)


def _已是百分数(响应: dict[str, Any], 键: str) -> float | None:
    """折成百分数，但字段本身已经是百分数。

    `kast` 是这一类里的唯一一个：其余比率都是 0 到 1 的小数（`winRate`
    0.48、`headShotRatio` 0.547），而 `kast` 直接给 74。套上 `_百分数`
    会算成 7400%。这是拿真实响应量出来的，不是从命名猜的。
    """
    值 = _取数(响应, 键)
    return None if 值 is None else _取整(值)


def _地图池(响应: dict[str, Any]) -> list[dict[str, Any]]:
    """常用地图，附带场次。

    接口的 `hotMaps` 同时给代号（`map`）与中文名（`mapName`），中文名直接用。
    `hotMaps` 不带胜负场次，只有统计值，所以这里不猜胜率。
    """
    结果 = []
    for 项 in 响应.get("hotMaps") or []:
        if not isinstance(项, dict):
            continue
        名 = str(项.get("mapName") or "") or str(项.get("map") or "")
        if not 名:
            continue
        结果.append(
            {
                "地图": 名,
                "场次": int(_取数(项, "totalMatch") or 0),
            }
        )
    return 结果


def _武器池(响应: dict[str, Any], 上限: int = 5) -> list[dict[str, Any]]:
    """常用武器，按击杀数排序。

    爆头数取不到时留 None，由 `汇总文本` 整段省掉，不能填 0——0 会被读成
    「这把枪一个爆头都没有」，而事实是接口没给这个数。
    """
    原始 = [项 for 项 in 响应.get("hotWeapons") or [] if isinstance(项, dict)]
    带名 = [项 for 项 in 原始 if 项.get("weaponName")]
    带名.sort(key=lambda 项: -(_取数(项, "weaponKill") or 0))
    结果 = []
    for 项 in 带名[:上限]:
        爆头 = _取数(项, "weaponHeadShot")
        击杀 = _取数(项, "weaponKill")
        if 击杀 is None:
            continue
        结果.append(
            {
                "武器": str(项["weaponName"]),
                "击杀": int(击杀),
                "爆头": int(爆头) if 爆头 is not None else None,
                "场次": int(_取数(项, "totalMatch") or 0),
            }
        )
    return 结果


def _近十场评分(响应: dict[str, Any]) -> list[float] | None:
    """最近若干场的评分序列。

    接口给的是 `historyRatings`，**不要拿 `historyDates` 跟它配对**：实测
    同一个响应里日期有 100 条（对应 100 场）而评分只有 30 条（对应最近 30 场），
    两者不是一一对应的。而且 `historyRanks` 里混着 0 与 14 这类未定级与定级赛
    的记录，说明序列还会跳过那些场次，按索引对齐会配错。

    所以这里只取评分序列本身，要日期得另找能对齐的来源。
    """
    评分 = 响应.get("historyRatings")
    if not isinstance(评分, list) or not 评分:
        return None
    结果 = []
    for 值 in 评分[:10]:
        try:
            结果.append(float(值))
        except (TypeError, ValueError):
            return None
    return 结果


def 统计战绩(响应: dict[str, Any]) -> dict[str, Any]:
    """把完美接口的响应折成统计结论。

    取不到的维度一律留 None，由 `汇总文本` 决定不显示。

    **`cnt` 与 `historyWinCount` 不是同一个池子**，别拿后者减前者算负场：
    实测 `cnt` 是近期统计场次（100），`historyWinCount` 是生涯累计胜场（679），
    两者量级差得远。100 减 679 会得到负场 0，而胜率 0.48 反推出来的负场是 52。
    所以负场由 `cnt` 与 `winRate` 反算，生涯胜场单独成一个字段。
    """
    场次 = int(_取数(响应, "cnt") or 0)
    胜率 = _百分数(响应, "winRate")

    胜场 = 负场 = None
    if 场次 > 0 and 胜率 is not None:
        胜场 = round(场次 * 胜率 / 100)
        负场 = 场次 - 胜场

    多杀 = {
        "三杀": int(_取数(响应, "k3") or 0),
        "四杀": int(_取数(响应, "k4") or 0),
        "五杀": int(_取数(响应, "k5") or 0),
    }

    return {
        "总场次": 场次,
        "胜场": 胜场,
        "负场": 负场,
        "胜率": 胜率,
        "生涯胜场": int(_取数(响应, "historyWinCount") or 0),
        "KD": _取数(响应, "kd"),
        "Rating": _取数(响应, "rating"),
        "ADR": _取数(响应, "adr"),
        "KAST": _已是百分数(响应, "kast"),
        "RWS": _取数(响应, "rws"),
        "爆头率": _百分数(响应, "headShotRatio"),
        "首杀率": _百分数(响应, "entryKillRatio"),
        "AWP击杀占比": _百分数(响应, "awpKillRatio"),
        "闪光成功率": _百分数(响应, "flashSuccessRatio"),
        "段位分": _取数(响应, "rank"),
        "时长小时": int(_取数(响应, "hours") or 0),
        "多杀": 多杀,
        "地图池": _地图池(响应),
        "武器池": _武器池(响应),
        "近十场评分": _近十场评分(响应),
        "当前连胜": int(_取数(响应, "endingWin") or 0),
        "昵称": str(响应.get("nickName") or ""),
    }


def 汇总文本(统计: dict[str, Any], *, 段位: str = "") -> str:
    """把统计折成给模型读的紧凑文本。

    带不出值的维度直接不出现。这个接口在玩家关闭战绩展示时会返回空壳数据，
    那种情况下只有昵称，正文只说明这一点。
    """
    if not 统计.get("总场次"):
        昵称 = 统计.get("昵称") or ""
        if 昵称:
            return f"{昵称} 的战绩数据是空的。对方可能关闭了战绩展示，或最近没打过排位。"
        return "没有查到可用的战绩数据。"

    行 = []

    头部 = [f"段位 {段位}" if 段位 else "段位未定级"]
    if 统计.get("段位分"):
        头部.append(f"综合分 {int(统计['段位分'])}")
    if 统计.get("胜场") is not None and 统计.get("负场") is not None:
        头部.append(f"统计场次 {统计['总场次']}（{统计['胜场']}胜{统计['负场']}负）")
    else:
        头部.append(f"统计场次 {统计['总场次']}")
    if 统计.get("胜率") is not None:
        头部.append(f"胜率 {统计['胜率']}%")
    行.append(" ｜ ".join(头部))

    if 统计.get("生涯胜场"):
        行.append(f"生涯累计胜场 {统计['生涯胜场']}")

    核心 = []
    if 统计.get("KD") is not None:
        核心.append(f"KD {统计['KD']}")
    if 统计.get("Rating") is not None:
        核心.append(f"Rating {统计['Rating']}")
    if 统计.get("ADR") is not None:
        核心.append(f"ADR {统计['ADR']}")
    if 核心:
        行.append("｜".join(核心))

    深度 = []
    if 统计.get("KAST") is not None:
        深度.append(f"KAST {统计['KAST']}%")
    if 统计.get("爆头率") is not None:
        深度.append(f"爆头率 {统计['爆头率']}%")
    if 统计.get("首杀率") is not None:
        深度.append(f"首杀率 {统计['首杀率']}%")
    if 统计.get("RWS") is not None:
        深度.append(f"RWS {统计['RWS']}")
    if 深度:
        行.append("｜".join(深度))

    特殊 = []
    if 统计.get("AWP击杀占比") is not None:
        特殊.append(f"AWP 击杀占比 {统计['AWP击杀占比']}%")
    if 统计.get("闪光成功率") is not None:
        特殊.append(f"闪光成功率 {统计['闪光成功率']}%")
    if 特殊:
        行.append("｜".join(特殊))

    地图 = [f"{项['地图']} {项['场次']}场" for 项 in 统计.get("地图池") or [] if 项.get("场次")]
    if 地图:
        行.append("常用地图：" + "、".join(地图[:5]))

    武器 = 统计.get("武器池") or []
    武器项 = []
    for 项 in 武器:
        if 项.get("击杀") is None:
            continue
        描述 = f"{项['武器']} {项['击杀']}杀"
        # 爆头数缺了就整段省掉，不能显示「爆头 0」——那会被读成
        # 「这把枪一个爆头都没有」，而事实是接口没给这个数。
        if 项.get("爆头") is not None:
            描述 += f"（爆头 {项['爆头']}）"
        武器项.append(描述)
    if 武器项:
        行.append("常用武器：" + "、".join(武器项))

    多杀 = [f"{名} {数} 次" for 名, 数 in (统计.get("多杀") or {}).items() if 数]
    if 多杀:
        行.append("多杀：" + "、".join(多杀))

    评分 = 统计.get("近十场评分")
    if 评分:
        走势 = " ".join(f"{值:g}" for 值 in 评分)
        行.append(f"最近 {len(评分)} 场评分：{走势}")

    if 统计.get("当前连胜", 0) >= 2:
        行.append(f"当前连胜 {统计['当前连胜']} 场")

    if 统计.get("时长小时"):
        行.append(f"游戏时长 {统计['时长小时']} 小时")

    return "\n".join(行)


def 对比要点(甲: dict[str, Any], 乙: dict[str, Any]) -> list[dict[str, str]]:
    """逐项比出高低。

    返回 `[{"项": ..., "甲": ..., "乙": ..., "优": "甲" | "乙" | "持平"}]`。
    「甲」与「乙」是位置标记，具体是谁由调用方的 `对比文本` 填名字。

    对比**由代码算死，不交给模型**：让模型自己比，它最省事的答案就是「各有千秋」
    这类端水话。每项都算清谁占优、双方数字多少，模型的活只剩解说，端水就没地方藏。
    """
    要点: list[dict[str, str]] = []

    # 有一方没数据就不比。空统计里各项都是 None，逐项比下来会得到一串「持平」，
    # 看着像「两人打得一样好」，其实是「没数据」。
    if not 甲.get("总场次") or not 乙.get("总场次"):
        return 要点

    def 一项(
        标题: str,
        甲值: float | None,
        乙值: float | None,
        *,
        越小越好: bool = False,
        单位: str = "",
        位数: int = 1,
    ) -> None:
        if 甲值 is None or 乙值 is None:
            return
        模板 = f"{{:.{位数}f}}"
        甲文 = 模板.format(甲值) + 单位
        乙文 = 模板.format(乙值) + 单位
        if 甲值 == 乙值:
            优 = "持平"
        else:
            甲赢 = 甲值 < 乙值 if 越小越好 else 甲值 > 乙值
            优 = "甲" if 甲赢 else "乙"
        要点.append({"项": 标题, "甲": 甲文, "乙": 乙文, "优": 优})

    一项("胜率", 甲.get("胜率"), 乙.get("胜率"), 单位="%")
    一项("KD", 甲.get("KD"), 乙.get("KD"))
    一项("Rating", 甲.get("Rating"), 乙.get("Rating"))
    一项("ADR", 甲.get("ADR"), 乙.get("ADR"))
    一项("KAST", 甲.get("KAST"), 乙.get("KAST"), 单位="%")
    一项("爆头率", 甲.get("爆头率"), 乙.get("爆头率"), 单位="%")
    一项("首杀率", 甲.get("首杀率"), 乙.get("首杀率"), 单位="%")
    一项("RWS", 甲.get("RWS"), 乙.get("RWS"))
    一项(
        "近十场平均评分",
        _近十场均值(甲),
        _近十场均值(乙),
    )
    一项("统计场次", float(甲.get("总场次") or 0), float(乙.get("总场次") or 0), 位数=0)
    return 要点


def _近十场均值(统计: dict[str, Any]) -> float | None:
    序列 = 统计.get("近十场评分")
    if not 序列:
        return None
    return _取整(sum(序列) / len(序列))


def 对比文本(要点: list[dict[str, str]], 甲名: str, 乙名: str) -> str:
    """把对比要点折成给模型读的文本。每一行都直接说明谁占优。"""
    行 = []
    for 条 in 要点:
        if 条["优"] == "持平":
            行.append(f"{条['项']}：持平（{甲名} {条['甲']} / {乙名} {条['乙']}）")
        else:
            优名 = 甲名 if 条["优"] == "甲" else 乙名
            行.append(f"{条['项']}：{优名}占优（{甲名} {条['甲']} / {乙名} {条['乙']}）")
    return "\n".join(行)


def 占优项数(要点: list[dict[str, str]], 甲名: str, 乙名: str) -> str:
    """「asd 5 项、老王 2 项」这样的汇总，写进提示里当参考。

    刻意**不**把它写成「占优多的一方必须赢」：项数是机械数出来的，而实际谁更强
    要看是哪几项——输赢判断留给模型，这里只提供事实。
    """
    甲 = sum(1 for 条 in 要点 if 条["优"] == "甲")
    乙 = sum(1 for 条 in 要点 if 条["优"] == "乙")
    return f"{甲名} {甲} 项、{乙名} {乙} 项"
