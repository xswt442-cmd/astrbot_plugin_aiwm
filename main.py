"""爱完美：完美世界竞技平台 CS2 战绩查询。

用户绑定自己的 steamid64 后，指令与模型都能读到他自己的战绩数据。
完美接口查战绩不需要登录态，所以绑定只是记一个 id，没有扫码登录。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import command_group, llm_tool
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr

# 全部在模块顶层导入。插件加载时就把整个包摸清：少文件、依赖缺失都在启动
# 阶段报错，而不是等用户发了指令才在懒加载里抛模块不存在。
from .aiwm.battles import 读战绩数据
from .aiwm.pk import 找对手
from .aiwm.prompts import PK提示, 锐评提示
from .aiwm.stats import 占优项数, 对比文本, 对比要点
from .aiwm.storage import 凭据仓库, 取有效steamid
from .aiwm.transport import 业务错误, 完美传输

# PK 名字要念在提示里，太长挤版面。
_昵称上限 = 16

_帮助文本 = """爱完美 · 完美竞技平台 CS2 战绩

/爱完美 绑定 <steamid64>
  记下你的 SteamID64，之后的查询都看它。

  不用自己从一串东西里挑数字——下面这些粘给我都行，我从里面取：
  · Steam 个人资料页的网址（…/profiles/76561198159976336）
  · 启动器参数（steam.exe -login 76561198159976336）
  · 那串数字本身
  查战绩不需要登录平台，不用扫码。

/爱完美 战绩
  近期战绩：段位与综合分、胜率、KD、Rating、ADR、KAST、RWS、
  爆头率与首杀率、常用地图、常用武器与击杀分布、多杀次数、最近十场评分。

/爱完美 锐评
  让模型基于上面的数据写一段锐评。会先给一句称号，再分别说打得好、
  问题和一条具体建议。

/爱完美 PK <名字>
  和另一个人比近期战绩。名字是绑定时记下的平台显示名，可以用 /爱完美 昵称 改。
  双方都得先绑定。模型会给两人各打一个趣味分并点评胜负手。

/爱完美 昵称 <名字>
  改你在 PK 时被叫的名字。不设的话取绑定时的平台显示名。

/爱完美 解绑
  解除绑定并立即删除本地记录。

/爱完美 状态
  看自己的标识、绑定情况。排查用。

/爱完美 帮助
  就是这条。

直接问模型「我的 CS2 战绩怎么样」也会走同一套数据。"""


class Main(Star):
    @command_group("爱完美")
    def 爱完美(self):
        """完美竞技平台 CS2 战绩查询。指令都在这个组下，不占用通用名字。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        # config 目前没有配置项，但 AstrBot 按签名注入配置，去掉这个参数
        # 插件就加载不起来。等真有配置项时再用它。
        super().__init__(context)
        self.config = config
        self._凭据 = 凭据仓库(self._数据目录())

    def _数据目录(self) -> Path:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        return Path(get_astrbot_data_path()) / "plugin_data" / "aiwm"

    @爱完美.command("帮助", alias={"help", "菜单"})
    async def 帮助(self, event: AstrMessageEvent):
        """列出所有指令。"""
        yield event.plain_result(_帮助文本)

    @爱完美.command("绑定", alias={"绑定steamid"})
    async def 绑定(self, event: AstrMessageEvent, 内容: GreedyStr):
        """绑定 steamid64，绑定后就能查这个号的战绩。

        参数接受任意内容：Steam 个人资料页网址、启动器参数、含那串数字的
        消息都行，插件会自己从里面提取 steamid64。
        """
        用户 = event.get_sender_id()
        if not 用户:
            yield event.plain_result("拿不到你的用户标识，无法绑定。")
            return

        已有 = self._凭据.读取(用户)
        if 已有:
            yield event.plain_result(
                f"你已经绑定了 steamid {已有['steamid']}。要换号先用 /爱完美 解绑。"
            )
            return

        try:
            有效 = 取有效steamid(str(内容))
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return

        # 先探一次接口再落库。用户打错一位数字的话，这里就会失败，
        # 而不是存进去之后每次查询都报错。
        async with 完美传输() as 传输:
            try:
                文本, 统计 = await 读战绩数据(传输, 有效)
            except 业务错误 as exc:
                yield event.plain_result(f"完美接口拒绝了这次查询：{exc}")
                return
            except Exception as exc:
                logger.warning(f"[aiwm] 绑定前查询失败：{type(exc).__name__}: {exc}")
                yield event.plain_result(f"查询完美接口失败：{exc}")
                return

        if not 统计.get("总场次"):
            self._凭据.写入(用户, 有效, 昵称=self._昵称(event))
            yield event.plain_result(
                f"已绑定 steamid {有效}，但完美平台没有返回战绩数据。"
                "可能对方关闭了战绩展示，或还没打过天梯。"
            )
            return

        # 顺手记下平台显示名。PK 时要念出双方的名字，而对手的显示名只能
        # 在对方绑定时留下——事件在 PK 那一刻是拿不到的。
        self._凭据.写入(用户, 有效, 昵称=self._昵称(event))
        logger.info(f"[aiwm] 用户绑定 steamid {有效}")
        yield event.plain_result(
            f"绑定成功，steamid {有效}。\n\n战绩：\n{文本}\n\n"
            "发 /爱完美 昵称 <名字> 可以改你在 PK 时被叫的名字。"
        )

    def _昵称(self, event: AstrMessageEvent) -> str:
        """发起绑定那个人的平台显示名。取不到就空着，不猜。"""
        try:
            return str(event.get_sender_name() or "")
        except Exception:
            return ""

    @爱完美.command("解绑")
    async def 解绑(self, event: AstrMessageEvent):
        """解除绑定并删除记录。"""
        用户 = event.get_sender_id()
        记录 = self._凭据.删除(用户)
        if not 记录:
            yield event.plain_result("你还没有绑定 steamid。")
            return
        yield event.plain_result(f"已解绑，本地记录已删除（steamid {记录['steamid']}）。")

    @爱完美.command("昵称")
    async def 昵称(self, event: AstrMessageEvent, 名字: GreedyStr):
        """改 PK 时被叫的名字。不带参数时看当前是什么。"""
        用户 = event.get_sender_id()
        记录 = self._凭据.读取(用户)
        if not 记录:
            yield event.plain_result("还没绑定 steamid，先发 /爱完美 绑定。")
            return

        新名 = str(名字).strip()
        if not 新名:
            当前 = str(记录.get("昵称") or "").strip()
            yield event.plain_result(
                f"当前 PK 名字：{当前 or '（还没设）'}"
                + (f"，绑定时自动取的是「{当前}」" if 当前 else "")
            )
            return

        # 名字要念在 PK 的提示里，太长会把版面挤掉，也让人在 PK 时敲不完。
        if len(新名) > _昵称上限:
            yield event.plain_result(f"名字太长了，最多 {_昵称上限} 个字。")
            return

        self._凭据.写入(用户, 记录["steamid"], 昵称=新名)
        yield event.plain_result(f"PK 名字改成「{新名}」。群里发 /爱完美 PK {新名} 就能点到你。")

    @爱完美.command("状态", alias={"status"})
    async def 状态(self, event: AstrMessageEvent):
        """看当前绑定情况。排查用。"""
        用户 = event.get_sender_id()
        记录 = self._凭据.读取(用户)

        行 = [f"你的标识：{用户 or '（拿不到）'}"]
        if 记录:
            昵称 = str(记录.get("昵称") or "").strip()
            行.append(
                f"已绑定 steamid {记录['steamid']}"
                + (f"，PK 名字 {昵称}" if 昵称 else "，还没设 PK 名字")
            )
        else:
            行.append("未绑定 steamid，发 /爱完美 绑定 <steamid64> 开始。")

        yield event.plain_result("\n".join(行))

    @爱完美.command("战绩")
    async def 战绩(self, event: AstrMessageEvent):
        """当前绑定的近期战绩摘要。"""
        文本, _ = await self._读战绩(event.get_sender_id())
        yield event.plain_result(文本)

    @llm_tool(name="get_cs2_profile")
    async def 查询玩家画像(self, event: AstrMessageEvent) -> str:
        """读取提问者自己绑定的 CS2 战绩，并给出结构化摘要。

        Returns:
            段位、胜率、KD、ADR、KAST 等统计结果，以及常用地图与武器。
            玩家关闭了战绩展示时返回说明文字。
        """
        文本, _ = await self._读战绩(event.get_sender_id())
        return 文本

    @爱完美.command("锐评")
    async def 锐评(self, event: AstrMessageEvent):
        """让模型基于近期战绩给一段评价。"""
        数据, 统计 = await self._读战绩(event.get_sender_id())
        if 统计 is None:
            yield event.plain_result(数据)
            return

        try:
            提供方 = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
        except Exception as exc:
            yield event.plain_result(f"取不到当前对话用的模型：{exc}")
            return

        try:
            结果 = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=提供方,
                prompt=锐评提示(数据),
                max_steps=8,
            )
        except Exception as exc:
            logger.warning(f"[aiwm] 锐评失败：{type(exc).__name__}: {exc}")
            yield event.plain_result(f"锐评失败：{exc}")
            return

        yield event.plain_result(结果.completion_text or "模型没有返回内容。")

    @爱完美.command("PK", alias={"pk", "对战"})
    async def PK(self, event: AstrMessageEvent, 目标: GreedyStr):
        """和另一个人比近期战绩。

        对手从三处找：@ 组件、正文里的 `<@!id>`、以及绑定时记下的昵称。
        QQ 官方平台上 @ 别人拿不到标识（适配器只把 @机器人 转成组件），
        所以昵称那条是实际能走通的路径。
        """
        自己 = event.get_sender_id()
        自己记录 = self._凭据.读取(自己)
        if not 自己记录:
            yield event.plain_result("还没绑定 steamid，先发 /爱完美 绑定。")
            return

        参数 = str(目标).strip()
        命中数, 对手记录 = self._找对手记录(event, 参数)
        if not 对手记录:
            if 命中数 > 1:
                可选 = "、".join(
                    str(记录.get("昵称") or 记录["steamid"]) for 记录 in self._同名候选(参数)[:5]
                )
                yield event.plain_result(
                    f"有 {命中数} 个人叫「{参数}」，分不清是哪个。\n"
                    f"候选：{可选}\n"
                    "让对方用 /爱完美 昵称 换个更特别的名字。"
                )
                return
            yield event.plain_result(
                "没找到要 PK 的人。可以直接发他的 PK 名字：\n"
                "例：/爱完美 PK 小明\n"
                "对方需要先绑定 steamid，并且用 /爱完美 昵称 设过名字。"
            )
            return

        # 自己跟自己 PK 没有意义，而昵称可能与别人重名。
        if str(对手记录.get("用户") or "") == 自己 and 自己:
            yield event.plain_result("不能跟自己 PK。")
            return

        async with 完美传输() as 传输:
            try:
                自己数据, 自己统计 = await 读战绩数据(传输, 自己记录["steamid"])
            except Exception as exc:
                logger.warning(f"[aiwm] PK 读自己战绩失败：{type(exc).__name__}: {exc}")
                yield event.plain_result(f"读取你的战绩失败：{exc}")
                return

            try:
                对手数据, 对手统计 = await 读战绩数据(传输, 对手记录["steamid"])
            except Exception as exc:
                logger.warning(f"[aiwm] PK 读对手战绩失败：{type(exc).__name__}: {exc}")
                yield event.plain_result(f"读取对方的战绩失败：{exc}")
                return

        if not 自己统计.get("总场次") or not 对手统计.get("总场次"):
            yield event.plain_result(
                "有一方没有战绩数据。对方可能在完美平台关了战绩展示，或还没打过天梯。"
            )
            return

        自己名 = self._显示名(str(自己记录.get("昵称") or ""), "你")
        对手名 = self._显示名(str(对手记录.get("昵称") or ""), "对手")

        # 逐项对比里用真实姓名，不用「甲／乙」。同一份提示里一处写「甲占优」
        # 一处写「老王 3 项」，模型得自己推断甲是老王——这层映射没有必要，
        # 平白多一次出错的机会。
        要点 = 对比要点(自己统计, 对手统计)
        if not 要点:
            yield event.plain_result("双方的数据没有可比的项目。")
            return

        try:
            提供方 = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
        except Exception as exc:
            yield event.plain_result(f"取不到当前对话用的模型：{exc}")
            return

        try:
            结果 = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=提供方,
                prompt=PK提示(
                    自己名,
                    对手名,
                    对比文本(要点, 自己名, 对手名),
                    占优项数(要点, 自己名, 对手名),
                    自己数据,
                    对手数据,
                ),
                max_steps=8,
            )
        except Exception as exc:
            logger.warning(f"[aiwm] PK 失败：{type(exc).__name__}: {exc}")
            yield event.plain_result(f"PK 失败：{exc}\n\n两人的数据：\n\n{自己数据}\n\n{对手数据}")
            return

        yield event.plain_result(结果.completion_text or "模型没有返回内容。")

    def _找对手记录(self, event: AstrMessageEvent, 参数: str) -> tuple[int, dict[str, Any] | None]:
        """按可靠性依次找对手，返回 (按昵称命中的人数, 要用的记录)。

        标识那条先试（`aiwm/pk.py`），再按昵称找（`storage.按昵称找`）。
        昵称命中的是**记录**而不是标识，所以查到之后直接用记录里的
        `steamid`，不要再去拼一个用户标识出来。

        返回命中人数是给「有几个人叫这个名字」那条回复用的。对真实存在的
        名字回一句「没找到」，等于告诉用户他没绑定。
        """
        对手标识 = 找对手(
            event.get_messages(),
            f"{参数} {getattr(event, 'message_str', '') or ''}",
            自己=event.get_sender_id(),
            机器人=self._机器人标识(event),
        )
        if 对手标识:
            记录 = self._凭据.读取(对手标识)
            if 记录:
                return 0, 记录

        命中的 = self._凭据.按昵称找(参数)
        if len(命中的) == 1:
            return 1, 命中的[0]
        if len(命中的) > 1:
            可选 = "、".join(str(记录.get("昵称") or 记录["steamid"]) for 记录 in 命中的[:5])
            logger.warning(f"[aiwm] PK 按昵称「{参数}」匹配到 {len(命中的)} 个人：{可选}")
        return len(命中的), None

    def _同名候选(self, 参数: str) -> list[dict[str, Any]]:
        """按昵称找到的所有记录。给「有几个人叫这个名字」那条回复列候选用。"""
        return self._凭据.按昵称找(参数)

    async def _读战绩(self, 用户: str) -> tuple[str, dict[str, Any] | None]:
        """读一个用户的战绩，返回 (给用户看的文本, 统计字典)。

        统计字典为 None 表示没有可用数据——没绑定、读失败，或者对方关闭了
        战绩展示。**调用方要靠这个 None 判断能不能继续，不能靠文本长什么样**：
        「没有战绩数据」和「读取战绩失败」都是给人看的整句话，两者若当成数据
        喂给模型，锐评提示会要求它写够 3 个具体数字，模型只能编。
        """
        记录 = self._凭据.读取(用户)
        if not 记录:
            return "提问者还没有绑定 steamid，无法查询战绩。", None

        async with 完美传输() as 传输:
            try:
                文本, 统计 = await 读战绩数据(传输, 记录["steamid"])
            except Exception as exc:
                logger.warning(f"[aiwm] 读战绩失败：{type(exc).__name__}: {exc}")
                return f"读取战绩失败：{exc}", None

        if not 统计.get("总场次"):
            return 文本, None
        return 文本, 统计

    @staticmethod
    def _显示名(候选: str, 兜底: str) -> str:
        return 候选.strip() or 兜底

    @staticmethod
    def _机器人标识(event: AstrMessageEvent) -> str:
        """机器人自己的标识。群里 @机器人 会产生 At 组件，得把它排掉。"""
        try:
            return str(event.get_self_id() or "")
        except Exception:
            return ""
