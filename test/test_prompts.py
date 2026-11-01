"""提示词的测试。

提示词里那些硬性的输出格式与反端水约定是要被钉住的——模型很容易在
这些地方自由发挥，而一旦格式飘了，输出就没法直接展示给用户。
"""

from __future__ import annotations

import pytest

from aiwm.prompts import (
    FLUFF_WORDS,
    SIMULATION_NOTICE,
    TITLE_PREFIX,
    match_prompt,
    pk_prompt,
    review_prompt,
)


class TestNoFabrication:
    """日志里模型把数据当结论编：「最近18连胜只是一场幻觉」「你永远不是该
    开第一枪的那个人」。看着犀利，其实数据撑不住——它说的这些依据一条都
    不在给它的文本里。

    真正危险的是编出来的东西**看起来很有道理**，用户分辨不出来，还会照着
    改。所以提示里要写死「宁可少说一句，也不要编一句」。
    """

    @pytest.mark.parametrize(
        "prompt",
        [
            review_prompt("数据"),
            match_prompt("设定"),
            pk_prompt("甲", "乙", "对比", "占优", "甲数据", "乙数据"),
        ],
    )
    def test_says_no_fabrication(self, prompt):
        assert "只说数据支撑得住的话" in prompt
        assert "宁可少说一句，也不要编一句" in prompt

    def test_review_lists_forbidden_claims(self):
        """最容易被编的三类：无对局明细、经济数据、队友信息。"""
        prompt = review_prompt("数据")

        assert "对局明细" in prompt
        assert "经济" in prompt
        assert "队友" in prompt

    def test_data_source_is_official_matching(self):
        """不能说成「完美竞技平台」——那是替接口撒谎，用户一核对就对不上。"""
        assert "官匹" in review_prompt("数据")
        assert "完美竞技平台" not in review_prompt("数据")

    def test_match_prompt_avoids_perfect_arena(self):
        prompt = match_prompt("设定")

        assert "完美竞技平台" not in prompt
        assert "CS2 竞技" in prompt


class TestReviewPrompt:
    def test_title_prefix_fixed(self):
        """模型很爱自由发挥成「称号：xxx」，所以前后都要写一遍这个前缀。"""
        prompt = review_prompt("数据")

        assert TITLE_PREFIX in prompt
        assert f"第一行必须以「{TITLE_PREFIX}」开头" in prompt

    def test_bans_fluff_words(self):
        """对模型说「不要端水」效果一般，列具体词表才有用。"""
        prompt = review_prompt("数据")

        for word in FLUFF_WORDS:
            assert word in prompt

    def test_data_passed_through(self):
        assert "数据：\n统计场次 100（48胜52负）" in review_prompt("统计场次 100（48胜52负）")

    def test_requires_specific_numbers(self):
        prompt = review_prompt("数据")

        assert "至少出现 3 个具体数字" in prompt

    def test_names_cs2_metrics(self):
        """RWS 与 ADR 是 CS2 才有的指标，提示里要引导模型去看它们。"""
        prompt = review_prompt("数据")

        assert "ADR" in prompt
        assert "KAST" in prompt
        assert "首杀率" in prompt

    def test_requires_specific_weakness(self):
        prompt = review_prompt("数据")

        assert "必须指向数据里的具体一项" in prompt

    def test_gives_length_range(self):
        prompt = review_prompt("数据")

        assert "180 到 260 字" in prompt


class TestPkPrompt:
    def _prompt(self) -> str:
        return pk_prompt(
            "老王",
            "小明",
            "KD：老王占优（老王 1.3 / 小明 0.9）",
            "老王 1 项、小明 0 项",
            "老王数据",
            "小明数据",
        )

    def test_forbids_overriding_contrast(self):
        """让模型自己比，它最省事的答案就是「各有千秋」。"""
        prompt = self._prompt()

        assert "不要推翻对比结论" in prompt
        assert "已经替你算好了" in prompt

    def test_requires_both_numbers(self):
        prompt = self._prompt()

        assert "必须写出项名与双方数字" in prompt

    def test_advantage_count_is_reference_only(self):
        prompt = self._prompt()

        assert "占优项更多的一方不一定分数更高" in prompt
        assert "仅供参考" in prompt

    def test_score_gap_matches_reality(self):
        """分差不该为了制造对立硬拉开，两人本来就接近时就该接近。"""
        prompt = self._prompt()

        assert "分差要跟两人的实际差距相符" in prompt
        assert "敢于给大的分数差距" not in prompt

    def test_winner_matches_score(self):
        """分数与胜者由模型各写各的，不钉住就会出现 88 分输给 70 分。"""
        prompt = self._prompt()

        assert "胜者那一行写分数更高的那个人" in prompt
        assert "老王 或 小明" in prompt

    def test_both_players_data_included(self):
        prompt = self._prompt()

        assert "【老王】原始数据\n老王数据" in prompt
        assert "【小明】原始数据\n小明数据" in prompt

    def test_bans_fluff_words(self):
        prompt = self._prompt()

        for word in FLUFF_WORDS:
            assert word in prompt

    def test_roast_has_min_length(self):
        prompt = self._prompt()

        assert "至少 90 字" in prompt

    def test_roast_targets_loser(self):
        """两边都重点攻击等于没有倾向，反而像端水。"""
        prompt = self._prompt()

        assert "主要攻击输的一方最难看的那一项" in prompt
        assert "赢的一方顺带攻击一下" in prompt
        assert "不要两边都重点攻击" in prompt


class TestMatchPrompt:
    def test_marks_as_simulation(self):
        """这是整个功能最要紧的一条：用户不能以为看到的是真实战绩。

        所以「推演」这个字样要在提示里出现好几次——开头说明设定是编的、
        骨架里第一行是免责声明、硬要求里再说一遍不许省略。
        """
        prompt = match_prompt("设定")

        assert prompt.count(SIMULATION_NOTICE) >= 2
        assert "不是真实战绩" in prompt

    def test_disclaimer_in_skeleton(self):
        """输出模板的第一行就是那句声明，模型照着填才不会漏。

        按内容找而不是数索引——提示词的段落顺序以后可能调整，数索引会假红。
        """
        prompt = match_prompt("设定")
        template = [
            line.strip() for line in prompt.split("硬要求：")[0].splitlines() if line.strip()
        ]

        assert SIMULATION_NOTICE in template
        notice_pos = template.index(SIMULATION_NOTICE)
        assert template[notice_pos + 1 : notice_pos + 5] == [
            "经过：<两三句：这一局是怎么打的，节奏怎么走>",
            "亮点：<点出这局设定里最漂亮的一处，带具体数字>",
            "问题：<点出这局设定里最难看的一处，带具体数字>",
            "复盘：<一句下次该怎么做>",
        ], "声明后面要紧跟四个小标题，那是输出模板"

    def test_hard_requirements_say_no_omission(self):
        prompt = match_prompt("设定")

        assert "不许改写、不许省略" in prompt
        assert f"第一行必须是「{SIMULATION_NOTICE}」" in prompt

    def test_section_labels_kept(self):
        """标题飘了输出就没法直接展示，要靠这几行钉住。"""
        prompt = match_prompt("设定")

        for title in ("经过：", "亮点：", "问题：", "复盘："):
            assert title in prompt

    def test_highlights_and_problems_have_numbers(self):
        """只要数字出现在全文就够了——分得太细模型会写得很别扭。"""
        prompt = match_prompt("设定")

        assert "「亮点」和「问题」各必须出现设定里的至少一个数字" in prompt

    def test_setup_passed_through(self):
        prompt = match_prompt("地图：远古遗迹\n击杀：16")

        assert "这局的设定：\n地图：远古遗迹\n击杀：16" in prompt

    def test_never_presents_setup_as_real(self):
        """提示里要明确设定是随机生成的，别让模型当成用户的历史数据。"""
        prompt = match_prompt("设定")

        assert "数字是随机生成的" in prompt
