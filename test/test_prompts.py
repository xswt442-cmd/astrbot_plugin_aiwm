"""提示词的测试。

提示词里那些硬性的输出格式与反端水约定是要被钉住的——模型很容易在
这些地方自由发挥，而一旦格式飘了，输出就没法直接展示给用户。
"""

from __future__ import annotations

from aiwm.prompts import PK提示, 称号前缀, 端水词, 锐评提示


class Test锐评提示:
    def test_写死称号前缀(self):
        """模型很爱自由发挥成「称号：xxx」，所以前后都要写一遍这个前缀。"""
        提示 = 锐评提示("数据")

        assert 称号前缀 in 提示
        assert f"第一行必须以「{称号前缀}」开头" in 提示

    def test_端水词列成禁令(self):
        """对模型说「不要端水」效果一般，列具体词表才有用。"""
        提示 = 锐评提示("数据")

        for 词 in 端水词:
            assert 词 in 提示

    def test_数据原样带进提示(self):
        assert "数据：\n统计场次 100（48胜52负）" in 锐评提示("统计场次 100（48胜52负）")

    def test_要求出现具体数字(self):
        提示 = 锐评提示("数据")

        assert "至少出现 3 个具体数字" in 提示

    def test_点名CS2专属指标(self):
        """RWS 与 ADR 是 CS2 才有的指标，提示里要引导模型去看它们。"""
        提示 = 锐评提示("数据")

        assert "ADR" in 提示
        assert "KAST" in 提示
        assert "首杀率" in 提示

    def test_要求指出具体短板(self):
        提示 = 锐评提示("数据")

        assert "必须指向数据里的具体一项" in 提示

    def test_给了字数范围(self):
        提示 = 锐评提示("数据")

        assert "180 到 260 字" in 提示


class TestPK提示:
    def _提示(self) -> str:
        return PK提示(
            "老王",
            "小明",
            "KD：老王占优（老王 1.3 / 小明 0.9）",
            "老王 1 项、小明 0 项",
            "老王数据",
            "小明数据",
        )

    def test_明确不许推翻已算好的对比(self):
        """让模型自己比，它最省事的答案就是「各有千秋」。"""
        提示 = self._提示()

        assert "不要推翻对比结论" in 提示
        assert "已经替你算好了" in 提示

    def test_要求写出双方数字(self):
        提示 = self._提示()

        assert "必须写出项名与双方数字" in 提示

    def test_占优项数只作参考不判定胜负(self):
        提示 = self._提示()

        assert "占优项更多的一方不一定分数更高" in 提示
        assert "仅供参考" in 提示

    def test_双方数据都在提示里(self):
        提示 = self._提示()

        assert "【老王】原始数据\n老王数据" in 提示
        assert "【小明】原始数据\n小明数据" in 提示

    def test_端水词列成禁令(self):
        提示 = self._提示()

        for 词 in 端水词:
            assert 词 in 提示

    def test_互损要有字数下限(self):
        提示 = self._提示()

        assert "至少 90 字" in 提示
