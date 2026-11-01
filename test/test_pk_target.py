"""PK 对手识别的测试。

重点是「从参数里直接抠 steamid」这条：实测用户发了 Steam 个人资料页链接想
PK，而当时对方必须先绑定，整件事没成。
"""

from __future__ import annotations

from aiwm.pk_target import OpponentSource, looks_like_id_text, looks_like_steamid, resolve_opponent


class TestLooksLikeSteamId:
    def test_digits_only(self):
        assert looks_like_steamid("76561198829920790") == "76561198829920790"

    def test_extracts_from_profile_url(self):
        assert (
            looks_like_steamid("https://steamcommunity.com/profiles/76561198829920790")
            == "76561198829920790"
        )

    def test_extracts_from_launcher_args(self):
        assert (
            looks_like_steamid("steam.exe -login 76561198829920790 -language schinese")
            == "76561198829920790"
        )

    def test_id_inside_chinese_sentence(self):
        assert looks_like_steamid("跟 76561198829920790 比一下") == "76561198829920790"

    def test_no_guess_with_multiple_ids(self):
        """粘了一堆东西进来，让用户说清要哪个。"""
        assert looks_like_steamid("76561198829920790 和 76561198412825279") is None

    def test_nickname_is_not_id(self):
        assert looks_like_steamid("小明") is None

    def test_empty(self):
        assert looks_like_steamid("") is None
        assert looks_like_steamid(None) is None

    def test_long_number_not_truncated(self):
        """18 位里截一段会得到一个看起来合法、实际是别人的号。"""
        assert looks_like_steamid("765611988299207901") is None


class TestResolveOpponent:
    def test_uses_id_from_arg(self):
        steamid, source, record = resolve_opponent(
            "76561198829920790", None, lambda name: (0, None)
        )

        assert steamid == "76561198829920790"
        assert source == OpponentSource.FROM_ARG
        assert record is None

    def test_arg_wins_over_at(self):
        """参数里明写了 id，就用那个——@ 组件可能是误@。"""
        steamid, source, _ = resolve_opponent(
            "76561198829920790", "someone-else", lambda name: (0, None)
        )

        assert steamid == "76561198829920790"
        assert source == OpponentSource.FROM_ARG

    def test_at_used_when_no_id(self):
        steamid, source, _ = resolve_opponent("小明", "user-123", lambda name: (0, None))

        assert steamid == "user-123"
        assert source == OpponentSource.FROM_AT

    def test_nickname_lookup_is_last(self):
        def find_by_nickname(name):
            return 1, {"steamid": "76561198000000001", "用户": "u2"}

        steamid, source, record = resolve_opponent("小明", None, find_by_nickname)

        assert steamid == "76561198000000001"
        assert source == OpponentSource.FROM_NICKNAME
        assert record["用户"] == "u2"

    def test_nothing_found(self):
        steamid, source, record = resolve_opponent("查无此人", None, lambda name: (0, None))

        assert steamid == ""
        assert source == OpponentSource.NOT_FOUND
        assert record is None


class TestLooksLikeIdText:
    def test_digits_look_like_id(self):
        assert looks_like_id_text("76561198829920790") is True

    def test_chinese_only_not_id(self):
        assert looks_like_id_text("小明") is False

    def test_url_looks_like_id(self):
        assert looks_like_id_text("https://steamcommunity.com/profiles/7656") is True

    def test_empty_not_id(self):
        assert looks_like_id_text("") is False
