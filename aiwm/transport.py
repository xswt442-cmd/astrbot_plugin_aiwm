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

__all__ = ["WmpvpClient", "ApiError"]

WMPVP_API = "https://api.wmpvp.com"

# 这三个请求头缺任何一个，接口都返回 `statusCode: 14 参数错误`。
# `t` 是秒级时间戳，`gameType` 表示要 CS:GO 与 CS2 两个游戏的数据。
_BASE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "okhttp/4.11.0",
    "gameType": "1,2",
    "gameTypeStr": "1,2",
}


class ApiError(Exception):
    """完美接口返回了失败的业务码。"""


# 这些码实测到的含义。补齐其余的之前，先让已知的能被读懂。
_ERROR_TEXTS = {
    14: "请求参数不对，可能是完美接口改了字段名",
    90003: "完美接口暂时不可用，稍后再试",
}

_NO_DATA_MESSAGE = "完美接口的响应里没有 data 字段"


class WmpvpClient:
    """完美平台战绩接口的 HTTP 客户端。"""

    def __init__(self, timeout: float = 30.0) -> None:
        # 不设 total 的话，接口挂起会把整条指令一直吊着，用户只看到「没反应」。
        self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))

    async def close(self) -> None:
        await self._http.close()

    async def __aenter__(self) -> WmpvpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _fetch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST 一个 JSON 请求体，取出 `data`。

        响应结构是 `{"statusCode": 0, "errorMessage": "", "data": {...}}`。
        `statusCode` 为 0 才算成功。
        """
        headers = {**_BASE_HEADERS, "t": str(int(time.time()))}

        async with self._http.post(
            f"{WMPVP_API}{path}",
            headers=headers,
            json=body,
        ) as response:
            text = await response.text()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"完美接口的响应不是 JSON：{text[:200]}") from exc

        code = payload.get("statusCode")
        if code != 0:
            message = _ERROR_TEXTS.get(code)
            if message is None:
                message = (
                    str(payload.get("errorMessage") or "").strip() or f"完美接口返回业务码 {code}"
                )
            raise ApiError(message)

        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(_NO_DATA_MESSAGE)
        return data

    async def fetch_stats(self, steamid: str, *, access_token: str = "") -> dict[str, Any]:
        """取一个 steamid64 的战绩统计。

        `toSteamId` 与 `mySteamId` 两个字段都要填，只填其一会报参数错误。
        `accessToken` 留空不影响统计本身，只有完整对局列表需要它。
        """
        return await self._fetch(
            "/api/csgo/home/official/detailStats",
            {
                "toSteamId": steamid,
                "mySteamId": steamid,
                "accessToken": access_token,
            },
        )
