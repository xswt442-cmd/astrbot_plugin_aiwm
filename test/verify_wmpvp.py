"""手工验证脚本：拿真实接口跑一遍完整链路。

不打 AstrBot（本地没这个包），只验传输层到汇总文本这一段。改完协议相关的
代码手动跑一次，确认接口还通、字段还对得上。

带 `--检查` 时不打印内容，只核对字段名与量纲并用退出码表态，给持续集成用：

```sh
python test/verify_wmpvp.py 76561198159976336 --检查
```

退出码 0 表示对得上，1 表示接口改了字段或量纲，2 表示接口打不通。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from 核对规则 import check  # noqa: E402

from aiwm.battles import fetch_battle_data  # noqa: E402
from aiwm.transport import WmpvpClient  # noqa: E402

DEFAULT_STEAM_ID = "76561198159976336"


async def main() -> int:
    inspect = "--检查" in sys.argv
    arg = [item for item in sys.argv[1:] if not item.startswith("--")]
    steamid = arg[0] if arg else DEFAULT_STEAM_ID

    async with WmpvpClient() as client:
        try:
            # 只取接口原始响应，不过统计层——统计层会把字段名的问题掩盖掉，
            # 比如字段被删了，统计层只是让那一项从文本里消失，看不出来。
            response = await client.fetch_stats(steamid)
        except Exception as exc:
            print(f"打完美接口失败：{type(exc).__name__}: {exc}")
            return 2

        if not inspect:
            text, stats = await fetch_battle_data(client, steamid)
            print(text)
            print()
            print("--- 统计字典 ---")
            for key, value in stats.items():
                print(f"{key}: {value}")
            print()
            print("--- 原始响应 ---")
            print(json.dumps(response, ensure_ascii=False, indent=2))
            return 0

    problems = check(response)
    if problems:
        print("接口的字段名或量纲与测试里的构造数据对不上：\n")
        for line in problems:
            print(f"  · {line}")
        return 1

    print(f"接口字段名与量纲都对得上（steamid {steamid}）")
    return 0


sys.exit(asyncio.run(main()))
