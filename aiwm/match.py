"""「开一局」的对局设定。

这一局是**推演出来的，不是真实战绩**。所有数字都由这里用随机数生成，不让模型
自己编——模型编的数字既不服从概率，看起来也不像真人。

随机的东西要贴近真人：击杀数不能均匀分布，团队获胜的局个人表现一般不会太拉，
评级在一局里的起伏比分数小。
"""

from __future__ import annotations

import random
from typing import Any

__all__ = [
    "build_match_setup",
    "setup_text",
    "skill_profile",
    "pick_map",
    "pick_weapon",
    "WEAPON_CATEGORIES",
]

# 完美平台在 CS2 里的地图。挑的是玩家真会遇到的池子，不含竞技模式专属图。
MAP_POOL = (
    "远古遗迹",
    "炼狱小镇",
    "荒漠迷城",
    "核子危机",
    "死城之谜",
    "列车停放站",
    "古堡激战",
    "炼狱小镇",
)

# 武器按类别给命中率区间，用同一套逻辑派生出这一局的命中与爆头数。
WEAPON_CATEGORIES = {
    "AK47": (0.28, 0.42),
    "M4A4": (0.26, 0.40),
    "M4A1消音型": (0.30, 0.44),
    "AWP": (0.62, 0.80),
    "大地球": (0.72, 0.90),
    "沙漠之鹰": (0.30, 0.46),
    "P250": (0.24, 0.38),
    "Tec-9": (0.25, 0.40),
    "MP9": (0.24, 0.38),
    "UMP-45": (0.26, 0.40),
    "Nova": (0.20, 0.34),
    "XM1014": (0.18, 0.32),
}

# 手枪在残局与下ECO局才会拿得比较显眼，整局里权重低一些。
WEAPON_WEIGHTS = {
    "AK47": 10,
    "M4A4": 9,
    "M4A1消音型": 8,
    "AWP": 6,
    "大地球": 4,
    "沙漠之鹰": 3,
    "MP9": 3,
    "Tec-9": 3,
    "UMP-45": 3,
    "P250": 2,
    "Nova": 2,
    "XM1014": 2,
}

# 段位分到大致水平。人一局里的表现不会脱离自己的水平太多。
TIER_RANGES = (
    (1000, 6000, "白银到黄金段"),
    (6000, 12000, "大地球到传奇段"),
    (12000, 20000, "传奇到神话段"),
    (20000, 28000, "神话到超凡段"),
)


def _weighted_pick(rng: random.Random, weight_table: dict[str, int]) -> str:
    names = list(weight_table)
    weights = [weight_table[name] for name in names]
    return rng.choices(names, weights=weights, k=1)[0]


def pick_map(rng: random.Random) -> str:
    return rng.choice(MAP_POOL)


def pick_weapon(rng: random.Random) -> str:
    return _weighted_pick(rng, WEAPON_WEIGHTS)


def skill_profile(rng: random.Random, tier_score: float) -> str:
    """给一个段位分，返回水平描述。用来在提示里告诉模型这个人大概什么水平。"""
    for lower, upper, label in TIER_RANGES:
        if lower <= tier_score < upper:
            return label
    return TIER_RANGES[-1][2]


def build_match_setup(rng: random.Random, stats: dict[str, Any] | None) -> dict[str, Any]:
    """生成一局的完整设定。

    `统计` 是玩家真实的近期统计，用它决定这一局的水平——没有就按中间档来。
    这样推演出来的表现贴着这人平时的水平，而不是凭空一个路人。

    固定两件事：**比分走 13 局**（CS2 竞技的赛制），**评级不会比上局掉太多**
    （一局里大幅掉分要出意外状况，绝大多数时候是平的）。
    """
    if stats and stats.get("总场次"):
        level = stats
    else:
        level = {}

    map_name = pick_map(rng)
    weapon = pick_weapon(rng)
    accuracy_low, accuracy_high = WEAPON_CATEGORIES[weapon]

    # 个人表现随水平浮动。没有真实数据时取中位，不假装知道他什么水平。
    base_kills = level.get("KD") or 1.0
    base_headshot = level.get("爆头率")
    base_headshot = base_headshot / 100 if base_headshot else 0.5

    won_match = rng.random() < 0.5
    won = 13 if won_match else rng.randint(9, 12)
    lost = 13 if not won_match else rng.randint(9, 12)

    kills = max(
        0,
        round(rng.triangular(8, 32, 8 + base_kills * 9) + (2 if won_match else -2)),
    )
    deaths = max(1, round(kills / max(0.35, base_kills)))
    assists = max(0, round(kills * rng.uniform(0.2, 0.6)))

    headshots = min(kills, round(kills * rng.triangular(0.2, 0.75, base_headshot)))
    accuracy = rng.uniform(accuracy_low, accuracy_high)
    damage = round(kills * rng.uniform(88, 108) + deaths * rng.uniform(20, 45))

    recent_ratings = level.get("近十场评分") or []
    reference = recent_ratings[0] if recent_ratings else 1.0
    rating = round(max(0, min(2, rng.gauss(reference, 0.3))), 2)

    tier_score = level.get("段位分") or 0

    return {
        "地图": map_name,
        "武器": weapon,
        "是否胜利": won_match,
        "比分": f"{won}:{lost}",
        "击杀": kills,
        "死亡": deaths,
        "助攻": assists,
        "爆头数": headshots,
        "命中率": round(accuracy * 100, 1),
        "伤害": damage,
        "评级": rating,
        "首杀": rng.random() < 0.45,
        "残局": rng.choice(("打出一次 1v2 残局", "被残局翻盘", "残局站住了", "残局白给")),
        "走位": rng.choice(
            ("中路架点稳", "开局抢点激进", "被打得退守", "绕后拿了个侧翼", "跟着队友进点")
        ),
        "水平": skill_profile(rng, tier_score) if tier_score else "无历史数据，取中等水平",
    }


def setup_text(setup: dict[str, Any]) -> str:
    """把设定折成给模型读的文字。"""
    lines = [
        f"地图：{setup['地图']}",
        f"武器：{setup['武器']}",
        f"比分：{setup['比分']}（{'胜' if setup['是否胜利'] else '负'}）",
        f"击杀/死亡/助攻：{setup['击杀']}/{setup['死亡']}/{setup['助攻']}",
        f"爆头：{setup['爆头数']}，命中率 {setup['命中率']}%",
        f"伤害：{setup['伤害']}",
        f"本局评级：{setup['评级']}",
        f"拿到首杀：{'是' if setup['首杀'] else '否'}",
        f"残局：{setup['残局']}",
        f"走位：{setup['走位']}",
        f"玩家水平：{setup['水平']}",
    ]
    return "\n".join(lines)
