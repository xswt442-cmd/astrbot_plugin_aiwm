"""在容器里验插件能不能真的加载。

`main.py` 本地跑不了单测（顶层 import astrbot），所以装到容器里才算第一次
真验。上一版就是本地全绿、容器 `AttributeError` 挂掉的，所以这条检查值得
单独做。
"""

import ast
import importlib
import sys
from pathlib import Path

PLUGIN_DIR = Path(sys.argv[1])
sys.path.insert(0, str(PLUGIN_DIR))
sys.path.insert(0, "/AstrBot")

problems = []

# 1. 语法
try:
    source = (PLUGIN_DIR / "main.py").read_text(encoding="utf-8")
    ast.parse(source)
except Exception as exc:
    print(f"[失败] main.py 语法：{type(exc).__name__}: {exc}")
    raise SystemExit(1) from None
print("[通过] main.py 语法")

# 2. 用到的 astrbot API 真的存在
for name in ("command_group", "custom_filter", "llm_tool"):
    module = importlib.import_module("astrbot.api.event.filter")
    if not hasattr(module, name):
        problems.append(f"astrbot.api.event.filter 没有 {name}")
    else:
        print(f"[通过] astrbot.api.event.filter.{name}")

for path, name in (
    ("astrbot.api.star", "Context"),
    ("astrbot.api.star", "Star"),
    ("astrbot.core.star.filter.custom_filter", "CustomFilter"),
    ("astrbot.core.platform.astr_message_event", "MessageEventResult"),
):
    try:
        module = importlib.import_module(path)
        getattr(module, name)
        print(f"[通过] {path}.{name}")
    except Exception as exc:
        problems.append(f"{path}.{name} 拿不到：{exc}")

# 3. 兜底挂在指令组方法上，且不是那句会 AttributeError 的写法
tree = ast.parse(source)
if "@custom_filter(_落空兜底)" not in source:
    problems.append("兜底没挂在指令组方法上")
# 只扫代码里的属性访问，别扫注释——注释里为了说明坑会提到那个方法名。
used_attrs = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
if "add_custom_filter" in used_attrs:
    problems.append("还在调 self.爱完美.add_custom_filter(...)，那会 AttributeError")
if not problems:
    print("[通过] 兜底的挂法")

# 4. 真的 import 一遍插件包（不加载插件，只验模块级代码）
try:
    importlib.import_module("aiwm.fallback")
    importlib.import_module("aiwm.pk_target")
    importlib.import_module("aiwm.source")
    print("[通过] aiwm 各模块可导入")
except Exception as exc:
    problems.append(f"import 失败：{type(exc).__name__}: {exc}")

if problems:
    print("\n[失败]")
    for line in problems:
        print(f"  · {line}")
    raise SystemExit(1)

print("\n[全部通过] 可以在容器里加载")
