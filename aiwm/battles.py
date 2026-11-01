"""读战绩。

把完美接口的响应接上 `aiwm.stats`，折成模型可读的文本与统计字典。

统计字典单独给出来是给 PK 用的：两个人的逐项对比**必须由代码算**，不能把
两份文本丢给模型让它自己比——那样它会给「各有千秋」。
"""

from __future__ import annotations

from typing import Any

from .stats import summarize, summary_text, tier_name

__all__ = ["fetch_battle_data"]


async def fetch_battle_data(client, steam_id: str) -> tuple[str, dict[str, Any]]:
    """取一个 steamid64 的战绩，返回 (给模型读的文本, 统计字典)。"""
    response = await client.fetch_stats(steam_id)
    stats = summarize(response)
    text = summary_text(stats, 段位=tier_name(stats.get("段位分")))
    return text, stats
