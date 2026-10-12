"""在容器里验插件能不能真的加载。

`main.py` 本地跑不了单测（顶层 import astrbot），所以装到容器里才算第一次
真验。上一版就是本地全绿、容器 `AttributeError` 挂掉的，所以这条检查值得
单独做。
"""

import ast
import importlib
import sys
from pathlib import Path

插件目录 = Path(sys.argv[1])
sys.path.insert(0, str(插件目录))
sys.path.insert(0, "/AstrBot")

问题 = []

# 1. 语法
try:
    源码 = (插件目录 / "main.py").read_text(encoding="utf-8")
    ast.parse(源码)
except Exception as exc:
    print(f"[失败] main.py 语法：{type(exc).__name__}: {exc}")
    raise SystemExit(1) from None
print("[通过] main.py 语法")

# 2. 用到的 astrbot API 真的存在
for 名 in ("command_group", "custom_filter", "llm_tool"):
    模 = importlib.import_module("astrbot.api.event.filter")
    if not hasattr(模, 名):
        问题.append(f"astrbot.api.event.filter 没有 {名}")
    else:
        print(f"[通过] astrbot.api.event.filter.{名}")

for 路径, 名 in (
    ("astrbot.api.star", "Context"),
    ("astrbot.api.star", "Star"),
    ("astrbot.core.star.filter.custom_filter", "CustomFilter"),
    ("astrbot.core.platform.astr_message_event", "MessageEventResult"),
):
    try:
        模 = importlib.import_module(路径)
        getattr(模, 名)
        print(f"[通过] {路径}.{名}")
    except Exception as exc:
        问题.append(f"{路径}.{名} 拿不到：{exc}")

# 3. 兜底挂在指令组方法上，且不是那句会 AttributeError 的写法
树 = ast.parse(源码)
if "@custom_filter(_落空兜底)" not in 源码:
    问题.append("兜底没挂在指令组方法上")
# 只扫代码里的属性访问，别扫注释——注释里为了说明坑会提到那个方法名。
用到的属性 = [节点.attr for 节点 in ast.walk(树) if isinstance(节点, ast.Attribute)]
if "add_custom_filter" in 用到的属性:
    问题.append("还在调 self.爱完美.add_custom_filter(...)，那会 AttributeError")
if not 问题:
    print("[通过] 兜底的挂法")

# 4. 真的 import 一遍插件包（不加载插件，只验模块级代码）
try:
    importlib.import_module("aiwm.兜底")
    importlib.import_module("aiwm.pk_target")
    importlib.import_module("aiwm.来源")
    print("[通过] aiwm 各模块可导入")
except Exception as exc:
    问题.append(f"import 失败：{type(exc).__name__}: {exc}")

if 问题:
    print("\n[失败]")
    for 条 in 问题:
        print(f"  · {条}")
    raise SystemExit(1)

print("\n[全部通过] 可以在容器里加载")
