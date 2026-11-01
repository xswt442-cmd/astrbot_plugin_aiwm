"""战绩统计。

把完美接口的原始响应折成能直接交给模型的结论：什么段位、打什么地图、
什么打法风格、近期的表现。输出是紧凑文本而不是 JSON——模型读文本更省
token，也更容易从中得出有话说的评价。

与营地接口不同，这里的字段名稳定、缺失的维度直接整个键不存在，所以
缺字段一律不出现，不用候选键名挨个试。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "tier_name",
    "summarize",
    "summary_text",
    "contrast_points",
    "contrast_text",
    "advantage_count",
]

_ONE_DECIMAL = 1


def _number(response: dict[str, Any], key: str) -> float | None:
    """取一个数值字段，取不到或非数值时返回 None。

    返回 None 而不返回 0：0 是合法数据（「爆头率 0%」确实可能），
    「没有这个字段」不是。混起来模型会把「没这个字段」读成「这项就是 0」。
    """
    value = response.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round1(value: float) -> float:
    return round(value, _ONE_DECIMAL)


# 段位分到段位名。
#
# 阈值是照着这个响应的 `rank` 试出来的，没有文档可抄。**这是官匹的分数段，
# 不是完美竞技平台的段位名**——见 `aiwm.source`。加新的档位得先拿对应分数的
# 真实响应来验。
#
# 一千分以下的分数单独处理：实测同一条 `historyRanks` 序列里出现过 0、13、
# 14 三种小值，它们是未定级与定级赛的标记而不是段位分（这个号当时段位 20620，
# 序列里却夹着这三个值）。具体对应哪个定级赛区间没有依据可查，所以不编，
# 一律显示成「未定级」。
_TIER_RANGES = (
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
_UNRANKED_CAP = 1000


def tier_name(score: float | None) -> str:
    """段位分折成段位名。

    分数缺失或低于一分的返回空串，一千分以下返回「未定级」——照着显示等于
    告诉模型「这人段位 14 分」，而事实是他没定级。
    """
    if score is None or score < 1:
        return ""
    if score < _UNRANKED_CAP:
        return "未定级"
    for floor, cap, name in _TIER_RANGES:
        if score >= floor and (cap is None or score <= cap):
            return name
    return ""


def _percent(response: dict[str, Any], key: str) -> float | None:
    """接口用小数表示比率（0.547 是 54.7%），折成百分数。"""
    value = _number(response, key)
    return None if value is None else _round1(value * 100)


def _ALREADY_PERCENT(response: dict[str, Any], key: str) -> float | None:
    """折成百分数，但字段本身已经是百分数。

    `kast` 是这一类里的唯一一个：其余比率都是 0 到 1 的小数（`winRate`
    0.48、`headShotRatio` 0.547），而 `kast` 直接给 74。套上 `_百分数`
    会算成 7400%。这是拿真实响应量出来的，不是从命名猜的。
    """
    value = _number(response, key)
    return None if value is None else _round1(value)


def _MAP_POOL(response: dict[str, Any]) -> list[dict[str, Any]]:
    """常用地图，附带场次。

    接口的 `hotMaps` 同时给代号（`map`）与中文名（`mapName`），中文名直接用。
    `hotMaps` 不带胜负场次，只有统计值，所以这里不猜胜率。
    """
    result = []
    for item in response.get("hotMaps") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("mapName") or "") or str(item.get("map") or "")
        if not name:
            continue
        result.append(
            {
                "地图": name,
                "场次": int(_number(item, "totalMatch") or 0),
            }
        )
    return result


def _WEAPON_POOL(response: dict[str, Any], cap: int = 5) -> list[dict[str, Any]]:
    """常用武器，按击杀数排序。

    爆头数取不到时留 None，由 `汇总文本` 整段省掉，不能填 0——0 会被读成
    「这把枪一个爆头都没有」，而事实是接口没给这个数。
    """
    raw = [item for item in response.get("hotWeapons") or [] if isinstance(item, dict)]
    with_name = [item for item in raw if item.get("weaponName")]
    with_name.sort(key=lambda item: -(_number(item, "weaponKill") or 0))
    result = []
    for item in with_name[:cap]:
        headshot = _number(item, "weaponHeadShot")
        kills = _number(item, "weaponKill")
        if kills is None:
            continue
        result.append(
            {
                "武器": str(item["weaponName"]),
                "击杀": int(kills),
                "爆头": int(headshot) if headshot is not None else None,
                "场次": int(_number(item, "totalMatch") or 0),
            }
        )
    return result


def _RECENT_RATINGS(response: dict[str, Any]) -> list[float] | None:
    """最近若干场的评分序列。

    接口给的是 `historyRatings`，**不要拿 `historyDates` 跟它配对**：实测
    同一个响应里日期有 100 条（对应 100 场）而评分只有 30 条（对应最近 30 场），
    两者不是一一对应的。而且 `historyRanks` 里混着 0 与 14 这类未定级与定级赛
    的记录，说明序列还会跳过那些场次，按索引对齐会配错。

    所以这里只取评分序列本身，要日期得另找能对齐的来源。
    """
    rating = response.get("historyRatings")
    if not isinstance(rating, list) or not rating:
        return None
    result = []
    for value in rating[:10]:
        try:
            result.append(float(value))
        except (TypeError, ValueError):
            return None
    return result


def summarize(response: dict[str, Any]) -> dict[str, Any]:
    """把完美接口的响应折成统计结论。

    取不到的维度一律留 None，由 `汇总文本` 决定不显示。

    **`cnt` 与 `historyWinCount` 不是同一个池子**，别拿后者减前者算负场：
    实测 `cnt` 是近期统计场次（100），`historyWinCount` 是生涯累计胜场（679），
    两者量级差得远。100 减 679 会得到负场 0，而胜率 0.48 反推出来的负场是 52。
    所以负场由 `cnt` 与 `winRate` 反算，生涯胜场单独成一个字段。
    """
    matches = int(_number(response, "cnt") or 0)
    win_rate = _percent(response, "winRate")

    wins = losses = None
    if matches > 0 and win_rate is not None:
        wins = round(matches * win_rate / 100)
        losses = matches - wins

    multi_kills = {
        "三杀": int(_number(response, "k3") or 0),
        "四杀": int(_number(response, "k4") or 0),
        "五杀": int(_number(response, "k5") or 0),
    }

    return {
        "总场次": matches,
        "胜场": wins,
        "负场": losses,
        "胜率": win_rate,
        "生涯胜场": int(_number(response, "historyWinCount") or 0),
        "KD": _number(response, "kd"),
        "Rating": _number(response, "rating"),
        "ADR": _number(response, "adr"),
        "KAST": _ALREADY_PERCENT(response, "kast"),
        "RWS": _number(response, "rws"),
        "爆头率": _percent(response, "headShotRatio"),
        "首杀率": _percent(response, "entryKillRatio"),
        "AWP击杀占比": _percent(response, "awpKillRatio"),
        "闪光成功率": _percent(response, "flashSuccessRatio"),
        "段位分": _number(response, "rank"),
        "时长小时": int(_number(response, "hours") or 0),
        "多杀": multi_kills,
        "地图池": _MAP_POOL(response),
        "武器池": _WEAPON_POOL(response),
        "近十场评分": _RECENT_RATINGS(response),
        "当前连胜": int(_number(response, "endingWin") or 0),
        "昵称": str(response.get("nickName") or ""),
    }


def summary_text(stats: dict[str, Any], *, tier: str = "") -> str:
    """把统计折成给模型读的紧凑文本。

    带不出值的维度直接不出现。这个接口在玩家关闭战绩展示时会返回空壳数据，
    那种情况下只有昵称，正文只说明这一点。
    """
    if not stats.get("总场次"):
        nickname = stats.get("昵称") or ""
        if nickname:
            return f"{nickname} 的战绩数据是空的。对方可能关闭了战绩展示，或最近没打过排位。"
        return "没有查到可用的战绩数据。"

    lines = []

    head = [f"段位 {tier}" if tier else "段位未定级"]
    if stats.get("段位分"):
        head.append(f"综合分 {int(stats['段位分'])}")
    if stats.get("胜场") is not None and stats.get("负场") is not None:
        head.append(f"统计场次 {stats['总场次']}（{stats['胜场']}胜{stats['负场']}负）")
    else:
        head.append(f"统计场次 {stats['总场次']}")
    if stats.get("胜率") is not None:
        head.append(f"胜率 {stats['胜率']}%")
    lines.append(" ｜ ".join(head))

    if stats.get("生涯胜场"):
        lines.append(f"生涯累计胜场 {stats['生涯胜场']}")

    core = []
    if stats.get("KD") is not None:
        core.append(f"KD {stats['KD']}")
    if stats.get("Rating") is not None:
        core.append(f"Rating {stats['Rating']}")
    if stats.get("ADR") is not None:
        core.append(f"ADR {stats['ADR']}")
    if core:
        lines.append("｜".join(core))

    depth = []
    if stats.get("KAST") is not None:
        depth.append(f"KAST {stats['KAST']}%")
    if stats.get("爆头率") is not None:
        depth.append(f"爆头率 {stats['爆头率']}%")
    if stats.get("首杀率") is not None:
        depth.append(f"首杀率 {stats['首杀率']}%")
    if stats.get("RWS") is not None:
        depth.append(f"RWS {stats['RWS']}")
    if depth:
        lines.append("｜".join(depth))

    special = []
    if stats.get("AWP击杀占比") is not None:
        special.append(f"AWP 击杀占比 {stats['AWP击杀占比']}%")
    if stats.get("闪光成功率") is not None:
        special.append(f"闪光成功率 {stats['闪光成功率']}%")
    if special:
        lines.append("｜".join(special))

    map_name = [
        f"{item['地图']} {item['场次']}场" for item in stats.get("地图池") or [] if item.get("场次")
    ]
    if map_name:
        lines.append("常用地图：" + "、".join(map_name[:5]))

    weapon = stats.get("武器池") or []
    weapon_stat = []
    for item in weapon:
        if item.get("击杀") is None:
            continue
        label = f"{item['武器']} {item['击杀']}杀"
        # 爆头数缺了就整段省掉，不能显示「爆头 0」——那会被读成
        # 「这把枪一个爆头都没有」，而事实是接口没给这个数。
        if item.get("爆头") is not None:
            label += f"（爆头 {item['爆头']}）"
        weapon_stat.append(label)
    if weapon_stat:
        lines.append("常用武器：" + "、".join(weapon_stat))

    multi_kills = [
        f"{name} {count} 次" for name, count in (stats.get("多杀") or {}).items() if count
    ]
    if multi_kills:
        lines.append("多杀：" + "、".join(multi_kills))

    rating = stats.get("近十场评分")
    if rating:
        form = " ".join(f"{value:g}" for value in rating)
        lines.append(f"最近 {len(rating)} 场评分：{form}")

    if stats.get("当前连胜", 0) >= 2:
        lines.append(f"当前连胜 {stats['当前连胜']} 场")

    if stats.get("时长小时"):
        lines.append(f"游戏时长 {stats['时长小时']} 小时")

    return "\n".join(lines)


def contrast_points(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, str]]:
    """逐项比出高低。

    返回 `[{"项": ..., "甲": ..., "乙": ..., "优": "甲" | "乙" | "持平"}]`。
    「甲」与「乙」是位置标记，具体是谁由调用方的 `对比文本` 填名字。

    对比**由代码算死，不交给模型**：让模型自己比，它最省事的答案就是「各有千秋」
    这类端水话。每项都算清谁占优、双方数字多少，模型的活只剩解说，端水就没地方藏。
    """
    points: list[dict[str, str]] = []

    # 有一方没数据就不比。空统计里各项都是 None，逐项比下来会得到一串「持平」，
    # 看着像「两人打得一样好」，其实是「没数据」。
    if not a.get("总场次") or not b.get("总场次"):
        return points

    def add_point(
        title: str,
        value_a: float | None,
        value_b: float | None,
        *,
        lower_is_better: bool = False,
        unit: str = "",
        digits: int = 1,
    ) -> None:
        if value_a is None or value_b is None:
            return
        template = f"{{:.{digits}f}}"
        text_a = template.format(value_a) + unit
        text_b = template.format(value_b) + unit
        if value_a == value_b:
            winner = "持平"
        else:
            a_wins = value_a < value_b if lower_is_better else value_a > value_b
            winner = "甲" if a_wins else "乙"
        points.append({"项": title, "甲": text_a, "乙": text_b, "优": winner})

    add_point("胜率", a.get("胜率"), b.get("胜率"), unit="%")
    add_point("KD", a.get("KD"), b.get("KD"))
    add_point("Rating", a.get("Rating"), b.get("Rating"))
    add_point("ADR", a.get("ADR"), b.get("ADR"))
    add_point("KAST", a.get("KAST"), b.get("KAST"), unit="%")
    add_point("爆头率", a.get("爆头率"), b.get("爆头率"), unit="%")
    add_point("首杀率", a.get("首杀率"), b.get("首杀率"), unit="%")
    add_point("RWS", a.get("RWS"), b.get("RWS"))
    add_point(
        "近十场平均评分",
        _RECENT_MEAN(a),
        _RECENT_MEAN(b),
    )
    add_point("统计场次", float(a.get("总场次") or 0), float(b.get("总场次") or 0), digits=0)
    return points


def _RECENT_MEAN(stats: dict[str, Any]) -> float | None:
    sequence = stats.get("近十场评分")
    if not sequence:
        return None
    return _round1(sum(sequence) / len(sequence))


def contrast_text(points: list[dict[str, str]], name_a: str, name_b: str) -> str:
    """把对比要点折成给模型读的文本。每一行都直接说明谁占优。"""
    lines = []
    for line in points:
        if line["优"] == "持平":
            lines.append(f"{line['项']}：持平（{name_a} {line['甲']} / {name_b} {line['乙']}）")
        else:
            winner_name = name_a if line["优"] == "甲" else name_b
            lines.append(
                f"{line['项']}：{winner_name}占优（{name_a} {line['甲']} / {name_b} {line['乙']}）"
            )
    return "\n".join(lines)


def advantage_count(points: list[dict[str, str]], name_a: str, name_b: str) -> str:
    """「asd 5 项、老王 2 项」这样的汇总，写进提示里当参考。

    刻意**不**把它写成「占优多的一方必须赢」：项数是机械数出来的，而实际谁更强
    要看是哪几项——输赢判断留给模型，这里只提供事实。
    """
    a = sum(1 for line in points if line["优"] == "甲")
    b = sum(1 for line in points if line["优"] == "乙")
    return f"{name_a} {a} 项、{name_b} {b} 项"
