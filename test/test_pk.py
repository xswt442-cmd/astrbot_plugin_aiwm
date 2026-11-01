"""PK 目标解析的测试。"""

from __future__ import annotations

from dataclasses import dataclass

from aiwm.pk import FAKE_MENTION_IDS, find_opponent


@dataclass
class AtComponent:
    qq: str


class TestAtComponent:
    def test_reads_id_from_component(self):
        assert find_opponent([AtComponent("2A8FDBA1")], "") == "2A8FDBA1"

    def test_excludes_bot(self):
        """群里 @机器人 同样会生成一个 At 组件，不排掉就把机器人当成对手。"""
        assert find_opponent([AtComponent("机器人")], "", me="甲", bot_id="机器人") is None

    def test_excludes_sender(self):
        assert find_opponent([AtComponent("甲")], "", me="甲") is None

    def test_excludes_known_placeholders(self):
        for fake in FAKE_MENTION_IDS:
            assert find_opponent([AtComponent(fake)], "") is None

    def test_non_at_component_skipped(self):
        class other_component:
            qq = None

        assert find_opponent([other_component()], "") is None

    def test_component_without_qq_no_crash(self):
        class no_attr:
            pass

        assert find_opponent([no_attr()], "") is None

    def test_picks_first_usable_component(self):
        assert (
            find_opponent([AtComponent("机器人"), AtComponent("小明")], "", bot_id="机器人")
            == "小明"
        )


class TestTextMention:
    def test_angle_bracket_form(self):
        assert find_opponent([], "<@2A8FDBA1>") == "2A8FDBA1"

    def test_bang_form(self):
        assert find_opponent([], "<@!2A8FDBA1>") == "2A8FDBA1"

    def test_too_short_noise_filtered(self):
        assert find_opponent([], "<@!1>") is None

    def test_excludes_self(self):
        assert find_opponent([], "<@!甲甲甲甲甲>", me="甲甲甲甲甲") is None

    def test_component_wins_over_text(self):
        assert find_opponent([AtComponent("组件里的")], "<@!正文里的>") == "组件里的"


class TestNotFound:
    def test_empty_message_returns_none(self):
        assert find_opponent([], "") is None

    def test_plain_text_returns_none(self):
        """昵称是 main.py 那边另一条路径处理的，这里只管标识。"""
        assert find_opponent([], "/爱完美 PK 小明") is None

    def test_none_message_list_no_crash(self):
        assert find_opponent(None, "") is None
