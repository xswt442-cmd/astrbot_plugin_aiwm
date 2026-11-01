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

MAIN_SOURCE = Path(__file__).resolve().parent.parent / "main.py"

# 参数没有默认值时用它占位，好与「默认值就是 None」区分开。
_none = object()


def _tree() -> ast.Module:
    return ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))


def _class_tree() -> ast.ClassDef:
    for node in _tree().body:
        if isinstance(node, ast.ClassDef) and node.name == "Main":
            return node
    raise AssertionError("main.py 里没有 Main 类")


def _method(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(_class_tree()):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Main 上没有 {name} 方法")


def _method_source(name: str) -> str:
    """方法体的源码。

    用 `ast.unparse` 而不是读文本片段：源码里只要出现过某个片段（比如注释里
    提到了某个方法名），`"... not in 片段"` 这种断言就会误判。
    """
    return ast.unparse(_method(name))


def _default(method: ast.FunctionDef, pos: int):
    """取第 `位置` 个位置参数的默认值，没有就返回 `_无`。"""
    count = len(method.args.defaults)
    start = len(method.args.args) - count
    if pos < start:
        return _none
    return ast.literal_eval(method.args.defaults[pos - start])


def _defaulted_params(method: ast.FunctionDef) -> set[str]:
    start = len(method.args.args) - len(method.args.defaults)
    return {item.arg for item in method.args.args[start:]}


class TestConstructorSignature:
    """`__init__` 的参数签名错了，插件整个加载不起来。

    AstrBot 的 `star_manager` 在 `if plugin_config and metadata.star_cls_type:`
    分支里才把配置传进来。没有 `_conf_schema.json` 时它读不到配置项，那一个
    `if` 分支不走，只传 context。所以 config 必须可省——这条踩过：声明成必需
    参数时报 `TypeError: missing 1 required positional argument: 'config'`，
    容器里插件直接加载失败，而本地跑不了 main.py 根本发现不了。
    """

    def test_only_context_is_required(self):
        build = _method("__init__")
        required = [
            item.arg for item in build.args.args[1:] if item.arg not in _defaulted_params(build)
        ]

        assert required == ["context"]

    def test_constructible_with_context_only(self):
        """真正按 AstrBot 的调用方式绑定一次参数。

        比看签名可靠——它验的是参数能不能少传，而不只是签名长什么样。
        """
        build = _method("__init__")
        arg = [
            inspect.Parameter(
                item.arg,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=(
                    inspect.Parameter.empty
                    if _default(build, pos) is _none
                    else _default(build, pos)
                ),
            )
            for pos, item in enumerate(build.args.args)
        ]

        # self 与 context，不传 config —— 这就是没有配置文件时 AstrBot 的调用
        bind_cmd = inspect.Signature(arg).bind(object(), object())

        assert "config" not in bind_cmd.arguments


class TestWiring:
    # 注意 `ast.unparse` 会把字符串统一规范成单引号，断言里照这个写。
    def test_group_name_is_aiwm(self):
        """组名走 `_组名` 常量，兜底那个 filter 也靠它剥前缀——改一处要够到
        帮助文本与 `aiwm/fallback.py`。"""
        module = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
        constants = [
            node.value.value
            for node in module.body
            if isinstance(node, ast.Assign)
            and getattr(node.targets[0], "id", "") == "_GROUP"
            and isinstance(node.value, ast.Constant)
        ]

        assert constants == ["爱完美"]

    def test_group_constant_used(self):
        source = ast.unparse(_class_tree())
        assert "command_group(_GROUP" in source

    def test_group_alias_has_slash(self):
        """QQ 官方的 At 唤醒分支不剥 message_str 里的 `/`。

        那条分支只置 `wake_prefix = ""`，于是 `@机器人 /爱完美 战绩` 的
        message_str 仍是 `/爱完美 战绩`，组名 `爱完美` 匹配不上，整条指令
        静默失败。加一个带斜杠的组别名，两种写法都能进。
        """
        # `ast.unparse` 把字符串规范成单引号，所以这里按源码文本查。
        assert "_GROUP_ALIASES" in ast.unparse(_class_tree()), "指令组没带组别名"
        module = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
        alias = [
            node.value
            for node in module.body
            if isinstance(node, ast.Assign)
            and getattr(node.targets[0], "id", "") == "_GROUP_ALIASES"
        ]
        assert alias, "缺 _组别名，QQ 官方上带斜杠的写法会静默失败"
        assert "_GROUP" in ast.unparse(alias[0]), "组别名应该是 /组名，写死字符串会漏改"

    def test_commands_are_methods(self):
        """所有 command 装饰器都要挂在某个方法上，不能散在模块顶层。"""
        cls = _class_tree()
        command = [
            node
            for node in ast.walk(cls)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "command"
        ]
        assert len(command) >= 7, "指令数量比预期少，检查是不是漏了"

    def test_fetch_uses_return_value(self):
        """不能靠文本前缀判断数据可用性。

        玩家关闭战绩展示时，`汇总文本` 返回的是一句「数据是空的」，它不以
        「提问者还没有」或「读取战绩失败」开头。靠前缀判断的话，锐评会把这句
        当成数据喂给模型，而锐评提示要求写够 3 个具体数字，模型只能编。
        """
        fetch_battles = _method_source("_fetch_battles")
        # 返回值是二元组，第二个是统计字典，没有数据时为 None
        assert "tuple[str, dict[str, Any] | None]" in fetch_battles
        assert "'还没绑定，先发 /爱完美 绑定 <steamid64>。', None" in fetch_battles
        # 数据为空时（玩家关了战绩展示）也要返回 None
        assert "return (text, None)" in fetch_battles

    def test_review_reads_stats_dict(self):
        review_cmd = _method_source("review_cmd")
        assert "if stats is None:" in review_cmd

    def test_legacy_prefix_check_removed(self):
        """这个判断被统计字典取代了，留着会有人以为还能用。"""
        with pytest.raises(AssertionError):
            _method("_战绩不可用")

    def test_pk_uses_nickname_lookup(self):
        """QQ 官方平台拿不到被 @ 的人的标识，昵称那条是实际能走通的路径。"""
        assert "find_by_nickname" in _method_source("_find_by_nickname")

    def test_pk_arg_wins_over_nickname(self):
        """参数里含 steamid 就直接查——对方不用绑定。"""
        source = _method_source("PK")
        assert "resolve_opponent" in source

    def test_pk_uses_found_steamid(self):
        """id 那条路没有本机记录，昵称那条才有记录，所以要分开拿。"""
        source = ast.unparse(_class_tree())
        assert "opponent_steam_id" in source
        assert "对手记录['steamid']" not in source

    def test_pk_blocks_self(self):
        source = ast.unparse(_class_tree())
        assert "不能跟自己 PK" in source

    def test_bind_probes_api_first(self):
        """用户打错一位数字的话要在绑定时就发现，而不是存进去之后每次查询失败。"""
        source = _method_source("bind_cmd")
        assert "fetch_battle_data" in source
        assert "resolve_steamid" in source

    def test_credential_dir_by_plugin_name(self):
        """数据落在 `plugin_data/astrbot_plugin_aiwm/`，不与别的插件目录混在一起。

        市场审核规则是 `data/plugin_data/<plugin_name>`，`<plugin_name>` 指
        插件目录名。自造简称（`aiwm`）会被驳回，所以这里钉死插件名。
        """
        source = ast.unparse(_class_tree())
        assert "StarTools.get_data_dir(_PLUGIN_NAME)" in source

        main_text = MAIN_SOURCE.read_text(encoding="utf-8")
        assert '_PLUGIN_NAME = "astrbot_plugin_aiwm"' in main_text
        assert "'plugin_data' / 'aiwm'" not in main_text

    def test_fallback_alias_list_matches_commands(self):
        """`aiwm.fallback.子命令名` 是手抄的，main.py 改了别名忘了改它，
        用户打那个别名时就静默落空——而落空的表现是模型开始胡说，很难归因。"""
        import ast as _ast

        from aiwm.fallback import SUBCOMMANDS

        tree = _ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
        actual: set[str] = set()
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            # @爱完美.command("战绩", alias={...})
            if not (isinstance(node.func, _ast.Attribute) and node.func.attr == "command"):
                continue
            if not node.args or not isinstance(node.args[0], _ast.Constant):
                continue
            name = node.args[0].value
            if not isinstance(name, str):
                continue
            actual.add(name)
            for keyword in node.keywords:
                if keyword.arg != "alias":
                    continue
                for element in getattr(keyword.value, "elts", []):
                    if isinstance(element, _ast.Constant) and isinstance(element.value, str):
                        actual.add(element.value)

        assert actual <= SUBCOMMANDS, f"main.py 里有子命令没登记进兜底：{actual - SUBCOMMANDS}"

    def test_review_and_pk_use_current_model(self):
        """两个指令都要先取当前会话用的模型，不能写死一个。"""
        for name in ("review_cmd", "PK"):
            source = _method_source(name)
            assert "get_current_chat_provider_id" in source, f"{name} 没有取当前对话用的模型"

    def test_play_match_uses_current_model(self):
        source = _method_source("play_match_cmd")

        assert "get_current_chat_provider_id" in source

    def test_play_match_uses_seed(self):
        """每次发都得是新的一局。固定种子会让人看到重复的局。"""
        source = _method_source("play_match_cmd")

        assert "random.Random()" in source
        assert "random.seed" not in source

    def test_play_match_gives_setup_first(self):
        """模型写崩了，至少还有这一局的数字可看。"""
        source = _method_source("play_match_cmd")

        assert source.count("setup_text") >= 2, "设定文本应该在提示与输出里各用一次"

    def test_play_match_survives_fetch_failure(self):
        """绑定着但接口挂了就退回「无历史数据」那一档，别让这条指令整个用不了。"""
        source = _method_source("play_match_cmd")

        assert "except Exception" in source
        assert "stats = None" in source

    def test_pk_prompt_has_no_placeholder_names(self):
        """已算好的对比与占优项数必须用同一套名字。

        混用的话模型得自己推断「甲」是老王，这层映射没有必要。
        """
        source = ast.unparse(_method("PK"))
        assert 'contrast_text(points, "甲", "乙")' not in source
        assert "contrast_text(points, my_name, opponent_name)" in source


class TestFallbackFilterWiring:
    """兜底 filter 的两个致命错误都在这里，各对应过一次线上事故。

    1. 返回值语义写反 → `CommandGroupFilter.filter` 里
       `if not custom_filter_ok(...): return False` 会把整个指令组毙掉，
       正常指令全部没反应。
    2. 不判断消息归不归自己管 → 那个 filter 对**每一条消息**都执行
       （组名检查在它之后），于是「在吗」「/爱农 开一局」全被
       `stop_event()` 掐掉，老狗对所有消息不理人。
    """

    def _fallback_filter(self) -> ast.FunctionDef:
        for node in _tree().body:
            if isinstance(node, ast.ClassDef) and node.name == "_MissFallbackFilter":
                for body in node.body:
                    if isinstance(body, ast.FunctionDef) and body.name == "filter":
                        return body
        raise AssertionError("main.py 里没有 _落空兜底.filter")

    def test_all_returns_are_true(self):
        method = self._fallback_filter()
        returned = [
            node.value.value
            for node in ast.walk(method)
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
        ]
        assert returned and set(returned) == {True}, (
            f"兜底 filter 里出现了 {returned}，必须所有出口都 return True"
        )

    def test_checks_ownership_first(self):
        method = self._fallback_filter()
        assert "starts_with_group" in ast.unparse(method), "缺了归属判断，会掐掉别人的消息"

    def test_hit_branch_stops_event(self):
        """命中落空必须 stop_event，否则消息会漏给模型让它开始编。"""
        assert "event.stop_event()" in ast.unparse(self._fallback_filter())


class TestSourceHygiene:
    """两类只在运行时才炸、本地又跑不到的写法。

    漏 f 前缀的字符串**语法完全合法**，只有用户看到字面量 `{名字}` 时才知道
    出事了；except 里读 try 体内才绑定的变量同样合法，只有异常真发生时才
    `UnboundLocalError`。
    """

    def test_no_missing_f_prefix(self):
        placeholder = re.compile(r"\{[^{}\n]{1,40}\}")
        leaks = [
            (node.lineno, hit.group(0))
            for node in ast.walk(_tree())
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            for hit in placeholder.finditer(node.value)
        ]
        assert not leaks, f"这些字符串里的占位符不会被替换（漏了 f 前缀）：{leaks}"

    def test_except_does_not_read_try_bound_vars(self):
        problems = []
        for func in [
            node
            for node in ast.walk(_tree())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]:
            for func_name, lineno, name in _unbound_reads(func):
                problems.append(f"{func_name} 第{lineno}行 except 里读了 {sorted(name)}")
        assert not problems, "\n".join(problems)


def _bound_names(nodes: list[ast.AST]) -> set[str]:
    out: set[str] = set()
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                out.add(child.id)
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.add(child.name)
            if isinstance(child, ast.ExceptHandler) and child.name:
                out.add(child.name)
    return out


def _unbound_reads(func: ast.AsyncFunctionDef | ast.FunctionDef) -> list[tuple[str, int, set]]:
    """找出 `except` 里读了「同一个 try 体内才绑定」的变量的地方。"""
    report: list[tuple[str, int, set]] = []
    bound = {arg.arg for arg in func.args.args}

    def scan(nodes: list[ast.stmt]) -> None:
        for node in nodes:
            if isinstance(node, ast.Try):
                in_body = _bound_names(node.body)
                for handler in node.handlers:
                    read = {
                        child.id
                        for child in ast.walk(handler)
                        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
                    }
                    suspect = (read & in_body) - bound
                    if suspect:
                        report.append((func.name, node.lineno, suspect))
                scan(node.body)
                for handler in node.handlers:
                    scan(handler.body)
                    bound.update(_bound_names(handler.body))
                scan(node.orelse)
                scan(node.finalbody)
                bound.update(in_body)
            elif hasattr(node, "body") and isinstance(node.body, list):
                bound.update(_bound_names([node]))
                scan(node.body)

    scan(func.body)
    return report


def _help_block() -> str:
    text = MAIN_SOURCE.read_text(encoding="utf-8")
    start = text.index('_HELP_TEXT = """') + len('_HELP_TEXT = """')
    return text[start : text.index('"""', start)]


def _formal_command_names() -> set[str]:
    """`@爱完美.command("x")` 声明的正式指令名，不含别名。"""
    out: set[str] = set()
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "command"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if isinstance(node.args[0].value, str):
            out.add(node.args[0].value)
    return out


class TestHelpText:
    def test_every_command_in_help(self):
        """帮助漏一条，用户就只能靠猜或问。

        只查正式指令名：别名是给习惯写法兜底的，不必逐条列进帮助。
        """
        missing = sorted(
            name for name in _formal_command_names() if f"/爱完美 {name}" not in _help_block()
        )
        assert not missing, f"帮助文本里没列这些指令：{missing}"

    def test_help_first_line_has_product_and_game(self):
        assert _help_block().lstrip().startswith("爱完美 · ")

    def test_help_states_data_source(self):
        """说成「完美平台战绩」，用户拿官匹数据一核对会以为插件坏了。"""
        help_block = _help_block()

        assert "数据来自" in help_block
        assert "官匹" in help_block
        assert "不是完美竞技平台" in help_block

    def test_help_mentions_natural_language(self):
        assert "自然语言" in _help_block()

    def test_play_match_marked_as_simulation(self):
        """用户看到一串 K/D/A 分不出真假，帮助里要先说清楚。"""
        assert "推演" in _help_block()


class TestLoggerSource:
    """插件规范：logger 必须且只能从 `astrbot.api` 取，不许用内置 `logging`。

    爱农上架审核第一次就是被这一条驳回的（`ainong/auth/` 下两个模块用了内置
    `logging`，只看 main.py 查不出来）。这里扫整个包，防止同样的写法溜进来。
    """

    def test_package_avoids_builtin_logging(self):
        violation = [
            path.name
            for path in sorted(MAIN_SOURCE.parent.joinpath("aiwm").rglob("*.py"))
            if re.search(r"^\s*(?:import logging|from logging)\b", path.read_text("utf-8"), re.M)
        ]
        assert not violation, f"这些文件用了内置 logging，要改成从 astrbot.api 取：{violation}"

    def test_logger_from_astrbot(self):
        source = MAIN_SOURCE.read_text(encoding="utf-8")
        assert re.search(r"^from astrbot\.api import .*\blogger\b", source, re.M)


class TestBareCommandHelp:
    """只发 `/爱完美` 时回帮助，别甩框架的「参数不足」。

    2026-10-29 实测（爱瓦）：`/爱瓦 @某人` 落到框架那层，回的是「参数不足」
    加全部子命令和各自的 docstring——一大段内部说明，用户还是不知道能发什么。
    """

    @pytest.mark.parametrize("message", ["/爱完美", "爱完美", "/爱完美   ", "爱完美 "])
    def test_bare_group_is_bare_command(self, message: str):
        from aiwm.fallback import is_bare_command

        assert is_bare_command(message, "爱完美")

    @pytest.mark.parametrize(
        "message",
        ["/爱完美 战绩", "爱完美战绩", "/爱瓦 状态", "今天天气不错", ""],
    )
    def test_with_arg_or_foreign_not_bare(self, message: str):
        from aiwm.fallback import is_bare_command

        assert not is_bare_command(message, "爱完美")

    def test_filter_returns_help_not_miss_hint(self):
        source = MAIN_SOURCE.read_text(encoding="utf-8")
        body = source[source.index("class _MissFallbackFilter") :]
        body = body[: body.index("class Main(")]
        assert "is_bare_command(" in body
        assert "_HELP_TEXT" in body, "空指令要回帮助，不能只说「不是子命令」"
