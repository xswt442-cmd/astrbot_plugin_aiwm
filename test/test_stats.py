"""战绩统计的测试。

覆盖三件事：字段与量纲映射正确、缺字段时那一项从文本里消失、对比由代码算死。

测试用构造的数据而不是录制快照，所以**字段名与量纲必须与接口一致**，否则
这些断言会保护着一份已经不存在的协议。改动协议相关代码时，先用
`test/verify_wmpvp.py` 打一次真实接口，把真实返回里的字段名与量纲核对一遍
再改这里的断言。
"""

from __future__ import annotations

import pytest

from aiwm.stats import (
    advantage_count,
    contrast_points,
    contrast_text,
    summarize,
    summary_text,
    tier_name,
)

# 字段名与量纲照真实响应写：比率给的是 0~1 的小数，只有 kast 已经是百分数；
# cnt 与 historyWinCount 不是同一个池子；historyRatings 与 historyDates 长度
# 不一致。这几条都是量过真实响应才定下来的。
_full_response = {
    "steamId": "76561198000000000",
    "nickName": "示例昵称",
    "cnt": 100,
    "historyWinCount": 679,
    "winRate": 0.48,
    "kd": 1.24,
    "rating": 1.21,
    "adr": 95.64,
    "kast": 74,
    "rws": 12.07,
    "headShotRatio": 0.547,
    "entryKillRatio": 0.17,
    "awpKillRatio": 0.05,
    "flashSuccessRatio": 0.57,
    "rank": 20620,
    "endingWin": 44,
    "hours": 1188,
    "k3": 106,
    "k4": 38,
    "k5": 1,
    "hotMaps": [
        {"map": "de_ancient", "mapName": "远古遗迹", "totalMatch": 24},
        {"map": "de_inferno", "mapName": "炼狱小镇", "totalMatch": 19},
    ],
    "hotWeapons": [
        {"weaponName": "M4A1消音型", "weaponKill": 330, "weaponHeadShot": 130, "totalMatch": 68},
        {"weaponName": "AK47", "weaponKill": 753, "weaponHeadShot": 444, "totalMatch": 96},
    ],
    "historyRatings": [2.19, 0.94, 0.66, 1.24, 1.58, 0.67, 0.99, 1.03, 1.73, 1.7],
    # 真实响应里日期比评分长，两条数组不是一一对应的
    "historyDates": [f"2026-10-0{i} 20:00:00" for i in range(1, 31)],
}


class TestFieldMapping:
    def test_core_metrics_parsed(self):
        stats = summarize(_full_response)

        assert stats["总场次"] == 100
        assert stats["段位分"] == 20620
        assert stats["KD"] == 1.24
        assert stats["ADR"] == 95.64
        assert stats["昵称"] == "示例昵称"

    def test_ratio_to_percent(self):
        stats = summarize(_full_response)

        # 接口给的是 0.48 / 0.547 这样的比率
        assert stats["胜率"] == 48.0
        assert stats["爆头率"] == 54.7
        assert stats["首杀率"] == 17.0

    def test_kast_is_already_percent(self):
        """`kast` 给的是 74 而不是 0.74，套上换算会变成 7400%。"""
        stats = summarize(_full_response)

        assert stats["KAST"] == 74.0

    def test_losses_derived_from_rate(self):
        """`cnt`=100 与 `historyWinCount`=679 不是同一个池子。

        拿 679 去减 100 会得到负场 0，但胜率 0.48 反推出来是 48 胜 52 负。
        """
        stats = summarize(_full_response)

        assert stats["胜场"] == 48
        assert stats["负场"] == 52
        assert stats["生涯胜场"] == 679
        assert stats["胜场"] + stats["负场"] == stats["总场次"]

    def test_weapon_pool_sorted_by_kills(self):
        stats = summarize(_full_response)

        weapon = stats["武器池"]
        assert weapon[0]["武器"] == "AK47"
        assert weapon[0]["击杀"] == 753
        assert weapon[0]["爆头"] == 444
        # 降序，不能乱
        assert [item["击杀"] for item in weapon] == sorted(
            (item["击杀"] for item in weapon), reverse=True
        )

    def test_map_pool_uses_api_names(self):
        """接口的 `mapName` 直接是中文，不要自己维护代号到中文的映射表。"""
        stats = summarize(_full_response)

        map_name = stats["地图池"]
        assert map_name[0]["地图"] == "远古遗迹"
        assert map_name[0]["场次"] == 24

    def test_map_falls_back_to_code(self):
        stats = summarize({"hotMaps": [{"map": "de_ancient", "totalMatch": 5}]})

        assert stats["地图池"][0]["地图"] == "de_ancient"

    def test_recent_ratings_take_ten(self):
        stats = summarize(
            {"historyRatings": [float(i) for i in range(30)], "historyDates": ["x"] * 100}
        )

        assert len(stats["近十场评分"]) == 10
        assert stats["近十场评分"][0] == 0.0

    def test_long_date_does_not_break_rating(self):
        """真实响应里日期 100 条而评分 30 条，两者不是一一对应。"""
        stats = summarize({"historyRatings": [1.5, 2.5], "historyDates": ["x"] * 100})

        assert stats["近十场评分"] == [1.5, 2.5]

    def test_multi_kill_count_verbatim(self):
        stats = summarize(_full_response)

        assert stats["多杀"] == {"三杀": 106, "四杀": 38, "五杀": 1}

    def test_win_rate_consistent(self):
        stats = summarize({"cnt": 200, "winRate": 0.75})

        assert stats["胜场"] == 150
        assert stats["负场"] == 50

    def test_full_data_gives_readable_text(self):
        text = summary_text(summarize(_full_response))

        assert "KD 1.24" in text
        assert "KAST 74.0%" in text
        assert "AK47 753杀（爆头 444）" in text
        assert "远古遗迹 24场" in text


class TestMissingFields:
    """取不到的维度必须从文本里消失，不许填 0。

    0 是合法数据（「爆头率 0%」确实可能），「没有这个字段」不是。混起来
    模型会把「没这个字段」读成「这项就是 0」，凭空编出结论。
    """

    def test_empty_response_only_nickname(self):
        stats = summarize({"nickName": "某人"})

        assert stats["总场次"] == 0
        assert stats["KD"] is None
        assert stats["爆头率"] is None

    def test_missing_field_words_absent(self):
        text = summary_text(summarize({"nickName": "某人"}))

        assert text == "某人 的战绩数据是空的。对方可能关闭了战绩展示，或最近没打过排位。"
        for should_not_contain in ("KD", "ADR", "爆头率", "0", "None"):
            assert should_not_contain not in text

    def test_absent_fields_not_shown(self):
        response = {"cnt": 10, "historyWinCount": 5, "kd": 1.5, "nickName": "某人"}
        text = summary_text(summarize(response))

        assert "KD 1.5" in text
        for should_not_contain in ("ADR", "KAST", "爆头率", "首杀率"):
            assert should_not_contain not in text

    def test_zero_values_shown(self):
        """爆头率真的是 0 时要显示 0，不能因为「取不到就隐藏」被误伤。"""
        response = {"cnt": 10, "historyWinCount": 0, "headShotRatio": 0, "nickName": "某人"}
        text = summary_text(summarize(response))

        assert "爆头率 0.0%" in text

    def test_rating_taken_despite_length_mismatch(self):
        """日期覆盖 100 场而评分只有 30 条，不能因为长度不等就整个丢掉。"""
        stats = summarize({"historyRatings": [1.0, 1.2], "historyDates": ["1", "2", "3"]})

        assert stats["近十场评分"] == [1.0, 1.2]

    def test_no_guess_wins_without_rate(self):
        """只有场次没有胜率，算不出胜负就都不显示，不能编一个 0 出来。"""
        stats = summarize({"cnt": 100})

        assert stats["胜场"] is None
        assert stats["负场"] is None

        text = summary_text(stats)
        assert "100 胜" not in text
        assert "0负" not in text

    def test_weapon_without_headshots_skipped(self):
        """显示「爆头 0」等于说这把枪一个爆头都没有，而事实是接口没给这个数。"""
        stats = summarize(
            {
                "cnt": 10,
                "winRate": 0.5,
                "hotWeapons": [{"weaponName": "AK47", "weaponKill": 100}],
            }
        )
        text = summary_text(stats)

        assert "AK47 100杀" in text
        assert "爆头" not in text

    def test_weapon_with_headshots_shown(self):
        stats = summarize(
            {
                "cnt": 10,
                "winRate": 0.5,
                "hotWeapons": [{"weaponName": "AK47", "weaponKill": 100, "weaponHeadShot": 40}],
            }
        )

        assert "AK47 100杀（爆头 40）" in summary_text(stats)

    def test_zero_headshots_shown(self):
        """一把枪真的一个爆头都没有是合法数据，不能被当成「缺字段」隐藏。"""
        stats = summarize(
            {
                "cnt": 10,
                "winRate": 0.5,
                "hotWeapons": [{"weaponName": "小刀", "weaponKill": 5, "weaponHeadShot": 0}],
            }
        )

        assert "小刀 5杀（爆头 0）" in summary_text(stats)

    def test_no_empty_weapon_line(self):
        stats = summarize({"cnt": 10, "winRate": 0.5, "hotWeapons": [{"weaponName": "AK47"}]})

        assert "常用武器：" not in summary_text(stats)


class TestTierName:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (0, ""),
            (0.0, ""),
            (None, ""),
            (14, "未定级"),
            (999, "未定级"),
            (1200, "白银"),
            (20620, "神话"),
            (50000, "神话"),
            (4500, "超凡大师"),
        ],
    )
    def test_score_to_tier(self, score, expected):
        assert tier_name(score) == expected

    def test_unranked_has_no_tier_name(self):
        """实测序列里混着 0、13、14，那是未定级与定级赛的标记值，不是段位分。"""
        assert tier_name(0) == ""
        assert tier_name(14) == "未定级"


class TestContrast:
    def _two_players(self, response_a, response_b):
        return summarize(response_a), summarize(response_b)

    def test_each_item_has_fixed_winner(self):
        # winRate 是 0 到 1 的小数，与真实接口一致
        a, b = self._two_players(
            {"cnt": 100, "historyWinCount": 60, "winRate": 0.6, "kd": 1.3},
            {"cnt": 100, "historyWinCount": 40, "winRate": 0.4, "kd": 0.9},
        )
        points = contrast_points(a, b)

        rate_item = next(line for line in points if line["项"] == "胜率")
        assert rate_item["优"] == "甲"
        assert rate_item["甲"] == "60.0%"
        assert rate_item["乙"] == "40.0%"

    def test_tie_reported_as_tie(self):
        a, b = self._two_players({"cnt": 50, "kd": 1.1}, {"cnt": 50, "kd": 1.1})
        points = contrast_points(a, b)

        assert all(line["优"] == "持平" for line in points)

    def test_no_compare_when_one_side_empty(self):
        """空统计逐项比下来会得到一串「持平」，看着像「两人一样好」，其实是没数据。"""
        a = summarize({"nickName": "甲"})
        b = summarize({"cnt": 100, "kd": 1.2})

        assert contrast_points(a, b) == []

    def test_each_contrast_line_names_winner(self):
        a, b = self._two_players(
            {"cnt": 100, "winRate": 0.6, "kd": 1.3, "adr": 100, "headShotRatio": 0.5},
            {"cnt": 100, "winRate": 0.4, "kd": 0.9, "adr": 60, "headShotRatio": 0.5},
        )
        text = contrast_text(contrast_points(a, b), "甲", "乙")

        assert "胜率：甲占优（甲 60.0% / 乙 40.0%）" in text
        assert "KD：甲占优（甲 1.3 / 乙 0.9）" in text
        # 爆头率两人都是 50%，要如实报持平
        assert "爆头率：持平（甲 50.0% / 乙 50.0%）" in text

    def test_advantage_count_only_states_facts(self):
        a, b = self._two_players(
            {"cnt": 100, "winRate": 0.6, "kd": 1.3, "adr": 100, "headShotRatio": 0.5},
            {"cnt": 100, "winRate": 0.4, "kd": 0.9, "adr": 60, "headShotRatio": 0.5},
        )
        points = contrast_points(a, b)
        result = advantage_count(points, "甲", "乙")

        wins_a = sum(1 for line in points if line["优"] == "甲")
        wins_b = sum(1 for line in points if line["优"] == "乙")
        assert result == f"甲 {wins_a} 项、乙 {wins_b} 项"
        # 持平的项不计入任何一方
        assert wins_a + wins_b < len(points)
        # 刻意不给「占优多的一方必须赢」这类说法，输赢留给模型判断
        assert "必须赢" not in result
