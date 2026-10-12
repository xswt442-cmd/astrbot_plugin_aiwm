"""存储与 steamid 校验的测试。"""

from __future__ import annotations

import pytest

from aiwm.storage import 凭据仓库, 取有效steamid, 怎么找steamid, 提取steamid, 校验steamid


class Test提取steamid:
    @pytest.mark.parametrize(
        ("原文", "期望"),
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
    def test_能从常见形态里取到(self, 原文, 期望):
        assert 提取steamid(原文) == 期望

    def test_长数字不能被截出17位(self):
        """18 位数字里截一段 17 位，会得到一个看起来合法、实际是别人的号。"""
        assert 提取steamid("765611981599763367") == []

    def test_小数里的数字不算(self):
        assert 提取steamid("1.76561198159976336") == []

    def test_去重且保持顺序(self):
        文本 = "第二个 76561198159976336 第一个 76561198000000001 又 76561198159976336"

        assert 提取steamid(文本) == ["76561198159976336", "76561198000000001"]

    def test_没有就是空(self):
        assert 提取steamid("随便一句话") == []
        assert 提取steamid("") == []
        assert 提取steamid(None) == []

    def test_短数字不算(self):
        assert 提取steamid("76561198") == []


class Test取有效steamid:
    def test_纯数字直接过(self):
        assert 取有效steamid("76561198159976336") == "76561198159976336"

    def test_从网址里取(self):
        assert (
            取有效steamid("https://steamcommunity.com/profiles/76561198159976336")
            == "76561198159976336"
        )

    def test_从启动器参数里取(self):
        assert 取有效steamid("steam.exe -login 76561198159976336 -language schinese") == (
            "76561198159976336"
        )

    def test_带前后空白也能取(self):
        assert 取有效steamid("  76561198159976336  ") == "76561198159976336"

    def test_多个时不猜(self):
        """粘了一堆东西进来时，让用户说清要哪个，而不是随便挑一个。"""
        with pytest.raises(ValueError, match="好几个"):
            取有效steamid("76561198159976336 和 76561198000000001")

    def test_取不到时给指引(self):
        with pytest.raises(ValueError, match="没找到"):
            取有效steamid("我不知道我的号")

    def test_错误信息里带得上取号方法(self):
        """用户看到的是怎么找，不是只知道自己错了。"""
        with pytest.raises(ValueError) as 错:
            取有效steamid("abc")

        assert 怎么找steamid() in str(错.value)

    def test_超长内容截断显示(self):
        """贴了一整篇日志进来时，错误信息别把全文回显一遍。"""
        with pytest.raises(ValueError) as 错:
            取有效steamid("啊" * 200)

        assert "…" in str(错.value)
        assert len(str(错.value)) < 200


class Teststeamid校验:
    @pytest.mark.parametrize(
        "候选",
        [
            "76561198159976336",
            # 实测这个号就是 76561198 开头，第 8 位是 8——别对中间位做白名单
            "70000000000000000",
            "79999999999999999",
        ],
    )
    def test_合法值(self, 候选):
        assert 校验steamid(候选) is True

    @pytest.mark.parametrize(
        "候选",
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
    def test_非法值(self, 候选):
        assert 校验steamid(候选) is False

    def test_两边空白不碍事(self):
        assert 校验steamid("  76561198159976336  ") is True

    def test_非法值报错信息要指出格式(self):
        with pytest.raises(ValueError, match="17 位数字"):
            取有效steamid("abc")

    def test_合法值去空白返回(self):
        assert 取有效steamid("  76561198159976336 ") == "76561198159976336"


class Test凭据仓库:
    def test_写入后能读回(self, tmp_path):
        仓库 = 凭据仓库(tmp_path)
        仓库.写入("用户甲", "76561198159976336", 昵称="老王")

        记录 = 仓库.读取("用户甲")
        assert 记录["steamid"] == "76561198159976336"
        assert 记录["昵称"] == "老王"

    def test_文件名不是用户标识(self, tmp_path):
        """用户标识可能带 @ 和斜杠，不能直接当文件名。"""
        仓库 = 凭据仓库(tmp_path)
        仓库.写入("QQ号@某设备/1", "76561198159976336")

        文件们 = list(tmp_path.glob("*.json"))
        assert len(文件们) == 1
        assert "@" not in 文件们[0].name

    def test_非法steamid的文件不算绑定(self, tmp_path):
        """手工改坏的文件不该被当成有效绑定，否则查询时才报错。"""
        仓库 = 凭据仓库(tmp_path)
        仓库.写入("用户甲", "76561198159976336")
        仓库.路径("用户甲").write_text('{"steamid": "坏值"}', encoding="utf-8")

        assert 仓库.读取("用户甲") is None
        assert 仓库.全部() == []

    def test_按昵称找_精确优先(self, tmp_path):
        仓库 = 凭据仓库(tmp_path)
        仓库.写入("甲", "76561198159976336", 昵称="小明")
        仓库.写入("乙", "76561198159976337", 昵称="小明强")

        精确 = 仓库.按昵称找("小明")
        assert [记录["steamid"] for 记录 in 精确] == ["76561198159976336"]

    def test_按昵称找_不区分大小写(self, tmp_path):
        仓库 = 凭据仓库(tmp_path)
        仓库.写入("甲", "76561198159976336", 昵称="ZnNe")

        assert 仓库.按昵称找("znne") == 仓库.按昵称找("ZnNe")
        assert len(仓库.按昵称找("znne")) == 1

    def test_按昵称找_空名不给结果(self, tmp_path):
        仓库 = 凭据仓库(tmp_path)
        仓库.写入("甲", "76561198159976336", 昵称="小明")

        assert 仓库.按昵称找("") == []
        assert 仓库.按昵称找("   ") == []

    def test_删除后读不到(self, tmp_path):
        仓库 = 凭据仓库(tmp_path)
        仓库.写入("甲", "76561198159976336")

        assert 仓库.删除("甲") is not None
        assert 仓库.读取("甲") is None
        assert 仓库.删除("甲") is None

    def test_损坏的JSON不抛异常(self, tmp_path):
        仓库 = 凭据仓库(tmp_path)
        仓库.写入("甲", "76561198159976336")
        仓库.路径("甲").write_text("{不是 JSON", encoding="utf-8")

        assert 仓库.读取("甲") is None
        assert 仓库.全部() == []
