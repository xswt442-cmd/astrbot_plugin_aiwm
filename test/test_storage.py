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
        assert extract_steamids(原文) == 期望

    def test_长数字不能被截出17位(self):
        """18 位数字里截一段 17 位，会得到一个看起来合法、实际是别人的号。"""
        assert extract_steamids("765611981599763367") == []

    def test_小数里的数字不算(self):
        assert extract_steamids("1.76561198159976336") == []

    def test_去重且保持顺序(self):
        文本 = "第二个 76561198159976336 第一个 76561198000000001 又 76561198159976336"

        assert extract_steamids(文本) == ["76561198159976336", "76561198000000001"]

    def test_没有就是空(self):
        assert extract_steamids("随便一句话") == []
        assert extract_steamids("") == []
        assert extract_steamids(None) == []

    def test_短数字不算(self):
        assert extract_steamids("76561198") == []


class Test取有效steamid:
    def test_纯数字直接过(self):
        assert resolve_steamid("76561198159976336") == "76561198159976336"

    def test_从网址里取(self):
        assert (
            resolve_steamid("https://steamcommunity.com/profiles/76561198159976336")
            == "76561198159976336"
        )

    def test_从启动器参数里取(self):
        assert resolve_steamid("steam.exe -login 76561198159976336 -language schinese") == (
            "76561198159976336"
        )

    def test_带前后空白也能取(self):
        assert resolve_steamid("  76561198159976336  ") == "76561198159976336"

    def test_多个时不猜(self):
        """粘了一堆东西进来时，让用户说清要哪个，而不是随便挑一个。"""
        with pytest.raises(ValueError, match="好几个"):
            resolve_steamid("76561198159976336 和 76561198000000001")

    def test_取不到时给指引(self):
        with pytest.raises(ValueError, match="没找到"):
            resolve_steamid("我不知道我的号")

    def test_错误信息里带得上取号方法(self):
        """用户看到的是怎么找，不是只知道自己错了。"""
        with pytest.raises(ValueError) as 错:
            resolve_steamid("abc")

        assert how_to_find_steamid() in str(错.value)

    def test_超长内容截断显示(self):
        """贴了一整篇日志进来时，错误信息别把全文回显一遍。"""
        with pytest.raises(ValueError) as 错:
            resolve_steamid("啊" * 200)

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
        assert is_valid_steamid(候选) is True

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
        assert is_valid_steamid(候选) is False

    def test_两边空白不碍事(self):
        assert is_valid_steamid("  76561198159976336  ") is True

    def test_非法值报错信息要指出格式(self):
        with pytest.raises(ValueError, match="17 位数字"):
            resolve_steamid("abc")

    def test_合法值去空白返回(self):
        assert resolve_steamid("  76561198159976336 ") == "76561198159976336"


class Test凭据仓库:
    def test_写入后能读回(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("用户甲", "76561198159976336", nickname="老王")

        记录 = store.read("用户甲")
        assert 记录["steamid"] == "76561198159976336"
        assert 记录["昵称"] == "老王"

    def test_文件名不是用户标识(self, tmp_path):
        """用户标识可能带 @ 和斜杠，不能直接当文件名。"""
        store = CredentialStore(tmp_path)
        store.write("QQ号@某设备/1", "76561198159976336")

        文件们 = list(tmp_path.glob("*.json"))
        assert len(文件们) == 1
        assert "@" not in 文件们[0].name

    def test_非法steamid的文件不算绑定(self, tmp_path):
        """手工改坏的文件不该被当成有效绑定，否则查询时才报错。"""
        store = CredentialStore(tmp_path)
        store.write("用户甲", "76561198159976336")
        store.path_for("用户甲").write_text('{"steamid": "坏值"}', encoding="utf-8")

        assert store.read("用户甲") is None
        assert store.iter_all() == []

    def test_按昵称找_精确优先(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336", nickname="小明")
        store.write("乙", "76561198159976337", nickname="小明强")

        精确 = store.find_by_nickname("小明")
        assert [记录["steamid"] for 记录 in 精确] == ["76561198159976336"]

    def test_按昵称找_不区分大小写(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336", nickname="ZnNe")

        assert store.find_by_nickname("znne") == store.find_by_nickname("ZnNe")
        assert len(store.find_by_nickname("znne")) == 1

    def test_按昵称找_空名不给结果(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336", nickname="小明")

        assert store.find_by_nickname("") == []
        assert store.find_by_nickname("   ") == []

    def test_删除后读不到(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336")

        assert store.delete("甲") is not None
        assert store.read("甲") is None
        assert store.delete("甲") is None

    def test_损坏的JSON不抛异常(self, tmp_path):
        store = CredentialStore(tmp_path)
        store.write("甲", "76561198159976336")
        store.path_for("甲").write_text("{不是 JSON", encoding="utf-8")

        assert store.read("甲") is None
        assert store.iter_all() == []


class Test净化昵称:
    """昵称会拼进 PK 提示词：换行能伪造指令，零宽字符能让两个名字看着一样。"""

    def test_换行与制表符被去掉(self):
        assert clean_nickname("老\n王\t") == "老王"

    def test_零宽字符被去掉(self):
        assert clean_nickname("老\u200b王") == "老王"

    def test_首尾空白被压掉(self):
        assert clean_nickname("  老王  ") == "老王"

    def test_空值不抛(self):
        assert clean_nickname("") == ""
        assert clean_nickname(None) == ""
