"""main.py 的接线检查。

`main.py` 跑不了单测——它顶层 import astrbot，本地没这个包。所以下面这些
只能检查源码。改动 `main.py` 时这些检查要跟着一起过。
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

main源 = Path(__file__).resolve().parent.parent / "main.py"

# 参数没有默认值时用它占位，好与「默认值就是 None」区分开。
_无 = object()


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


def _默认值(方法: ast.FunctionDef, 位置: int):
    """取第 `位置` 个位置参数的默认值，没有就返回 `_无`。"""
    数量 = len(方法.args.defaults)
    起点 = len(方法.args.args) - 数量
    if 位置 < 起点:
        return _无
    return ast.literal_eval(方法.args.defaults[位置 - 起点])


def _有默认值的参数(方法: ast.FunctionDef) -> set[str]:
    起点 = len(方法.args.args) - len(方法.args.defaults)
    return {项.arg for 项 in 方法.args.args[起点:]}


class Test构造签名:
    """`__init__` 的参数签名错了，插件整个加载不起来。

    AstrBot 的 `star_manager` 在 `if plugin_config and metadata.star_cls_type:`
    分支里才把配置传进来。没有 `_conf_schema.json` 时它读不到配置项，那一个
    `if` 分支不走，只传 context。所以 config 必须可省——这条踩过：声明成必需
    参数时报 `TypeError: missing 1 required positional argument: 'config'`，
    容器里插件直接加载失败，而本地跑不了 main.py 根本发现不了。
    """

    def test_必需参数只有context(self):
        构造 = _方法("__init__")
        必填 = [项.arg for 项 in 构造.args.args[1:] if 项.arg not in _有默认值的参数(构造)]

        assert 必填 == ["context"]

    def test_只传context能构造出来(self):
        """真正按 AstrBot 的调用方式绑定一次参数。

        比看签名可靠——它验的是参数能不能少传，而不只是签名长什么样。
        """
        构造 = _方法("__init__")
        参数 = [
            inspect.Parameter(
                项.arg,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=(
                    inspect.Parameter.empty if _默认值(构造, 位置) is _无 else _默认值(构造, 位置)
                ),
            )
            for 位置, 项 in enumerate(构造.args.args)
        ]

        # self 与 context，不传 config —— 这就是没有配置文件时 AstrBot 的调用
        绑定 = inspect.Signature(参数).bind(object(), object())

        assert "config" not in 绑定.arguments


class Test接线:
    # 注意 `ast.unparse` 会把字符串统一规范成单引号，断言里照这个写。
    def test_指令组名是爱完美(self):
        """组名走 `_组名` 常量，兜底那个 filter 也靠它剥前缀——改一处要够到
        帮助文本与 `aiwm/兜底.py`。"""
        模块 = ast.parse(main源.read_text(encoding="utf-8"))
        常量 = [
            节点.value.value
            for 节点 in 模块.body
            if isinstance(节点, ast.Assign)
            and getattr(节点.targets[0], "id", "") == "_组名"
            and isinstance(节点.value, ast.Constant)
        ]

        assert 常量 == ["爱完美"]

    def test_组名常量用在了指令组上(self):
        源码 = ast.unparse(_类树())
        assert "command_group(_组名" in 源码

    def test_组别名带上斜杠(self):
        """QQ 官方的 At 唤醒分支不剥 message_str 里的 `/`。

        那条分支只置 `wake_prefix = ""`，于是 `@机器人 /爱完美 战绩` 的
        message_str 仍是 `/爱完美 战绩`，组名 `爱完美` 匹配不上，整条指令
        静默失败。加一个带斜杠的组别名，两种写法都能进。
        """
        # `ast.unparse` 把字符串规范成单引号，所以这里按源码文本查。
        assert "_组别名" in ast.unparse(_类树()), "指令组没带组别名"
        模块 = ast.parse(main源.read_text(encoding="utf-8"))
        别名 = [
            节点.value
            for 节点 in 模块.body
            if isinstance(节点, ast.Assign) and getattr(节点.targets[0], "id", "") == "_组别名"
        ]
        assert 别名, "缺 _组别名，QQ 官方上带斜杠的写法会静默失败"
        assert "_组名" in ast.unparse(别名[0]), "组别名应该是 /组名，写死字符串会漏改"

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
        assert "'还没绑定 steamid，先发 /爱完美 绑定 <steamid64>。', None" in 读战绩
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
        assert "按昵称找" in _方法源码("_按昵称找")

    def test_PK_参数优先于昵称(self):
        """参数里含 steamid 就直接查——对方不用绑定。"""
        源码 = _方法源码("PK")
        assert "取对手标识" in 源码

    def test_PK_用取到的steamid(self):
        """id 那条路没有本机记录，昵称那条才有记录，所以要分开拿。"""
        源码 = ast.unparse(_类树())
        assert "对手steamid" in 源码
        assert "对手记录['steamid']" not in 源码

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

    def test_兜底的别名清单与指令一致(self):
        """`aiwm.兜底.子命令名` 是手抄的，main.py 改了别名忘了改它，
        用户打那个别名时就静默落空——而落空的表现是模型开始胡说，很难归因。"""
        import ast as _ast

        from aiwm.兜底 import 子命令名

        树 = _ast.parse(main源.read_text(encoding="utf-8"))
        实际: set[str] = set()
        for 节点 in _ast.walk(树):
            if not isinstance(节点, _ast.Call):
                continue
            # @爱完美.command("战绩", alias={...})
            if not (isinstance(节点.func, _ast.Attribute) and 节点.func.attr == "command"):
                continue
            if not 节点.args or not isinstance(节点.args[0], _ast.Constant):
                continue
            名 = 节点.args[0].value
            if not isinstance(名, str):
                continue
            实际.add(名)
            for 关键字 in 节点.keywords:
                if 关键字.arg != "alias":
                    continue
                for 元素 in getattr(关键字.value, "elts", []):
                    if isinstance(元素, _ast.Constant) and isinstance(元素.value, str):
                        实际.add(元素.value)

        assert 实际 <= 子命令名, f"main.py 里有子命令没登记进兜底：{实际 - 子命令名}"

    def test_锐评与PK都拿当前对话的模型(self):
        """两个指令都要先取当前会话用的模型，不能写死一个。"""
        for 名 in ("锐评", "PK"):
            源码 = _方法源码(名)
            assert "get_current_chat_provider_id" in 源码, f"{名} 没有取当前对话用的模型"

    def test_开一局也在取当前对话的模型(self):
        源码 = _方法源码("开一局")

        assert "get_current_chat_provider_id" in 源码

    def test_开一局用随机种子(self):
        """每次发都得是新的一局。固定种子会让人看到重复的局。"""
        源码 = _方法源码("开一局")

        assert "random.Random()" in 源码
        assert "random.seed" not in 源码

    def test_开一局先给设定再给复盘(self):
        """模型写崩了，至少还有这一局的数字可看。"""
        源码 = _方法源码("开一局")

        assert 源码.count("设定文本") >= 2, "设定文本应该在提示与输出里各用一次"

    def test_开一局读战绩失败不影响整条指令(self):
        """绑定着但接口挂了就退回「无历史数据」那一档，别让这条指令整个用不了。"""
        源码 = _方法源码("开一局")

        assert "except Exception" in 源码
        assert "统计 = None" in 源码

    def test_PK_提示里没有甲乙与真实姓名混用(self):
        """已算好的对比与占优项数必须用同一套名字。

        混用的话模型得自己推断「甲」是老王，这层映射没有必要。
        """
        源码 = ast.unparse(_方法("PK"))
        assert '对比文本(要点, "甲", "乙")' not in 源码
        assert "对比文本(要点, 自己名, 对手名)" in 源码


class Test兜底过滤器挂法:
    """兜底 filter 的两个致命错误都在这里，各对应过一次线上事故。

    1. 返回值语义写反 → `CommandGroupFilter.filter` 里
       `if not custom_filter_ok(...): return False` 会把整个指令组毙掉，
       正常指令全部没反应。
    2. 不判断消息归不归自己管 → 那个 filter 对**每一条消息**都执行
       （组名检查在它之后），于是「在吗」「/爱农 开一局」全被
       `stop_event()` 掐掉，老狗对所有消息不理人。
    """

    def _兜底filter(self) -> ast.FunctionDef:
        for 节点 in _树().body:
            if isinstance(节点, ast.ClassDef) and 节点.name == "_落空兜底":
                for 体 in 节点.body:
                    if isinstance(体, ast.FunctionDef) and 体.name == "filter":
                        return 体
        raise AssertionError("main.py 里没有 _落空兜底.filter")

    def test_所有出口都return_True(self):
        方法 = self._兜底filter()
        返回 = [
            节点.value.value
            for 节点 in ast.walk(方法)
            if isinstance(节点, ast.Return) and isinstance(节点.value, ast.Constant)
        ]
        assert 返回 and set(返回) == {True}, (
            f"兜底 filter 里出现了 {返回}，必须所有出口都 return True"
        )

    def test_先判是否归自己管(self):
        方法 = self._兜底filter()
        assert "以组名开头" in ast.unparse(方法), "缺了归属判断，会掐掉别人的消息"

    def test_命中分支要掐掉事件(self):
        """命中落空必须 stop_event，否则消息会漏给模型让它开始编。"""
        assert "event.stop_event()" in ast.unparse(self._兜底filter())


class Test源码卫生:
    """两类只在运行时才炸、本地又跑不到的写法。

    漏 f 前缀的字符串**语法完全合法**，只有用户看到字面量 `{名字}` 时才知道
    出事了；except 里读 try 体内才绑定的变量同样合法，只有异常真发生时才
    `UnboundLocalError`。
    """

    def test_没有漏f前缀的字符串(self):
        占位 = re.compile(r"\{[^{}\n]{1,40}\}")
        漏 = [
            (节点.lineno, 命中.group(0))
            for 节点 in ast.walk(_树())
            if isinstance(节点, ast.Constant) and isinstance(节点.value, str)
            for 命中 in 占位.finditer(节点.value)
        ]
        assert not 漏, f"这些字符串里的占位符不会被替换（漏了 f 前缀）：{漏}"

    def test_except里不读try体内才绑定的变量(self):
        问题 = []
        for 函数 in [
            节点
            for 节点 in ast.walk(_树())
            if isinstance(节点, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]:
            for 函数名, 行号, 名字 in _未绑定读取(函数):
                问题.append(f"{函数名} 第{行号}行 except 里读了 {sorted(名字)}")
        assert not 问题, "\n".join(问题)


def _绑定的(节点们: list[ast.AST]) -> set[str]:
    出: set[str] = set()
    for 节点 in 节点们:
        for 子 in ast.walk(节点):
            if isinstance(子, ast.Name) and isinstance(子.ctx, ast.Store):
                出.add(子.id)
            if isinstance(子, (ast.FunctionDef, ast.AsyncFunctionDef)):
                出.add(子.name)
            if isinstance(子, ast.ExceptHandler) and 子.name:
                出.add(子.name)
    return 出


def _未绑定读取(函数: ast.AsyncFunctionDef | ast.FunctionDef) -> list[tuple[str, int, set]]:
    """找出 `except` 里读了「同一个 try 体内才绑定」的变量的地方。"""
    报告: list[tuple[str, int, set]] = []
    已绑 = {参数.arg for 参数 in 函数.args.args}

    def 扫(节点们: list[ast.stmt]) -> None:
        for 节点 in 节点们:
            if isinstance(节点, ast.Try):
                体内 = _绑定的(节点.body)
                for 处理 in 节点.handlers:
                    读到 = {
                        子.id
                        for 子 in ast.walk(处理)
                        if isinstance(子, ast.Name) and isinstance(子.ctx, ast.Load)
                    }
                    可疑 = (读到 & 体内) - 已绑
                    if 可疑:
                        报告.append((函数.name, 节点.lineno, 可疑))
                扫(节点.body)
                for 处理 in 节点.handlers:
                    扫(处理.body)
                    已绑.update(_绑定的(处理.body))
                扫(节点.orelse)
                扫(节点.finalbody)
                已绑.update(体内)
            elif hasattr(节点, "body") and isinstance(节点.body, list):
                已绑.update(_绑定的([节点]))
                扫(节点.body)

    扫(函数.body)
    return 报告


def _帮助块() -> str:
    文本 = main源.read_text(encoding="utf-8")
    起点 = 文本.index('_帮助文本 = """') + len('_帮助文本 = """')
    return 文本[起点 : 文本.index('"""', 起点)]


def _正式指令名() -> set[str]:
    """`@爱完美.command("x")` 声明的正式指令名，不含别名。"""
    出: set[str] = set()
    for 节点 in ast.walk(_树()):
        if not isinstance(节点, ast.Call):
            continue
        if not (isinstance(节点.func, ast.Attribute) and 节点.func.attr == "command"):
            continue
        if not 节点.args or not isinstance(节点.args[0], ast.Constant):
            continue
        if isinstance(节点.args[0].value, str):
            出.add(节点.args[0].value)
    return 出


class Test帮助文案:
    def test_每个指令都在帮助里(self):
        """帮助漏一条，用户就只能靠猜或问。

        只查正式指令名：别名是给习惯写法兜底的，不必逐条列进帮助。
        """
        缺 = sorted(名 for 名 in _正式指令名() if f"/爱完美 {名}" not in _帮助块())
        assert not 缺, f"帮助文本里没列这些指令：{缺}"

    def test_帮助首行是产品名加游戏名(self):
        assert _帮助块().lstrip().startswith("爱完美 · ")

    def test_说清数据来自官匹(self):
        """说成「完美平台战绩」，用户拿官匹数据一核对会以为插件坏了。"""
        帮助块 = _帮助块()

        assert "数据来自" in 帮助块
        assert "官匹" in 帮助块
        assert "不是完美竞技平台" in 帮助块

    def test_说明自然语言也能用(self):
        assert "直接问模型" in _帮助块()

    def test_开一局说明是推演(self):
        """用户看到一串 K/D/A 分不出真假，帮助里要先说清楚。"""
        assert "推演" in _帮助块()


class Test日志出口:
    """插件规范：logger 必须且只能从 `astrbot.api` 取，不许用内置 `logging`。

    爱农上架审核第一次就是被这一条驳回的（`ainong/auth/` 下两个模块用了内置
    `logging`，只看 main.py 查不出来）。这里扫整个包，防止同样的写法溜进来。
    """

    def test_包内不用内置logging(self):
        违规 = [
            路径.name
            for 路径 in sorted(main源.parent.joinpath("aiwm").rglob("*.py"))
            if re.search(r"^\s*(?:import logging|from logging)\b", 路径.read_text("utf-8"), re.M)
        ]
        assert not 违规, f"这些文件用了内置 logging，要改成从 astrbot.api 取：{违规}"

    def test_logger_从_astrbot_取(self):
        源码 = main源.read_text(encoding="utf-8")
        assert re.search(r"^from astrbot\.api import .*\blogger\b", 源码, re.M)
