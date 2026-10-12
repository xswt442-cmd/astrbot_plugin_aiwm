"""main.py 的接线检查。

`main.py` 跑不了单测——它顶层 import astrbot，本地没这个包。所以下面这些
只能检查源码。改动 `main.py` 时这些检查要跟着一起过。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

main源 = Path(__file__).resolve().parent.parent / "main.py"


def _树() -> ast.Module:
    return ast.parse(main源.read_text(encoding="utf-8"))


def _类树() -> ast.ClassDef:
    for 节点 in _树().body:
        if isinstance(节点, ast.ClassDef) and 节点.name == "Main":
            return 节点
    raise AssertionError("main.py 里没有 Main 类")


def _方法(名: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for 节点 in ast.walk(_类树()):
        if isinstance(节点, ast.FunctionDef | ast.AsyncFunctionDef) and 节点.name == 名:
            return 节点
    raise AssertionError(f"Main 上没有 {名} 方法")


def _方法源码(名: str) -> str:
    """方法体的源码。

    用 `ast.unparse` 而不是读文本片段：源码里只要出现过某个片段（比如注释里
    提到了某个方法名），`"... not in 片段"` 这种断言就会误判。
    """
    return ast.unparse(_方法(名))


class Test接线:
    # 注意 `ast.unparse` 会把字符串统一规范成单引号，断言里照这个写。
    def test_指令组名是爱完美(self):
        源码 = ast.unparse(_类树())
        assert "@command_group('爱完美')" in 源码

    def test_指令都挂在方法上(self):
        """所有 command 装饰器都要挂在某个方法上，不能散在模块顶层。"""
        类 = _类树()
        命令 = [
            节点
            for 节点 in ast.walk(类)
            if isinstance(节点, ast.Call)
            and isinstance(节点.func, ast.Attribute)
            and 节点.func.attr == "command"
        ]
        assert len(命令) >= 7, "指令数量比预期少，检查是不是漏了"

    def test_读战绩用返回值判断有没有数据(self):
        """不能靠文本前缀判断数据可用性。

        玩家关闭战绩展示时，`汇总文本` 返回的是一句「数据是空的」，它不以
        「提问者还没有」或「读取战绩失败」开头。靠前缀判断的话，锐评会把这句
        当成数据喂给模型，而锐评提示要求写够 3 个具体数字，模型只能编。
        """
        读战绩 = _方法源码("_读战绩")
        # 返回值是二元组，第二个是统计字典，没有数据时为 None
        assert "tuple[str, dict[str, Any] | None]" in 读战绩
        assert "'提问者还没有绑定 steamid，无法查询战绩。', None" in 读战绩
        # 数据为空时（玩家关了战绩展示）也要返回 None
        assert "return (文本, None)" in 读战绩

    def test_锐评看统计字典而不是文本(self):
        锐评 = _方法源码("锐评")
        assert "if 统计 is None:" in 锐评

    def test_战绩不可用的前缀判断已经不存在(self):
        """这个判断被统计字典取代了，留着会有人以为还能用。"""
        with pytest.raises(AssertionError):
            _方法("_战绩不可用")

    def test_PK_走昵称查找(self):
        """QQ 官方平台拿不到被 @ 的人的标识，昵称那条是实际能走通的路径。"""
        源码 = _方法源码("_找对手记录")
        assert "按昵称找" in 源码

    def test_PK_用记录里的steamid(self):
        """昵称命中的是记录不是标识，不要去拼一个用户标识出来。"""
        源码 = ast.unparse(_类树())
        assert "对手记录['steamid']" in 源码

    def test_PK_自己跟自己要挡住(self):
        源码 = ast.unparse(_类树())
        assert "不能跟自己 PK" in 源码

    def test_绑定前先探接口(self):
        """用户打错一位数字的话要在绑定时就发现，而不是存进去之后每次查询失败。"""
        源码 = _方法源码("绑定")
        assert "读战绩数据" in 源码
        assert "取有效steamid" in 源码

    def test_凭据目录按插件名分开(self):
        """数据落在 `plugin_data/aiwm/`，不与别的插件目录混在一起。"""
        源码 = ast.unparse(_类树())
        assert "'plugin_data' / 'aiwm'" in 源码
        assert "ainong" not in 源码

    def test_锐评与PK都拿当前对话的模型(self):
        """两个指令都要先取当前会话用的模型，不能写死一个。"""
        for 名 in ("锐评", "PK"):
            源码 = _方法源码(名)
            assert "get_current_chat_provider_id" in 源码, f"{名} 没有取当前对话用的模型"

    def test_PK_提示里没有甲乙与真实姓名混用(self):
        """已算好的对比与占优项数必须用同一套名字。

        混用的话模型得自己推断「甲」是老王，这层映射没有必要。
        """
        源码 = ast.unparse(_方法("PK"))
        assert '对比文本(要点, "甲", "乙")' not in 源码
        assert "对比文本(要点, 自己名, 对手名)" in 源码
