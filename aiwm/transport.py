"""完美世界竞技平台接口的传输层。

负责拼请求头、发请求、解读业务码。不含业务语义。

战绩接口对查询目标没有鉴权要求：`accessToken` 留空就能拿到完整的统计，
所以这个传输层不需要登录会话，建起来就能用。`accessToken` 只影响
`/api/csgo/home/match/list`（完整对局历史分页）。
"""

from __future__ import annotations

import json
import time
from typing import Any

import aiohttp

__all__ = ["完美传输", "业务错误"]

完美接口 = "https://api.wmpvp.com"

# 这三个请求头缺任何一个，接口都返回 `statusCode: 14 参数错误`。
# `t` 是秒级时间戳，`gameType` 表示要 CS:GO 与 CS2 两个游戏的数据。
_基础头 = {
    "Content-Type": "application/json",
    "User-Agent": "okhttp/4.11.0",
    "gameType": "1,2",
    "gameTypeStr": "1,2",
}


class 业务错误(Exception):
    """完美接口返回了失败的业务码。"""


# 这些码实测到的含义。补齐其余的之前，先让已知的能被读懂。
_业务码文案 = {
    14: "请求参数不对，可能是完美接口改了字段名",
    90003: "完美接口暂时不可用，稍后再试",
}

_取数据失败 = "完美接口的响应里没有 data 字段"


class 完美传输:
    """完美平台战绩接口的 HTTP 客户端。"""

    def __init__(self, 超时: float = 30.0) -> None:
        # 不设 total 的话，接口挂起会把整条指令一直吊着，用户只看到「没反应」。
        self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=超时))

    async def 关闭(self) -> None:
        await self._http.close()

    async def __aenter__(self) -> 完美传输:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.关闭()

    async def _取数(self, 路径: str, 表单: dict[str, Any]) -> dict[str, Any]:
        """POST 一个 JSON 请求体，取出 `data`。

        响应结构是 `{"statusCode": 0, "errorMessage": "", "data": {...}}`。
        `statusCode` 为 0 才算成功。
        """
        头 = {**_基础头, "t": str(int(time.time()))}

        async with self._http.post(
            f"{完美接口}{路径}",
            headers=头,
            json=表单,
        ) as 响应:
            文本 = await 响应.text()

        try:
            载荷 = json.loads(文本)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"完美接口的响应不是 JSON：{文本[:200]}") from exc

        码 = 载荷.get("statusCode")
        if 码 != 0:
            文案 = _业务码文案.get(码)
            if 文案 is None:
                文案 = str(载荷.get("errorMessage") or "").strip() or f"完美接口返回业务码 {码}"
            raise 业务错误(文案)

        数据 = 载荷.get("data")
        if not isinstance(数据, dict):
            raise RuntimeError(_取数据失败)
        return 数据

    async def 查战绩(self, steamid: str, *, access_token: str = "") -> dict[str, Any]:
        """取一个 steamid64 的战绩统计。

        `toSteamId` 与 `mySteamId` 两个字段都要填，只填其一会报参数错误。
        `accessToken` 留空不影响统计本身，只有完整对局列表需要它。
        """
        return await self._取数(
            "/api/csgo/home/official/detailStats",
            {
                "toSteamId": steamid,
                "mySteamId": steamid,
                "accessToken": access_token,
            },
        )
