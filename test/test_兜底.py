"""指令落空时的兜底。

`/爱完美 <任意内容>` 时，如果没有子命令匹配上，`CommandGroupFilter.filter`
会返回 False，指令被跳过，**消息原样进模型**。于是模型把它当成一句提问，
自己编答案——实测过用户发 `/爱完美 <steam 链接>`，模型回「打不开Steam，你发
链接干嘛，考验我视力？」，还自称「我又没权限爬Steam」。

用户没打错指令，是这条指令没接住。所以组里要挂一个兜底过滤器：匹配了组名
但没匹配任何子命令时，自己回一句提示，不让消息落到模型手上。

这些测试不 import `main.py`（它顶层 import astrbot，本地跑不了），只测本模块
里的纯函数。
"""

from __future__ import annotations

import pytest

from aiwm.fallback import (
    SUBCOMMANDS,
    is_command_miss,
    leftover_arg,
    miss_hint,
    starts_with_group,
)


class TestLeftoverArg:
    def test_extracts_arg_after_group(self):
        assert leftover_arg("/爱完美 https://x.com/profiles/7656", "爱完美") == (
            "https://x.com/profiles/7656"
        )

    def test_leading_slash_and_spaces(self):
        assert leftover_arg("/爱完美   76561198829920790", "爱完美") == "76561198829920790"

    def test_bare_group_is_bare(self):
        assert leftover_arg("/爱完美", "爱完美") == ""

    def test_accepts_missing_slash(self):
        """有些平台的消息不会带 `/`。"""
        assert leftover_arg("爱完美 绑定", "爱完美") == "绑定"

    def test_uses_first_group_occurrence(self):
        assert leftover_arg("/爱完美 /爱完美 战绩", "爱完美") == "/爱完美 战绩"


class TestSubcommands:
    def test_knows_every_subcommand(self):
        for name in ("战绩", "锐评", "开一局", "PK", "昵称", "解绑", "状态", "帮助", "绑定"):
            assert name in SUBCOMMANDS

    def test_knows_aliases(self):
        """别名也要认，否则用户打 `/爱完美 开局` 照样落空。"""
        for alias in ("pk", "对战", "开局", "来一局", "help", "菜单", "status"):
            assert alias in SUBCOMMANDS

    def test_case_insensitive(self):
        assert "PK" in SUBCOMMANDS
        assert "pk" in SUBCOMMANDS


class TestMissHint:
    def test_points_to_bind(self):
        """落空的最常见原因是没绑定，或用户以为发 id 就行。"""
        hint = miss_hint("76561198829920790")

        assert "绑定" in hint

    def test_echoes_arg_back(self):
        """用户不用重新打字。"""
        hint = miss_hint("76561198829920790")

        assert "76561198829920790" in hint

    def test_no_arg_points_to_help(self):
        """只留一句出口，不再复述一份迷你菜单。"""
        hint = miss_hint("")

        assert "/爱完美 帮助" in hint

    def test_no_link_echo(self):
        """别再教用户发链接了，那条路走不通——Steam 社区站要登录态，
        而且插件也没必要去查别人的主页。"""
        hint = miss_hint("https://steamcommunity.com/profiles/7656")

        assert "链接" not in hint or "绑" in hint

    def test_short_is_kept(self):
        """落空说明要短，太长就成了第二份帮助文本。"""
        assert len(miss_hint("76561198829920790")) <= 120

    def test_empty_arg_no_raise(self):
        assert miss_hint("").strip()


class TestScope:
    @pytest.mark.parametrize(
        ("message", "expect_miss"),
        [
            ("/爱完美 战绩", False),
            ("/爱完美 锐评", False),
            ("/爱完美 开一局", False),
            ("/爱完美 开局", False),
            ("/爱完美 来一局", False),
            ("/爱完美 PK 老王", False),
            ("/爱完美 pk 老王", False),
            ("/爱完美 对战 老王", False),
            ("/爱完美 昵称 老王", False),
            ("/爱完美 绑定 76561198829920790", False),
            ("/爱完美 帮助", False),
            ("/爱完美 help", False),
            # 这些才是真的落空：该走绑定或别的子命令
            ("/爱完美 76561198829920790", True),
            ("/爱完美 https://steamcommunity.com/profiles/7656", True),
            ("/爱完美 我的战绩怎么样", True),
        ],
    )
    def test_only_real_miss_counts(self, message, expect_miss):
        """正常子命令与别名都走各自指令，别被兜底吃掉。

        顺带验「该拦」本身——上一版只断言了前半段，把后半段改成永远 False
        测试也不红，等于没钉。
        """
        assert is_command_miss(message, "爱完美") is expect_miss

    def test_without_slash_still_counts(self):
        """有些平台的消息不带 `/`，只按带斜杠的形式判会漏掉。"""
        arg = leftover_arg("爱完美 76561198829920790", "爱完美")

        assert arg == "76561198829920790"
        assert not any(arg.startswith(name) for name in SUBCOMMANDS)

    def test_other_plugin_not_ours(self):
        """`/爱农 开一局` 是另一个插件的，不能被这里抢走。

        注意：这个 filter **会**被调用。`CommandGroupFilter.filter` 的执行
        顺序是先跑 `custom_filter_ok()`、之后才检查组名是否匹配，所以挂在
        指令组上的过滤器对每一条消息都执行。
        原实现里 `取落空参数` 对非本组消息「原样返回」，于是
        `/爱农 开一局` 被判定成「爱完美的子命令落空」，`stop_event()` 把整条
        掐死——不只爱农，连「在吗」这种纯聊天也会被掐，老狗直接不理人。
        所以非本组消息必须返回**空串**，让调用方一眼看出不归自己管。
        """
        assert leftover_arg("/爱农 开一局", "爱完美") == ""
        assert not is_command_miss("/爱农 开一局", "爱完美")
        assert not is_command_miss("爱瓦 绑定", "爱完美")

    @pytest.mark.parametrize(
        "message",
        ["在吗", "", "今天天气不错", "爱农 状态", "爱瓦 绑定", "/help"],
    )
    def test_foreign_message_passes(self, message):
        """这六条都实测掐过（`老狗不理人`）。"""
        assert not is_command_miss(message, "爱完美"), f"{message!r} 被误判成爱完美的落空"

    @pytest.mark.parametrize(
        "message",
        ["/爱完美 绑定", "爱完美 绑定", "/爱完美 战绩", "爱完美 PK 老王", "/爱完美 help"],
    )
    def test_valid_command_passes(self, message):
        assert not is_command_miss(message, "爱完美"), f"{message!r} 是正常指令，不该判成落空"

    def test_starts_with_group(self):
        assert starts_with_group("爱完美 绑定", "爱完美")
        assert starts_with_group("/爱完美 绑定", "爱完美")
        assert not starts_with_group("爱农 开一局", "爱完美")
        assert not starts_with_group("在吗", "爱完美")
        assert not starts_with_group("", "爱完美")
