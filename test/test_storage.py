"""存储与 steamid 校验的测试。"""

from __future__ import annotations

import pytest

from aiwm.storage import (
    CredentialStore,
    clean_nickname,
    extract_steamids,
    how_to_find_steamid,
    is_valid_steamid,
    resolve_steamid,
)


class TestExtractSteamIds:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("76561198159976336", ["76561198159976336"]),
            (
                "https://steamcommunity.com/profiles/76561198159976336",
                ["76561198159976336"],
            ),
            ("steam.exe -login 76561198159976336", ["76561198159976336"]),
            ("我的号是76561198159976336谢谢", ["76561198159976336"]),
            ("（76561198159976336）", ["76561198159976336"]),
        ],
    )
    def test_extracts_from_common_shapes(self, raw, expected):
        assert extract_steamids(raw) == expected

    def test_long_number_not_cut(self):
        """18 位数字里截一段 17 位，会得到一个看起来合法、实际是别人的号。"""
        assert extract_steamids("765611981599763367") == []

    def test_decimal_digits_ignored(self):
        assert extract_steamids("1.76561198159976336") == []

    def test_dedupes_keeping_order(self):
        text = "第二个 76561198159976336 第一个 76561198000000001 又 76561198159976336"

        assert extract_steamids(text) == ["76561198159976336", "76561198000000001"]

    def test_none_is_empty(self):
        assert extract_steamids("随便一句话") == []
        assert extract_steamids("") == []
        assert extract_steamids(None) == []

    def test_short_digits_ignored(self):
        assert extract_steamids("76561198") == []


class TestResolveSteamId:
    def test_plain_digits_accepted(self):
        assert resolve_steamid("76561198159976336") == "76561198159976336"

    def test_from_profile_url(self):
        assert (
            resolve_steamid("https://steamcommunity.com/profiles/76561198159976336")
            == "76561198159976336"
        )

    def test_from_launcher_args(self):
        assert resolve_steamid("steam.exe -login 76561198159976336 -language schinese") == (
            "76561198159976336"
        )

    def test_trims_and_extracts(self):
        assert resolve_steamid("  76561198159976336  ") == "76561198159976336"

    def test_no_guess_with_many(self):
        """粘了一堆东西进来时，让用户说清要哪个，而不是随便挑一个。"""
        with pytest.raises(ValueError, match="好几个"):
            resolve_steamid("76561198159976336 和 76561198000000001")

    def test_gives_hint_when_missing(self):
        with pytest.raises(ValueError, match="没找到"):
            resolve_steamid("我不知道我的号")

    def test_error_mentions_how_to_find(self):
        """用户看到的是怎么找，不是只知道自己错了。"""
        with pytest.raises(ValueError) as wrong:
            resolve_steamid("abc")

        assert how_to_find_steamid() in str(wrong.value)

    def test_long_content_truncated(self):
        """贴了一整篇日志进来时，错误信息别把全文回显一遍。"""
        with pytest.raises(ValueError) as wrong:
            resolve_steamid("啊" * 200)

        assert "…" in str(wrong.value)
        assert len(str(wrong.value)) < 200


class TestSteamIdValidation:
    @pytest.mark.parametrize(
        "candidates",
        [
            "76561198159976336",
            # 实测这个号就是 76561198 开头，第 8 位是 8——别对中间位做白名单
            "70000000000000000",
            "79999999999999999",
        ],
    )
    def test_valid_value(self, candidates):
        assert is_valid_steamid(candidates) is True

    @pytest.mark.parametrize(
        "candidates",
        [
            "",
            "7656119815997633",  # 只有 16 位
            "765611981599763367",  # 18 位
            "66561198159976336",  # 首位不是 7
            "7656119815997633a",  # 含字母
            "7656119815997633 ",  # 尾部单个空格（不是整体前后空白）
            "  ",
        ],
    )
    def test_invalid_value(self, candidates):
        assert is_valid_steamid(candidates) is False

    def test_whitespace_both_sides_ok(self):
        assert is_valid_steamid("  76561198159976336  ") is True

    def test_invalid_value_error_shows_format(self):
        with pytest.raises(ValueError, match="17 位数字"):
            resolve_steamid("abc")

    def test_valid_value_trimmed(self):
        assert resolve_steamid("  76561198159976336 ") == "76561198159976336"


class TestCredentialStore:
    def test_read_back_after_write(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("用户甲", "76561198159976336", nickname="老王")

        record = store.read("用户甲")
        assert record["steamid"] == "76561198159976336"
        assert record["昵称"] == "老王"

    def test_filename_is_not_user_id(self, tmp_path):
        """用户标识可能带 @ 和斜杠，不能直接当文件名。"""
        store = CredentialStore(tmp_path)
        store.write("QQ号@某设备/1", "76561198159976336")

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert "@" not in files[0].name

    def test_invalid_steamid_not_bound(self, tmp_path):
        """手工改坏的文件不该被当成有效绑定，否则查询时才报错。"""
        store = CredentialStore(tmp_path)
        store.write("用户甲", "76561198159976336")
        store.path_for("用户甲").write_text('{"steamid": "坏值"}', encoding="utf-8")

        assert store.read("用户甲") is None
        assert store.iter_all() == []

    def test_find_by_nickname_exact_first(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336", nickname="小明")
        store.write("乙", "76561198159976337", nickname="小明强")

        exact = store.find_by_nickname("小明")
        assert [record["steamid"] for record in exact] == ["76561198159976336"]

    def test_find_by_nickname_case_insensitive(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336", nickname="ZnNe")

        assert store.find_by_nickname("znne") == store.find_by_nickname("ZnNe")
        assert len(store.find_by_nickname("znne")) == 1

    def test_find_by_nickname_empty(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336", nickname="小明")

        assert store.find_by_nickname("") == []
        assert store.find_by_nickname("   ") == []

    def test_read_after_delete_is_none(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336")

        assert store.delete("甲") is not None
        assert store.read("甲") is None
        assert store.delete("甲") is None

    def test_corrupt_json_no_raise(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336")
        store.path_for("甲").write_text("{不是 JSON", encoding="utf-8")

        assert store.read("甲") is None
        assert store.iter_all() == []


class TestCleanNickname:
    """昵称会拼进 PK 提示词：换行能伪造指令，零宽字符能让两个名字看着一样。"""

    def test_strips_newline_and_tab(self):
        assert clean_nickname("老\n王\t") == "老王"

    def test_strips_zero_width(self):
        assert clean_nickname("老\u200b王") == "老王"

    def test_trims_whitespace(self):
        assert clean_nickname("  老王  ") == "老王"

    def test_empty_value_no_raise(self):
        assert clean_nickname("") == ""
        assert clean_nickname(None) == ""
