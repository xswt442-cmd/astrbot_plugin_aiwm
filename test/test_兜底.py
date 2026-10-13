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

from aiwm.兜底 import (
    以组名开头,
    取落空参数,
    子命令名,
    是否落空,
    落空提示,
)


class Test取落空参数:
    def test_取出组名后面的内容(self):
        assert 取落空参数("/爱完美 https://x.com/profiles/7656", "爱完美") == (
            "https://x.com/profiles/7656"
        )

    def test_带开头的斜杠与空格(self):
        assert 取落空参数("/爱完美   76561198829920790", "爱完美") == "76561198829920790"

    def test_只有组名时是空(self):
        assert 取落空参数("/爱完美", "爱完美") == ""

    def test_没带斜杠也认(self):
        """有些平台的消息不会带 `/`。"""
        assert 取落空参数("爱完美 绑定", "爱完美") == "绑定"

    def test_组名出现两次时取第一个之后的(self):
        assert 取落空参数("/爱完美 /爱完美 战绩", "爱完美") == "/爱完美 战绩"


class Test子命令名:
    def test_认得各个子命令(self):
        for 名 in ("战绩", "锐评", "开一局", "PK", "昵称", "解绑", "状态", "帮助", "绑定"):
            assert 名 in 子命令名

    def test_认得别名(self):
        """别名也要认，否则用户打 `/爱完美 开局` 照样落空。"""
        for 别名 in ("pk", "对战", "开局", "来一局", "help", "菜单", "status"):
            assert 别名 in 子命令名

    def test_认得大小写差异(self):
        assert "PK" in 子命令名
        assert "pk" in 子命令名


class Test落空提示:
    def test_指向绑定(self):
        """落空的最常见原因是没绑定，或用户以为发 id 就行。"""
        提示 = 落空提示("76561198829920790")

        assert "绑定" in 提示

    def test_把参数原样带回去(self):
        """用户不用重新打字。"""
        提示 = 落空提示("76561198829920790")

        assert "76561198829920790" in 提示

    def test_没参数时列出指令(self):
        提示 = 落空提示("")

        assert "战绩" in 提示
        assert "帮助" in 提示

    def test_不给链接(self):
        """别再教用户发链接了，那条路走不通——Steam 社区站要登录态，
        而且插件也没必要去查别人的主页。"""
        提示 = 落空提示("https://steamcommunity.com/profiles/7656")

        assert "链接" not in 提示 or "绑" in 提示

    def test_不长(self):
        """落空说明要短，太长就成了第二份帮助文本。"""
        assert len(落空提示("76561198829920790")) <= 120

    def test_空参数不抛(self):
        assert 落空提示("").strip()


class Test该拦不该拦:
    @pytest.mark.parametrize(
        ("消息", "期望落空"),
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
    def test_只有真落空才算落空(self, 消息, 期望落空):
        """正常子命令与别名都走各自指令，别被兜底吃掉。

        顺带验「该拦」本身——上一版只断言了前半段，把后半段改成永远 False
        测试也不红，等于没钉。
        """
        assert 是否落空(消息, "爱完美") is 期望落空

    def test_不带斜杠也算本组(self):
        """有些平台的消息不带 `/`，只按带斜杠的形式判会漏掉。"""
        参数 = 取落空参数("爱完美 76561198829920790", "爱完美")

        assert 参数 == "76561198829920790"
        assert not any(参数.startswith(名) for 名 in 子命令名)

    def test_别的插件的指令不算本组(self):
        """`/爱农 开一局` 是另一个插件的，不能被这里抢走。

        注意：这个 filter **会**被调用。`CommandGroupFilter.filter` 的执行
        顺序是先跑 `custom_filter_ok()`、之后才检查组名是否匹配，所以挂在
        指令组上的过滤器对每一条消息都执行。
        原实现里 `取落空参数` 对非本组消息「原样返回」，于是
        `/爱农 开一局` 被判定成「爱完美的子命令落空」，`stop_event()` 把整条
        掐死——不只爱农，连「在吗」这种纯聊天也会被掐，老狗直接不理人。
        所以非本组消息必须返回**空串**，让调用方一眼看出不归自己管。
        """
        assert 取落空参数("/爱农 开一局", "爱完美") == ""
        assert not 是否落空("/爱农 开一局", "爱完美")
        assert not 是否落空("爱瓦 绑定", "爱完美")

    @pytest.mark.parametrize(
        "消息",
        ["在吗", "", "今天天气不错", "爱农 状态", "爱瓦 绑定", "/help"],
    )
    def test_陌生消息一律放行(self, 消息):
        """这六条都实测掐过（`老狗不理人`）。"""
        assert not 是否落空(消息, "爱完美"), f"{消息!r} 被误判成爱完美的落空"

    @pytest.mark.parametrize(
        "消息",
        ["/爱完美 绑定", "爱完美 绑定", "/爱完美 战绩", "爱完美 PK 老王", "/爱完美 help"],
    )
    def test_本组正常指令放行(self, 消息):
        assert not 是否落空(消息, "爱完美"), f"{消息!r} 是正常指令，不该判成落空"

    def test_以组名开头(self):
        assert 以组名开头("爱完美 绑定", "爱完美")
        assert 以组名开头("/爱完美 绑定", "爱完美")
        assert not 以组名开头("爱农 开一局", "爱完美")
        assert not 以组名开头("在吗", "爱完美")
        assert not 以组名开头("", "爱完美")
