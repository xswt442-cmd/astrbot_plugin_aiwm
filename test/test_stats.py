"""战绩统计的测试。

覆盖三件事：字段与量纲映射正确、缺字段时那一项从文本里消失、对比由代码算死。

测试用构造的数据而不是录制快照，所以**字段名与量纲必须与接口一致**，否则
这些断言会保护着一份已经不存在的协议。改动协议相关代码时，先用
`test/verify_wmpvp.py` 打一次真实接口，把真实返回里的字段名与量纲核对一遍
再改这里的断言。
"""

from __future__ import annotations

import pytest

from aiwm.stats import 占优项数, 对比文本, 对比要点, 段位名, 汇总文本, 统计战绩

# 字段名与量纲照真实响应写：比率给的是 0~1 的小数，只有 kast 已经是百分数；
# cnt 与 historyWinCount 不是同一个池子；historyRatings 与 historyDates 长度
# 不一致。这几条都是量过真实响应才定下来的。
_完整响应 = {
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


class Test字段映射:
    def test_解析核心指标(self):
        统计 = 统计战绩(_完整响应)

        assert 统计["总场次"] == 100
        assert 统计["段位分"] == 20620
        assert 统计["KD"] == 1.24
        assert 统计["ADR"] == 95.64
        assert 统计["昵称"] == "示例昵称"

    def test_比率折成百分数(self):
        统计 = 统计战绩(_完整响应)

        # 接口给的是 0.48 / 0.547 这样的比率
        assert 统计["胜率"] == 48.0
        assert 统计["爆头率"] == 54.7
        assert 统计["首杀率"] == 17.0

    def test_kast本来就是百分数(self):
        """`kast` 给的是 74 而不是 0.74，套上换算会变成 7400%。"""
        统计 = 统计战绩(_完整响应)

        assert 统计["KAST"] == 74.0

    def test_负场由胜率反算而不是拿生涯胜场减(self):
        """`cnt`=100 与 `historyWinCount`=679 不是同一个池子。

        拿 679 去减 100 会得到负场 0，但胜率 0.48 反推出来是 48 胜 52 负。
        """
        统计 = 统计战绩(_完整响应)

        assert 统计["胜场"] == 48
        assert 统计["负场"] == 52
        assert 统计["生涯胜场"] == 679
        assert 统计["胜场"] + 统计["负场"] == 统计["总场次"]

    def test_武器池按击杀排序(self):
        统计 = 统计战绩(_完整响应)

        武器 = 统计["武器池"]
        assert 武器[0]["武器"] == "AK47"
        assert 武器[0]["击杀"] == 753
        assert 武器[0]["爆头"] == 444
        # 降序，不能乱
        assert [项["击杀"] for 项 in 武器] == sorted((项["击杀"] for 项 in 武器), reverse=True)

    def test_地图池用接口自带的中文名(self):
        """接口的 `mapName` 直接是中文，不要自己维护代号到中文的映射表。"""
        统计 = 统计战绩(_完整响应)

        地图 = 统计["地图池"]
        assert 地图[0]["地图"] == "远古遗迹"
        assert 地图[0]["场次"] == 24

    def test_地图缺中文名时用代号(self):
        统计 = 统计战绩({"hotMaps": [{"map": "de_ancient", "totalMatch": 5}]})

        assert 统计["地图池"][0]["地图"] == "de_ancient"

    def test_近期评分取十条(self):
        统计 = 统计战绩(
            {"historyRatings": [float(i) for i in range(30)], "historyDates": ["x"] * 100}
        )

        assert len(统计["近十场评分"]) == 10
        assert 统计["近十场评分"][0] == 0.0

    def test_日期比评分长不影响取评分(self):
        """真实响应里日期 100 条而评分 30 条，两者不是一一对应。"""
        统计 = 统计战绩({"historyRatings": [1.5, 2.5], "historyDates": ["x"] * 100})

        assert 统计["近十场评分"] == [1.5, 2.5]

    def test_多杀次数照抄(self):
        统计 = 统计战绩(_完整响应)

        assert 统计["多杀"] == {"三杀": 106, "四杀": 38, "五杀": 1}

    def test_胜率与胜场负场自洽(self):
        统计 = 统计战绩({"cnt": 200, "winRate": 0.75})

        assert 统计["胜场"] == 150
        assert 统计["负场"] == 50

    def test_完整数据能折出可读文本(self):
        文本 = 汇总文本(统计战绩(_完整响应))

        assert "KD 1.24" in 文本
        assert "KAST 74.0%" in 文本
        assert "AK47 753杀（爆头 444）" in 文本
        assert "远古遗迹 24场" in 文本


class Test缺字段:
    """取不到的维度必须从文本里消失，不许填 0。

    0 是合法数据（「爆头率 0%」确实可能），「没有这个字段」不是。混起来
    模型会把「没这个字段」读成「这项就是 0」，凭空编出结论。
    """

    def test_空响应只有昵称(self):
        统计 = 统计战绩({"nickName": "某人"})

        assert 统计["总场次"] == 0
        assert 统计["KD"] is None
        assert 统计["爆头率"] is None

    def test_缺字段的字样不出现在文本里(self):
        文本 = 汇总文本(统计战绩({"nickName": "某人"}))

        assert 文本 == "某人 的战绩数据是空的。对方可能关闭了战绩展示，或还没打过天梯。"
        for 不该有 in ("KD", "ADR", "爆头率", "0", "None"):
            assert 不该有 not in 文本

    def test_只有部分字段时其余不出现(self):
        响应 = {"cnt": 10, "historyWinCount": 5, "kd": 1.5, "nickName": "某人"}
        文本 = 汇总文本(统计战绩(响应))

        assert "KD 1.5" in 文本
        for 不该有 in ("ADR", "KAST", "爆头率", "首杀率"):
            assert 不该有 not in 文本

    def test_零值要照常显示(self):
        """爆头率真的是 0 时要显示 0，不能因为「取不到就隐藏」被误伤。"""
        响应 = {"cnt": 10, "historyWinCount": 0, "headShotRatio": 0, "nickName": "某人"}
        文本 = 汇总文本(统计战绩(响应))

        assert "爆头率 0.0%" in 文本

    def test_评分与日期长度对不上时照样取评分(self):
        """日期覆盖 100 场而评分只有 30 条，不能因为长度不等就整个丢掉。"""
        统计 = 统计战绩({"historyRatings": [1.0, 1.2], "historyDates": ["1", "2", "3"]})

        assert 统计["近十场评分"] == [1.0, 1.2]

    def test_没有胜率时不猜胜场负场(self):
        """只有场次没有胜率，算不出胜负就都不显示，不能编一个 0 出来。"""
        统计 = 统计战绩({"cnt": 100})

        assert 统计["胜场"] is None
        assert 统计["负场"] is None

        文本 = 汇总文本(统计)
        assert "100 胜" not in 文本
        assert "0负" not in 文本

    def test_武器缺爆头数时整段省掉(self):
        """显示「爆头 0」等于说这把枪一个爆头都没有，而事实是接口没给这个数。"""
        统计 = 统计战绩(
            {
                "cnt": 10,
                "winRate": 0.5,
                "hotWeapons": [{"weaponName": "AK47", "weaponKill": 100}],
            }
        )
        文本 = 汇总文本(统计)

        assert "AK47 100杀" in 文本
        assert "爆头" not in 文本

    def test_武器有爆头数时照常显示(self):
        统计 = 统计战绩(
            {
                "cnt": 10,
                "winRate": 0.5,
                "hotWeapons": [{"weaponName": "AK47", "weaponKill": 100, "weaponHeadShot": 40}],
            }
        )

        assert "AK47 100杀（爆头 40）" in 汇总文本(统计)

    def test_爆头数真的是零时要显示零(self):
        """一把枪真的一个爆头都没有是合法数据，不能被当成「缺字段」隐藏。"""
        统计 = 统计战绩(
            {
                "cnt": 10,
                "winRate": 0.5,
                "hotWeapons": [{"weaponName": "小刀", "weaponKill": 5, "weaponHeadShot": 0}],
            }
        )

        assert "小刀 5杀（爆头 0）" in 汇总文本(统计)

    def test_武器全都缺击杀时不出空标签行(self):
        统计 = 统计战绩({"cnt": 10, "winRate": 0.5, "hotWeapons": [{"weaponName": "AK47"}]})

        assert "常用武器：" not in 汇总文本(统计)


class Test段位名:
    @pytest.mark.parametrize(
        ("分数", "期望"),
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
    def test_分数折段位(self, 分数, 期望):
        assert 段位名(分数) == 期望

    def test_未定级不编段位名(self):
        """实测序列里混着 0、13、14，那是未定级与定级赛的标记值，不是段位分。"""
        assert 段位名(0) == ""
        assert 段位名(14) == "未定级"


class Test对比:
    def _两人(self, 甲响应, 乙响应):
        return 统计战绩(甲响应), 统计战绩(乙响应)

    def test_逐项算死占优方(self):
        # winRate 是 0 到 1 的小数，与真实接口一致
        甲, 乙 = self._两人(
            {"cnt": 100, "historyWinCount": 60, "winRate": 0.6, "kd": 1.3},
            {"cnt": 100, "historyWinCount": 40, "winRate": 0.4, "kd": 0.9},
        )
        要点 = 对比要点(甲, 乙)

        胜率项 = next(条 for 条 in 要点 if 条["项"] == "胜率")
        assert 胜率项["优"] == "甲"
        assert 胜率项["甲"] == "60.0%"
        assert 胜率项["乙"] == "40.0%"

    def test_持平如实报持平(self):
        甲, 乙 = self._两人({"cnt": 50, "kd": 1.1}, {"cnt": 50, "kd": 1.1})
        要点 = 对比要点(甲, 乙)

        assert all(条["优"] == "持平" for 条 in 要点)

    def test_一方没数据不逐项比(self):
        """空统计逐项比下来会得到一串「持平」，看着像「两人一样好」，其实是没数据。"""
        甲 = 统计战绩({"nickName": "甲"})
        乙 = 统计战绩({"cnt": 100, "kd": 1.2})

        assert 对比要点(甲, 乙) == []

    def test_对比文本每行都说明谁占优(self):
        甲, 乙 = self._两人(
            {"cnt": 100, "winRate": 0.6, "kd": 1.3, "adr": 100, "headShotRatio": 0.5},
            {"cnt": 100, "winRate": 0.4, "kd": 0.9, "adr": 60, "headShotRatio": 0.5},
        )
        文本 = 对比文本(对比要点(甲, 乙), "甲", "乙")

        assert "胜率：甲占优（甲 60.0% / 乙 40.0%）" in 文本
        assert "KD：甲占优（甲 1.3 / 乙 0.9）" in 文本
        # 爆头率两人都是 50%，要如实报持平
        assert "爆头率：持平（甲 50.0% / 乙 50.0%）" in 文本

    def test_占优项数只报事实不判定胜负(self):
        甲, 乙 = self._两人(
            {"cnt": 100, "winRate": 0.6, "kd": 1.3, "adr": 100, "headShotRatio": 0.5},
            {"cnt": 100, "winRate": 0.4, "kd": 0.9, "adr": 60, "headShotRatio": 0.5},
        )
        要点 = 对比要点(甲, 乙)
        结果 = 占优项数(要点, "甲", "乙")

        甲胜 = sum(1 for 条 in 要点 if 条["优"] == "甲")
        乙胜 = sum(1 for 条 in 要点 if 条["优"] == "乙")
        assert 结果 == f"甲 {甲胜} 项、乙 {乙胜} 项"
        # 持平的项不计入任何一方
        assert 甲胜 + 乙胜 < len(要点)
        # 刻意不给「占优多的一方必须赢」这类说法，输赢留给模型判断
        assert "必须赢" not in 结果
