"""PK 目标解析的测试。"""

from __future__ import annotations

from dataclasses import dataclass

from aiwm.pk import 不是标识的提及, 找对手


@dataclass
class At组件:
    qq: str


class TestAt组件:
    def test_取到组件里的标识(self):
        assert 找对手([At组件("2A8FDBA1")], "") == "2A8FDBA1"

    def test_排掉机器人自己(self):
        """群里 @机器人 同样会生成一个 At 组件，不排掉就把机器人当成对手。"""
        assert 找对手([At组件("机器人")], "", 自己="甲", 机器人="机器人") is None

    def test_排掉发起者自己(self):
        assert 找对手([At组件("甲")], "", 自己="甲") is None

    def test_排掉已知的伪标识(self):
        for 伪 in 不是标识的提及:
            assert 找对手([At组件(伪)], "") is None

    def test_非At组件被跳过(self):
        class 别的组件:
            qq = None

        assert 找对手([别的组件()], "") is None

    def test_组件没有qq属性不崩(self):
        class 无属性:
            pass

        assert 找对手([无属性()], "") is None

    def test_多个组件取第一个可用的(self):
        assert 找对手([At组件("机器人"), At组件("小明")], "", 机器人="机器人") == "小明"


class Test正文提及:
    def test_尖括号写法(self):
        assert 找对手([], "<@2A8FDBA1>") == "2A8FDBA1"

    def test_感叹号写法(self):
        assert 找对手([], "<@!2A8FDBA1>") == "2A8FDBA1"

    def test_太短的噪声被滤掉(self):
        assert 找对手([], "<@!1>") is None

    def test_排掉自己(self):
        assert 找对手([], "<@!甲甲甲甲甲>", 自己="甲甲甲甲甲") is None

    def test_组件优先于正文(self):
        assert 找对手([At组件("组件里的")], "<@!正文里的>") == "组件里的"


class Test找不到:
    def test_空消息返回None(self):
        assert 找对手([], "") is None

    def test_普通文字返回None(self):
        """昵称是 main.py 那边另一条路径处理的，这里只管标识。"""
        assert 找对手([], "/爱完美 PK 小明") is None

    def test_None消息列表不崩(self):
        assert 找对手(None, "") is None
