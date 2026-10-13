"""爱完美：CS2 战绩查询。

用户绑定自己的 steamid64 后，指令与模型都能读到他自己的战绩数据。

数据来自 `api.wmpvp.com`——域名是完美竞技平台的，但**返回的是 CS2 官方匹配
（官匹）的数据**，不是完美平台的对局记录。三条实测证据见 `aiwm/来源.py`。
所以输出里不能说「完美平台战绩」。
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import command_group, custom_filter, llm_tool
from astrbot.api.star import Context, Star
from astrbot.core.platform.astr_message_event import MessageEventResult
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.star.filter.custom_filter import CustomFilter

# 全部在模块顶层导入。插件加载时就把整个包摸清：少文件、依赖缺失都在启动
# 阶段报错，而不是等用户发了指令才在懒加载里抛模块不存在。
from .aiwm.battles import 读战绩数据
from .aiwm.match import 开局设定, 设定文本
from .aiwm.pk import 找对手
from .aiwm.pk_target import 取对手标识, 对手来源
from .aiwm.prompts import PK提示, 开局提示, 锐评提示
from .aiwm.stats import 占优项数, 对比文本, 对比要点
from .aiwm.storage import 凭据仓库, 取有效steamid
from .aiwm.transport import 业务错误, 完美传输
from .aiwm.兜底 import 以组名开头, 取落空参数, 是否落空, 落空提示

# 指令组名。改这里要同时改 `_帮助文本` 的开头与 `aiwm/兜底.py` 的取参函数。
_组名 = "爱完美"

# 组名别名。QQ 官方适配器在「@机器人 + 指令」这条路径上走的是 At 唤醒分支，
# 那条分支只置 `wake_prefix = ""`，**不剥掉 message_str 里的 `/`**——只有
# startswith 分支才剥。于是 message_str 仍是 `/爱完美 战绩`，组名 `爱完美`
# 匹配不上，整条指令静默失败。加一个带斜杠的别名，两种写法都能进。
_组别名 = {f"/{_组名}"}

# PK 名字要念在提示里，太长挤版面。
_昵称上限 = 16

_帮助文本 = """爱完美 · CS2 战绩查询

数据来自 CS2 官方匹配（官匹），不是完美竞技平台的对局记录。

/爱完美 绑定 <steamid64>
  记下你的 SteamID64，之后的查询都看它。

  不用自己从一串东西里挑数字——下面这些粘给我都行，我从里面取：
  · Steam 个人资料页的网址（…/profiles/76561198159976336）
  · 启动器参数（steam.exe -login 76561198159976336）
  · 那串数字本身
  查战绩不需要登录平台，不用扫码。

/爱完美 战绩
  近期战绩：分数段与综合分、胜率、KD、Rating、ADR、KAST、RWS、
  爆头率与首杀率、常用地图、常用武器与击杀分布、多杀次数、最近十场评分。

/爱完美 开一局
  随机生成一局，让模型推演过程与结果。数字是编的，会写明这一点。
  绑定过的话推演贴近你的实际水平，没绑定按中等水平来。

/爱完美 锐评
  让模型基于上面的数据写一段锐评。会先给一句称号，再分别说打得好、
  问题和一条具体建议。

/爱完美 PK <steamid64 或名字>
  和另一个人比近期战绩。对方不用绑定：
  · 直接发他的 steamid64 或含它的网址，我从里面取
  · 发他在本机记下的 PK 名字（用 /爱完美 昵称 设的）

  模型会给两人各打一个趣味分并点评胜负手。

/爱完美 昵称 <名字>
  改你在 PK 时被叫的名字。不设的话取绑定时的显示名。

/爱完美 解绑
  解除绑定并立即删除本地记录。

/爱完美 状态
  看自己的标识、绑定情况。排查用。

/爱完美 帮助
  就是这条。

直接问模型「我的 CS2 战绩怎么样」也会走同一套数据。"""


class _落空兜底(CustomFilter):
    """`/爱完美 <没匹配上子命令的内容>` 时自己回一句。

    没有它的话这条消息会被 AstrBot 跳过指令、**原样进模型**——模型收到的是
    一句普通提问，于是自己编。实测用户发 `/爱完美 <Steam 主页链接>`，模型回
    「打不开Steam，你发链接干嘛，考验我视力？」还自称「我又没权限爬Steam」，
    它并不在查 Steam，它在编。

    只在真落空时 `set_result` + `stop_event`：前者把提示词放进结果链让适配器
    发出去，后者终止事件传播，免得消息继续走到模型。

    `filter` 的返回值语义是「这条消息我管不管」，**不是**「我有没有命中」——
    `CommandGroupFilter.filter` 里`if not self.custom_filter_ok(...): return False`，
    返回 False 会把整个指令组毙掉。所以所有出口都return True：不归我管就
    立刻放行（这一步不能省，见 `aiwm.兜底.以组名开头`），命中就自己给结果。
    写反的后果：正常指令没反应，或者别人的消息被误掐——两个都实际发生过。
    """

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        文本 = getattr(event, "message_str", "") or ""
        # 这条过滤器对**每一条消息**都会跑（CommandGroupFilter 先跑
        # custom_filter_ok 再检查组名），所以第一件事是判断关不关我事。
        if not 以组名开头(文本, _组名):
            return True
        if 是否落空(文本, _组名):
            event.set_result(MessageEventResult().message(落空提示(取落空参数(文本, _组名))))
            event.stop_event()
        return True


class Main(Star):
    # `custom_filter_ok` 每次判断时都会问一遍。
    #
    # 别写成 `self.爱完美.add_custom_filter(...)`——`self.爱完美` 是
    # `RegisteringCommandable`，它没有那个方法，会在加载时报 AttributeError。
    @custom_filter(_落空兜底)
    @command_group(_组名, alias=_组别名)
    def 爱完美(self):
        """CS2 战绩查询。指令都在这个组下，不占用通用名字。"""

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        """`config` 必须可省。

        AstrBot 的 `star_manager` 在 `if plugin_config and ...:` 分支里才把配置
        传进来，仓库没有 `_conf_schema.json` 时它读不到任何配置项，那一个分支
        不走，于是只传 context。声明成必需参数会 `TypeError: missing 1
        required positional argument: 'config'`，插件整个加载不起来。
        """
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
            logger.warning(f"[aiwm] 锐评调用模型失败：{type(exc).__name__}: {exc}")
            yield event.plain_result(f"调用模型失败：{exc}")
            return

        yield event.plain_result(结果.completion_text or "模型没有返回内容。")

    @爱完美.command("开一局", alias={"开局", "来一局"})
    async def 开一局(self, event: AstrMessageEvent):
        """随机生成一局，让模型推演过程与结果。

        数字全是随机生成的，只贴着玩家的真实水平走个形。绑定过的话推演会
        贴近他的实际表现，没绑定就按中等水平来。
        """
        用户 = event.get_sender_id()
        记录 = self._凭据.读取(用户)

        统计 = None
        if 记录:
            # 开一局不需要拿到完整战绩，接口失败就退回「无历史数据」那一档，
            # 不要因为查不到战绩就让这条指令整个用不了。
            try:
                async with 完美传输() as 传输:
                    _, 统计 = await 读战绩数据(传输, 记录["steamid"])
            except Exception as exc:
                logger.info(f"[aiwm] 开一局读战绩失败，按无历史数据推演：{exc}")
                统计 = None

        设定 = 开局设定(random.Random(), 统计)

        try:
            提供方 = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
        except Exception as exc:
            yield event.plain_result(f"取不到当前对话用的模型：{exc}")
            return

        try:
            结果 = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=提供方,
                prompt=开局提示(设定文本(设定)),
                max_steps=8,
            )
        except Exception as exc:
            logger.warning(f"[aiwm] 开一局调用模型失败：{type(exc).__name__}: {exc}")
            yield event.plain_result(f"调用模型失败：{exc}")
            return

        # 设定先给用户看，模型写崩了至少还有这一局的数字。
        yield event.plain_result(f"{设定文本(设定)}\n\n{结果.completion_text or ''}")

    @爱完美.command("PK", alias={"pk", "对战"})
    async def PK(self, event: AstrMessageEvent, 目标: GreedyStr):
        """和另一个人比近期战绩。

        对手从三处找，参数优先：参数里含 steamid 就直接用它（对方不用绑定），
        否则试 @ 组件，最后按本机记下的 PK 名字找。
        """
        自己 = event.get_sender_id()
        自己记录 = self._凭据.读取(自己)
        if not 自己记录:
            yield event.plain_result("还没绑定 steamid，先发 /爱完美 绑定。")
            return

        参数 = str(目标).strip()
        # @ 组件那条要把自己排除掉，否则在群里 @ 一下就变成跟自己 PK。
        # 文本要带上命令参数：官方适配器只把「@机器人」转成组件，@别人会原样
        # 留在正文里。
        at标识 = self._at标识(event, 参数)
        对手steamid, 来源, 对手记录 = 取对手标识(参数, at标识, self._按昵称找)

        if 来源 == 对手来源.没找到:
            命中数 = self._按昵称找(参数)[0]
            if 命中数 > 1:
                可选 = "、".join(
                    str(记录.get("昵称") or 记录["steamid"]) for 记录 in self._同名候选(参数)[:5]
                )
                yield event.plain_result(
                    f"有 {命中数} 个人叫「{参数}」，分不清是哪个。\n"
                    f"候选：{可选}\n"
                    "直接发对方的 steamid64 最省事，或者让他用 /爱完美 昵称 "
                    "换个更特别的名字。"
                )
                return
            yield event.plain_result(
                "没找到要 PK 的人。可以直接发他的 steamid64，我里面有就查：\n"
                "例：/爱完美 PK 76561198159976336\n"
                "也接受 Steam 个人资料页的网址。\n"
                "发本机记下的 PK 名字也行，但对方得先绑定过。"
            )
            return

        # 自己跟自己 PK 没有意义。参数直接给 id 时也拦一下——昵称那条拦不住，
        # 因为昵称可能重名，但同一个 id 一眼就能认出来。
        if 对手steamid == 自己记录["steamid"]:
            yield event.plain_result("不能跟自己 PK。")
            return
        # 昵称那条要额外看用户标识：可能查到的是自己那条记录
        if 对手记录 and str(对手记录.get("用户") or "") == 自己 and 自己:
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
                对手数据, 对手统计 = await 读战绩数据(传输, 对手steamid)
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
        # 参数直接给 id 时没有本机记下的昵称，就用接口返回的显示名——那是这人在
        # 平台上的名字，总比「对手」两个字好。
        对手名 = self._显示名(
            str((对手记录 or {}).get("昵称") or 对手统计.get("昵称") or ""), "对手"
        )

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
            logger.warning(f"[aiwm] PK 调用模型失败：{type(exc).__name__}: {exc}")
            yield event.plain_result(
                f"调用模型失败：{exc}\n\n两人的数据：\n\n{自己数据}\n\n{对手数据}"
            )
            return

        yield event.plain_result(结果.completion_text or "模型没有返回内容。")

    def _按昵称找(self, 参数: str) -> tuple[int, dict[str, Any] | None]:
        """在本机记下的 PK 名字里找，返回 (命中人数, 要用的记录)。

        只有本机绑定过的人在这里。参数直接给 steamid 或 @ 组件那两条路不经过
        这里，所以对方没绑定也能 PK。

        命中人数是给「有几个人叫这个名字」那条回复用的。对真实存在的名字回
        一句「没找到」，等于告诉用户他没绑定。
        """
        命中的 = self._凭据.按昵称找(参数)
        if len(命中的) == 1:
            return 1, 命中的[0]
        if len(命中的) > 1:
            可选 = "、".join(str(记录.get("昵称") or 记录["steamid"]) for 记录 in 命中的[:5])
            logger.warning(f"[aiwm] PK 按昵称「{参数}」匹配到 {len(命中的)} 个人：{可选}")
        return len(命中的), None

    def _at标识(self, event: AstrMessageEvent, 参数: str) -> str | None:
        """从 @ 组件或正文里取被 @ 者的标识。取不到返回 `None`。

        文本是命令参数与消息正文的拼接——正文里的 `<@!id>` 形式要靠它抠。
        """
        return 找对手(
            event.get_messages(),
            f"{参数} {getattr(event, 'message_str', '') or ''}",
            自己=event.get_sender_id(),
            机器人=self._机器人标识(event),
        )

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
