"""PK 目标解析的测试。"""

from __future__ import annotations

from dataclasses import dataclass

from aiwm.pk import FAKE_MENTION_IDS, find_opponent


@dataclass
class At组件:
    qq: str


class TestAt组件:
    def test_取到组件里的标识(self):
        assert find_opponent([At组件("2A8FDBA1")], "") == "2A8FDBA1"

    def test_排掉机器人自己(self):
        """群里 @机器人 同样会生成一个 At 组件，不排掉就把机器人当成对手。"""
        assert find_opponent([At组件("机器人")], "", me="甲", bot_id="机器人") is None

    def test_排掉发起者自己(self):
        assert find_opponent([At组件("甲")], "", me="甲") is None

    def test_排掉已知的伪标识(self):
        for 伪 in FAKE_MENTION_IDS:
            assert find_opponent([At组件(伪)], "") is None

    def test_非At组件被跳过(self):
        class 别的组件:
            qq = None

        assert find_opponent([别的组件()], "") is None

    def test_组件没有qq属性不崩(self):
        class 无属性:
            pass

        assert find_opponent([无属性()], "") is None

    def test_多个组件取第一个可用的(self):
        assert find_opponent([At组件("机器人"), At组件("小明")], "", bot_id="机器人") == "小明"


class Test正文提及:
    def test_尖括号写法(self):
        assert find_opponent([], "<@2A8FDBA1>") == "2A8FDBA1"

    def test_感叹号写法(self):
        assert find_opponent([], "<@!2A8FDBA1>") == "2A8FDBA1"

    def test_太短的噪声被滤掉(self):
        assert find_opponent([], "<@!1>") is None

    def test_排掉自己(self):
        assert find_opponent([], "<@!甲甲甲甲甲>", me="甲甲甲甲甲") is None

    def test_组件优先于正文(self):
        assert find_opponent([At组件("组件里的")], "<@!正文里的>") == "组件里的"


class Test找不到:
    def test_空消息返回None(self):
        assert find_opponent([], "") is None

    def test_普通文字返回None(self):
        """昵称是 main.py 那边另一条路径处理的，这里只管标识。"""
        assert find_opponent([], "/爱完美 PK 小明") is None

    def test_None消息列表不崩(self):
        assert find_opponent(None, "") is None
