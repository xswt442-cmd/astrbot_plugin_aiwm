"""「开一局」的对局设定的测试。

这些数字要像真人打出来的：击杀不能均匀分布，胜的局个人表现不能太拉，
武器命中率要落在该枪的合理区间。测试钉的是这些约束。
"""

from __future__ import annotations

import random
import statistics

from aiwm.match import (
    WEAPON_CATEGORIES,
    build_match_setup,
    pick_map,
    pick_weapon,
    setup_text,
    skill_profile,
)

_with_stats = {
    "总场次": 100,
    "KD": 1.24,
    "爆头率": 54.7,
    "段位分": 20620,
    "近十场评分": [2.19, 0.94, 0.66],
}


def _run_rounds(stats=None, rounds=300):
    rng = random.Random(20261012)
    return [build_match_setup(rng, stats) for _ in range(rounds)]


class TestScoreAndFormat:
    def test_winner_reaches_13(self):
        """CS2 竞技是打到 13 分，不是打满固定局数。"""
        for setup in _run_rounds(rounds=200):
            mine, opponent = (int(v) for v in setup["比分"].split(":"))
            assert 13 in (mine, opponent), f"{setup['比分']} 两边都没到 13"

    def test_winner_side_is_13(self):
        for setup in _run_rounds(rounds=200):
            mine, opponent = (int(v) for v in setup["比分"].split(":"))
            winner_side = mine if setup["是否胜利"] else opponent
            assert winner_side == 13

    def test_loser_side_at_most_12(self):
        for setup in _run_rounds(rounds=200):
            mine, opponent = (int(v) for v in setup["比分"].split(":"))
            loser_side = opponent if setup["是否胜利"] else mine
            assert 0 <= loser_side <= 12

    def test_results_roughly_even(self):
        """长期看胜率该在 50% 附近，否则用户会觉得插件偏帮他不帮他。"""
        match_count = _run_rounds(rounds=600)
        win_rate = sum(1 for setup in match_count if setup["是否胜利"]) / len(match_count)

        assert 0.42 <= win_rate <= 0.58, f"胜率 {win_rate:.2%} 偏得厉害"


class TestPersonalPerformance:
    def test_kills_not_negative(self):
        for setup in _run_rounds(rounds=200):
            assert setup["击杀"] >= 0

    def test_deaths_at_least_one(self):
        """死了零次的一局在 CS2 里不存在，除非整局没交火。"""
        for setup in _run_rounds(rounds=200):
            assert setup["死亡"] >= 1

    def test_headshots_not_above_kills(self):
        for setup in _run_rounds(rounds=200):
            assert setup["爆头数"] <= setup["击杀"]

    def test_accuracy_within_weapon_range(self):
        """AWP 的命中率天然高于步枪，用同一套区间会立刻露馅。"""
        for setup in _run_rounds(rounds=200):
            lower, upper = WEAPON_CATEGORIES[setup["武器"]]
            assert lower * 100 <= setup["命中率"] <= upper * 100, (
                f"{setup['武器']} 的命中率 {setup['命中率']} 越界"
                f"（应在 {lower * 100}~{upper * 100}）"
            )

    def test_rating_at_most_2(self):
        for setup in _run_rounds(rounds=200):
            assert 0 <= setup["评级"] <= 2

    def test_rating_near_reference(self):
        """一局里评级不会比平时水平差太多。"""
        match_count = _run_rounds(_with_stats, rounds=300)
        mean = statistics.mean(setup["评级"] for setup in match_count)

        assert 0.7 <= mean <= 2.0, f"评级均值 {mean:.2f} 偏离参照的 2.19 太多"

    def test_works_without_history(self):
        for setup in _run_rounds(None, rounds=100):
            assert setup["击杀"] >= 0
            assert setup["评级"] >= 0


class TestLevelFit:
    def test_level_from_tier(self):
        rng = random.Random(1)

        assert "白银" in skill_profile(rng, 3000)
        assert "神话" in skill_profile(rng, 20620)
        assert "超凡" in skill_profile(rng, 26000)

    def test_higher_tier_more_kills(self):
        """同样 300 局，高手该打得比新手多。"""
        expert = _run_rounds({**_with_stats, "KD": 1.8}, rounds=300)
        newbie = _run_rounds({**_with_stats, "KD": 0.6}, rounds=300)

        assert statistics.mean(s["击杀"] for s in expert) > statistics.mean(
            s["击杀"] for s in newbie
        )

    def test_level_in_setup(self):
        match_count = _run_rounds(_with_stats, rounds=20)

        assert all(setup["水平"] != "无历史数据，取中等水平" for setup in match_count)


class TestPickMapAndWeapon:
    def test_map_from_real_pool(self):
        rng = random.Random(7)
        map_set = {pick_map(rng) for _ in range(200)}

        assert map_set <= {
            "远古遗迹",
            "炼狱小镇",
            "荒漠迷城",
            "核子危机",
            "死城之谜",
            "列车停放站",
            "古堡激战",
        }

    def test_every_weapon_has_accuracy_range(self):
        """`_加权取` 与 `武器类别` 是两套表，漏配就会在生成时 KeyError。"""
        rng = random.Random(7)
        for _ in range(300):
            assert pick_weapon(rng) in WEAPON_CATEGORIES

    def test_rifles_more_common_than_pistols(self):
        rng = random.Random(7)
        weapon = [pick_weapon(rng) for _ in range(600)]
        rifle = sum(1 for name in weapon if name in ("AK47", "M4A4", "M4A1消音型"))

        assert rifle > len(weapon) * 0.5, f"步枪只占 {rifle / len(weapon):.0%}，不像真人"


class TestOutputText:
    def test_every_field_in_text(self):
        """结构化输出靠这段文字，漏一项模型就不知道该说什么。"""
        setup = _run_rounds(_with_stats, rounds=1)[0]
        text = setup_text(setup)

        for key in ("地图", "武器", "比分", "击杀", "命中率", "评级", "水平"):
            assert key in text, f"{key} 没出现在设定文本里"

    def test_score_shows_result(self):
        setup = _run_rounds(_with_stats, rounds=1)[0]
        text = setup_text(setup)

        assert "胜" in text or "负" in text

    def test_raw_stats_not_in_text(self):
        """设定文本只讲这一局，不该把玩家历史数据混进来——那会让模型混淆推演与事实。"""
        setup = _run_rounds(_with_stats, rounds=1)[0]
        text = setup_text(setup)

        assert "20620" not in text
        assert "100" not in text
