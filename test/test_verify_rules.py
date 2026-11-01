"""字段核对规则的测试。

这是「真实响应与构造数据对不上时会不会报出来」的唯一防线。测试不打网络，
用构造出来的响应模拟接口改版的几种方式。

**每条「应该报出来」的用例都要反向验证过**：把 `核对规则.核对` 改成永远返回空
列表，这些用例会全红。
"""

from __future__ import annotations

from test_stats import _full_response
from 核对规则 import build_data, check


def make_response() -> dict:
    return build_data()


class TestBothBuildersAgree:
    """`核对规则.构造数据` 与 `test_stats._完整响应` 描述的是同一套量纲。

    两处不一致的话，其中一边就没有真实响应兜底了——所以要钉住。
    """

    def test_dimension_fields_consistent(self):
        to_compare = ("cnt", "winRate", "kast", "kd", "headShotRatio", "entryKillRatio")

        for key in to_compare:
            assert build_data()[key] == _full_response[key], f"{key} 在两处对不上"

    def test_builder_data_passes_check(self):
        assert check(build_data()) == []

    def test_both_accepted_by_rules(self):
        """`_完整响应` 也要能过核对，否则它是构造错的。"""
        assert check(dict(_full_response)) == []


class TestNormalCase:
    def test_builder_data_consistent(self):
        assert check(make_response()) == []

    def test_different_values_not_a_problem(self):
        """核对的是量纲不是数值。换个号查，值本来就不同。"""
        response = make_response()
        response.update(
            {
                "cnt": 350,
                "winRate": 0.55,
                "kast": 68,
                "kd": 1.05,
                "nickName": "另一个人",
                "historyWinCount": 1900,
            }
        )

        assert check(response) == []

    def test_long_date_not_a_problem(self):
        """真实响应就是日期 100 条、评分 30 条，不是 bug。"""
        response = make_response()
        response["historyRatings"] = [1.0] * 30
        response["historyDates"] = ["2026-10-01 20:00:00"] * 100

        assert check(response) == []


class TestFieldMissing:
    def test_reports_missing_field(self):
        response = make_response()
        del response["kast"]

        problems = check(response)
        assert len(problems) == 1
        assert "kast" in problems[0]
        assert "没返回" in problems[0]

    def test_reports_empty_required_field(self):
        response = make_response()
        response["hotWeapons"] = []

        problems = check(response)
        assert any("hotWeapons" in line for line in problems)

    def test_reports_all_missing_fields(self):
        response = make_response()
        del response["kast"]
        del response["kd"]
        response["nickName"] = ""

        assert len(check(response)) == 3


class TestDimensionChanged:
    def test_kast_ratio_to_percent(self):
        """这个是真的发生过：写代码时按字段名想当然，当成 0~1 的比率，
        结果输出 KAST 7400%。接口哪天反过来改，这里要能报出来。
        """
        response = make_response()
        response["kast"] = 0.74

        problems = check(response)
        assert any("kast" in line and "量纲" in line for line in problems)

    def test_ratio_from_percent_to_decimal(self):
        response = make_response()
        response["winRate"] = 48.0

        problems = check(response)
        assert any("winRate" in line for line in problems)

    def test_dimension_hint_names_field(self):
        """报出问题就完了，人还得知道去改哪里。"""
        response = make_response()
        response["kast"] = 0.74

        problems = "\n".join(check(response))
        assert "test_stats.py" in problems

    def test_reports_type_change(self):
        response = make_response()
        response["kd"] = "1.24"

        problems = check(response)
        assert any("期望数字" in line for line in problems)

    def test_same_order_not_a_change(self):
        """不同的人数据差得挺多，太严会一直报。"""
        response = make_response()
        response["kd"] = 1.24 * 5

        assert check(response) == []


class TestMatchFieldSemantics:
    def test_reports_career_wins_below_matches(self):
        """两个字段互换了是个真会发生的坑。

        拿 historyWinCount 去减 cnt 算负场会得到 0，而 cnt 乘胜率反推是对的。
        """
        response = make_response()
        response["historyWinCount"] = 50

        problems = check(response)
        assert any("historyWinCount" in line and "cnt" in line for line in problems)

    def test_career_wins_above_matches_ok(self):
        """实测就是 679 对 100。"""
        response = make_response()
        response["historyWinCount"] = 679

        assert check(response) == []


class TestBadResponse:
    def test_empty_response_reports_many(self):
        problems = check({})

        assert len(problems) >= 9

    def test_reports_renamed_field(self):
        """`kd` 改成 `ratio` 之类的情况，所有字段都会报缺失。"""
        response = make_response()
        new = {"ratio": response.pop("kd")}

        problems = check(new | response)
        assert any("kd" in line and "没返回" in line for line in problems)
