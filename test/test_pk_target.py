"""PK 对手识别的测试。

重点是「从参数里直接抠 steamid」这条：实测用户发了 Steam 个人资料页链接想
PK，而当时对方必须先绑定，整件事没成。
"""

from __future__ import annotations

from aiwm.pk_target import OpponentSource, looks_like_id_text, looks_like_steamid, resolve_opponent


class Test判对手steamid:
    def test_纯数字(self):
        assert looks_like_steamid("76561198829920790") == "76561198829920790"

    def test_从网址里抠(self):
        assert (
            looks_like_steamid("https://steamcommunity.com/profiles/76561198829920790")
            == "76561198829920790"
        )

    def test_从启动器参数里抠(self):
        assert (
            looks_like_steamid("steam.exe -login 76561198829920790 -language schinese")
            == "76561198829920790"
        )

    def test_夹在中文句子里(self):
        assert looks_like_steamid("跟 76561198829920790 比一下") == "76561198829920790"

    def test_多个id时不猜(self):
        """粘了一堆东西进来，让用户说清要哪个。"""
        assert looks_like_steamid("76561198829920790 和 76561198412825279") is None

    def test_昵称不是id(self):
        assert looks_like_steamid("小明") is None

    def test_空(self):
        assert looks_like_steamid("") is None
        assert looks_like_steamid(None) is None

    def test_长数字不截(self):
        """18 位里截一段会得到一个看起来合法、实际是别人的号。"""
        assert looks_like_steamid("765611988299207901") is None


class Test取对手标识:
    def test_参数里有id就用它(self):
        steamid, 来源, 记录 = resolve_opponent("76561198829920790", None, lambda 名: (0, None))

        assert steamid == "76561198829920790"
        assert 来源 == OpponentSource.FROM_ARG
        assert 记录 is None

    def test_参数优先于at组件(self):
        """参数里明写了 id，就用那个——@ 组件可能是误@。"""
        steamid, 来源, _ = resolve_opponent(
            "76561198829920790", "someone-else", lambda 名: (0, None)
        )

        assert steamid == "76561198829920790"
        assert 来源 == OpponentSource.FROM_ARG

    def test_没有id才用at组件(self):
        steamid, 来源, _ = resolve_opponent("小明", "user-123", lambda 名: (0, None))

        assert steamid == "user-123"
        assert 来源 == OpponentSource.FROM_AT

    def test_最后才按昵称找(self):
        def 按昵称找(名):
            return 1, {"steamid": "76561198000000001", "用户": "u2"}

        steamid, 来源, 记录 = resolve_opponent("小明", None, 按昵称找)

        assert steamid == "76561198000000001"
        assert 来源 == OpponentSource.FROM_NICKNAME
        assert 记录["用户"] == "u2"

    def test_都没有就是没找到(self):
        steamid, 来源, 记录 = resolve_opponent("查无此人", None, lambda 名: (0, None))

        assert steamid == ""
        assert 来源 == OpponentSource.NOT_FOUND
        assert 记录 is None


class Test像标识文本:
    def test_纯数字像标识(self):
        assert looks_like_id_text("76561198829920790") is True

    def test_纯中文不像(self):
        assert looks_like_id_text("小明") is False

    def test_网址像标识(self):
        assert looks_like_id_text("https://steamcommunity.com/profiles/7656") is True

    def test_空不像(self):
        assert looks_like_id_text("") is False
