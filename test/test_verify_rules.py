"""字段核对规则的测试。

这是「真实响应与构造数据对不上时会不会报出来」的唯一防线。测试不打网络，
用构造出来的响应模拟接口改版的几种方式。

**每条「应该报出来」的用例都要反向验证过**：把 `核对规则.核对` 改成永远返回空
列表，这些用例会全红。
"""

from __future__ import annotations

from test_stats import _完整响应
from 核对规则 import 构造数据, 核对


def 一份响应() -> dict:
    return 构造数据()


class Test两处构造数据一致:
    """`核对规则.构造数据` 与 `test_stats._完整响应` 描述的是同一套量纲。

    两处不一致的话，其中一边就没有真实响应兜底了——所以要钉住。
    """

    def test_量纲字段一致(self):
        要比 = ("cnt", "winRate", "kast", "kd", "headShotRatio", "entryKillRatio")

        for 键 in 要比:
            assert 构造数据()[键] == _完整响应[键], f"{键} 在两处对不上"

    def test_构造数据本身能通过核对(self):
        assert 核对(构造数据()) == []

    def test_两份都被核对规则认可(self):
        """`_完整响应` 也要能过核对，否则它是构造错的。"""
        assert 核对(dict(_完整响应)) == []


class Test正常情况:
    def test_构造数据本身对得上(self):
        assert 核对(一份响应()) == []

    def test_具体值不同不算问题(self):
        """核对的是量纲不是数值。换个号查，值本来就不同。"""
        响应 = 一份响应()
        响应.update(
            {
                "cnt": 350,
                "winRate": 0.55,
                "kast": 68,
                "kd": 1.05,
                "nickName": "另一个人",
                "historyWinCount": 1900,
            }
        )

        assert 核对(响应) == []

    def test_日期比评分长不算问题(self):
        """真实响应就是日期 100 条、评分 30 条，不是 bug。"""
        响应 = 一份响应()
        响应["historyRatings"] = [1.0] * 30
        响应["historyDates"] = ["2026-10-01 20:00:00"] * 100

        assert 核对(响应) == []


class Test字段消失:
    def test_字段没了要报(self):
        响应 = 一份响应()
        del 响应["kast"]

        问题 = 核对(响应)
        assert len(问题) == 1
        assert "kast" in 问题[0]
        assert "没返回" in 问题[0]

    def test_必填字段空值也要报(self):
        响应 = 一份响应()
        响应["hotWeapons"] = []

        问题 = 核对(响应)
        assert any("hotWeapons" in 条 for 条 in 问题)

    def test_多个字段消失要全报(self):
        响应 = 一份响应()
        del 响应["kast"]
        del 响应["kd"]
        响应["nickName"] = ""

        assert len(核对(响应)) == 3


class Test量纲变了:
    def test_kast从小数变百分数(self):
        """这个是真的发生过：写代码时按字段名想当然，当成 0~1 的比率，
        结果输出 KAST 7400%。接口哪天反过来改，这里要能报出来。
        """
        响应 = 一份响应()
        响应["kast"] = 0.74

        问题 = 核对(响应)
        assert any("kast" in 条 and "量纲" in 条 for 条 in 问题)

    def test_比率从百分数变小数(self):
        响应 = 一份响应()
        响应["winRate"] = 48.0

        问题 = 核对(响应)
        assert any("winRate" in 条 for 条 in 问题)

    def test_量纲提示要指出去改哪(self):
        """报出问题就完了，人还得知道去改哪里。"""
        响应 = 一份响应()
        响应["kast"] = 0.74

        问题 = "\n".join(核对(响应))
        assert "test_stats.py" in 问题

    def test_字段类型变了要报(self):
        响应 = 一份响应()
        响应["kd"] = "1.24"

        问题 = 核对(响应)
        assert any("期望数字" in 条 for 条 in 问题)

    def test_差一个数量级之内不算变(self):
        """不同的人数据差得挺多，太严会一直报。"""
        响应 = 一份响应()
        响应["kd"] = 1.24 * 5

        assert 核对(响应) == []


class Test场次字段语义:
    def test_生涯胜场小于场次要报(self):
        """两个字段互换了是个真会发生的坑。

        拿 historyWinCount 去减 cnt 算负场会得到 0，而 cnt 乘胜率反推是对的。
        """
        响应 = 一份响应()
        响应["historyWinCount"] = 50

        问题 = 核对(响应)
        assert any("historyWinCount" in 条 and "cnt" in 条 for 条 in 问题)

    def test_生涯胜场远大于场次是正常的(self):
        """实测就是 679 对 100。"""
        响应 = 一份响应()
        响应["historyWinCount"] = 679

        assert 核对(响应) == []


class Test坏响应:
    def test_空响应要报一堆(self):
        问题 = 核对({})

        assert len(问题) >= 9

    def test_字段名换了要报(self):
        """`kd` 改成 `ratio` 之类的情况，所有字段都会报缺失。"""
        响应 = 一份响应()
        新 = {"ratio": 响应.pop("kd")}

        问题 = 核对(新 | 响应)
        assert any("kd" in 条 and "没返回" in 条 for 条 in 问题)
