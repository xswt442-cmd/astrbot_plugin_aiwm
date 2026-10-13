import sys

sys.path.insert(0, "/AstrBot")
sys.path.insert(0, "/AstrBot/data/plugins/astrbot_plugin_aiwm")

from aiwm.兜底 import 以组名开头, 取落空参数, 是否落空  # noqa: E402

组 = "爱完美"
用例 = [
    ("在吗", False),
    ("", False),
    ("爱瓦 绑定", False),
    ("爱农 状态", False),
    ("今天天气不错", False),
    ("/help", False),
    ("/爱完美 战绩", False),
    ("爱完美 战绩", False),
    ("/爱完美 绑定 76561198829920790", False),
    ("爱完美 PK 老王", False),
    ("/爱完美 76561198829920790", True),
    ("爱完美 我的战绩怎么样", True),
]

失败 = 0
for 消息, 期望 in 用例:
    实际 = 是否落空(消息, 组)
    对 = "✅" if 实际 is 期望 else "❌"
    if 实际 is not 期望:
        失败 += 1
    print(f"{对} {消息!r:34} 落空={实际} (期望 {期望})  参数={取落空参数(消息, 组)!r}")

print(f"\n失败 {失败} / {len(用例)}")