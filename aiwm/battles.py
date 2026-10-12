"""读战绩。

把完美接口的响应接上 `aiwm.stats`，折成模型可读的文本与统计字典。

统计字典单独给出来是给 PK 用的：两个人的逐项对比**必须由代码算**，不能把
两份文本丢给模型让它自己比——那样它会给「各有千秋」。
"""

from __future__ import annotations

from typing import Any

from .stats import 段位名, 汇总文本, 统计战绩

__all__ = ["读战绩数据"]


async def 读战绩数据(传输, steamid: str) -> tuple[str, dict[str, Any]]:
    """取一个 steamid64 的战绩，返回 (给模型读的文本, 统计字典)。"""
    响应 = await 传输.查战绩(steamid)
    统计 = 统计战绩(响应)
    文本 = 汇总文本(统计, 段位=段位名(统计.get("段位分")))
    return 文本, 统计
