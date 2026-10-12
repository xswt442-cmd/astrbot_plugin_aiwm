"""「开一局」的对局设定的测试。

这些数字要像真人打出来的：击杀不能均匀分布，胜的局个人表现不能太拉，
武器命中率要落在该枪的合理区间。测试钉的是这些约束。
"""

from __future__ import annotations

import random
import statistics

from aiwm.match import 侧写, 开局设定, 武器类别, 设定文本, 选地图, 选武器

_有统计 = {
    "总场次": 100,
    "KD": 1.24,
    "爆头率": 54.7,
    "段位分": 20620,
    "近十场评分": [2.19, 0.94, 0.66],
}


def _跑局数(统计=None, 局数=300):
    随机源 = random.Random(20261012)
    return [开局设定(随机源, 统计) for _ in range(局数)]


class Test比分与赛制:
    def test_比分到13局就结束(self):
        """CS2 竞技是打到 13 分，不是打满固定局数。"""
        for 设定 in _跑局数(局数=200):
            我的, 对手 = (int(v) for v in 设定["比分"].split(":"))
            assert 13 in (我的, 对手), f"{设定['比分']} 两边都没到 13"

    def test_胜的那边就是13(self):
        for 设定 in _跑局数(局数=200):
            我的, 对手 = (int(v) for v in 设定["比分"].split(":"))
            胜方 = 我的 if 设定["是否胜利"] else 对手
            assert 胜方 == 13

    def test_输的一方比分不超12(self):
        for 设定 in _跑局数(局数=200):
            我的, 对手 = (int(v) for v in 设定["比分"].split(":"))
            输方 = 对手 if 设定["是否胜利"] else 我的
            assert 0 <= 输方 <= 12

    def test_胜负大致各半(self):
        """长期看胜率该在 50% 附近，否则用户会觉得插件偏帮他不帮他。"""
        局 = _跑局数(局数=600)
        胜率 = sum(1 for 设定 in 局 if 设定["是否胜利"]) / len(局)

        assert 0.42 <= 胜率 <= 0.58, f"胜率 {胜率:.2%} 偏得厉害"


class Test个人表现:
    def test_击杀不低于0(self):
        for 设定 in _跑局数(局数=200):
            assert 设定["击杀"] >= 0

    def test_死亡至少1(self):
        """死了零次的一局在 CS2 里不存在，除非整局没交火。"""
        for 设定 in _跑局数(局数=200):
            assert 设定["死亡"] >= 1

    def test_爆头数不超过击杀(self):
        for 设定 in _跑局数(局数=200):
            assert 设定["爆头数"] <= 设定["击杀"]

    def test_命中率在该武器的合理区间(self):
        """AWP 的命中率天然高于步枪，用同一套区间会立刻露馅。"""
        for 设定 in _跑局数(局数=200):
            下, 上 = 武器类别[设定["武器"]]
            assert 下 * 100 <= 设定["命中率"] <= 上 * 100, (
                f"{设定['武器']} 的命中率 {设定['命中率']} 越界（应在 {下 * 100}~{上 * 100}）"
            )

    def test_评级不超过2(self):
        for 设定 in _跑局数(局数=200):
            assert 0 <= 设定["评级"] <= 2

    def test_评级贴近参照的历史评分(self):
        """一局里评级不会比平时水平差太多。"""
        局 = _跑局数(_有统计, 局数=300)
        均值 = statistics.mean(设定["评级"] for 设定 in 局)

        assert 0.7 <= 均值 <= 2.0, f"评级均值 {均值:.2f} 偏离参照的 2.19 太多"

    def test_无历史数据时也能生成(self):
        for 设定 in _跑局数(None, 局数=100):
            assert 设定["击杀"] >= 0
            assert 设定["评级"] >= 0


class Test水平适配:
    def test_水平按段位分给描述(self):
        随机源 = random.Random(1)

        assert "白银" in 侧写(随机源, 3000)
        assert "神话" in 侧写(随机源, 20620)
        assert "超凡" in 侧写(随机源, 26000)

    def test_段位更高时击杀更多(self):
        """同样 300 局，高手该打得比新手多。"""
        高手 = _跑局数({**_有统计, "KD": 1.8}, 局数=300)
        新手 = _跑局数({**_有统计, "KD": 0.6}, 局数=300)

        assert statistics.mean(s["击杀"] for s in 高手) > statistics.mean(s["击杀"] for s in 新手)

    def test_水平描述写进设定(self):
        局 = _跑局数(_有统计, 局数=20)

        assert all(设定["水平"] != "无历史数据，取中等水平" for 设定 in 局)


class Test选图与选枪:
    def test_地图来自真实池子(self):
        随机源 = random.Random(7)
        地图集 = {选地图(随机源) for _ in range(200)}

        assert 地图集 <= {
            "远古遗迹",
            "炼狱小镇",
            "荒漠迷城",
            "核子危机",
            "死城之谜",
            "列车停放站",
            "古堡激战",
        }

    def test_每把枪都有命中率区间(self):
        """`_加权取` 与 `武器类别` 是两套表，漏配就会在生成时 KeyError。"""
        随机源 = random.Random(7)
        for _ in range(300):
            assert 选武器(随机源) in 武器类别

    def test_步枪比手枪常见(self):
        随机源 = random.Random(7)
        枪 = [选武器(随机源) for _ in range(600)]
        步枪 = sum(1 for 名 in 枪 if 名 in ("AK47", "M4A4", "M4A1消音型"))

        assert 步枪 > len(枪) * 0.5, f"步枪只占 {步枪 / len(枪):.0%}，不像真人"


class Test输出文本:
    def test_每项都出现在文本里(self):
        """结构化输出靠这段文字，漏一项模型就不知道该说什么。"""
        设定 = _跑局数(_有统计, 局数=1)[0]
        文本 = 设定文本(设定)

        for 键 in ("地图", "武器", "比分", "击杀", "命中率", "评级", "水平"):
            assert 键 in 文本, f"{键} 没出现在设定文本里"

    def test_比分写明胜负(self):
        设定 = _跑局数(_有统计, 局数=1)[0]
        文本 = 设定文本(设定)

        assert "胜" in 文本 or "负" in 文本

    def test_真实统计不出现在设定文本里(self):
        """设定文本只讲这一局，不该把玩家历史数据混进来——那会让模型混淆推演与事实。"""
        设定 = _跑局数(_有统计, 局数=1)[0]
        文本 = 设定文本(设定)

        assert "20620" not in 文本
        assert "100" not in 文本
