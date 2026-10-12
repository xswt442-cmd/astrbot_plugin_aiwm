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

from 核对规则 import 核对  # noqa: E402

from aiwm.battles import 读战绩数据  # noqa: E402
from aiwm.transport import 完美传输  # noqa: E402

默认steamid = "76561198159976336"


async def 主() -> int:
    检查 = "--检查" in sys.argv
    参数 = [项 for 项 in sys.argv[1:] if not 项.startswith("--")]
    steamid = 参数[0] if 参数 else 默认steamid

    async with 完美传输() as 传输:
        try:
            # 只取接口原始响应，不过统计层——统计层会把字段名的问题掩盖掉，
            # 比如字段被删了，统计层只是让那一项从文本里消失，看不出来。
            响应 = await 传输.查战绩(steamid)
        except Exception as exc:
            print(f"打完美接口失败：{type(exc).__name__}: {exc}")
            return 2

        if not 检查:
            文本, 统计 = await 读战绩数据(传输, steamid)
            print(文本)
            print()
            print("--- 统计字典 ---")
            for 键, 值 in 统计.items():
                print(f"{键}: {值}")
            print()
            print("--- 原始响应 ---")
            print(json.dumps(响应, ensure_ascii=False, indent=2))
            return 0

    问题 = 核对(响应)
    if 问题:
        print("接口的字段名或量纲与测试里的构造数据对不上：\n")
        for 条 in 问题:
            print(f"  · {条}")
        return 1

    print(f"接口字段名与量纲都对得上（steamid {steamid}）")
    return 0


sys.exit(asyncio.run(主()))
