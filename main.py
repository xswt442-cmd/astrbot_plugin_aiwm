"""爱完美：CS2 战绩查询。

用户绑定自己的 steamid64 后，指令与模型都能读到他自己的战绩数据。

数据来自 `api.wmpvp.com`——域名是完美竞技平台的，但**返回的是 CS2 官方匹配
（官匹）的数据**，不是完美平台的对局记录。三条实测证据见 `aiwm/source.py`。
所以输出里不能说「完美平台战绩」。
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import command_group, custom_filter, llm_tool
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.star.filter.custom_filter import CustomFilter

# 全部在模块顶层导入。插件加载时就把整个包摸清：少文件、依赖缺失都在启动
# 阶段报错，而不是等用户发了指令才在懒加载里抛模块不存在。
from .aiwm.battles import fetch_battle_data
from .aiwm.fallback import (
    is_bare_command,
    is_command_miss,
    leftover_arg,
    miss_hint,
    starts_with_group,
)
from .aiwm.match import build_match_setup, setup_text
from .aiwm.pk import find_opponent
from .aiwm.pk_target import OpponentSource, resolve_opponent
from .aiwm.prompts import match_prompt, pk_prompt, review_prompt
from .aiwm.stats import advantage_count, contrast_points, contrast_text
from .aiwm.storage import CredentialStore, clean_nickname, resolve_steamid
from .aiwm.transport import ApiError, WmpvpClient

# 指令组名。改这里要同时改 `_帮助文本` 的开头与 `aiwm/fallback.py` 的取参函数。
_GROUP = "爱完美"

# 组名别名。QQ 官方适配器在「@机器人 + 指令」这条路径上走的是 At 唤醒分支，
# 那条分支只置 `wake_prefix = ""`，**不剥掉 message_str 里的 `/`**——只有
# startswith 分支才剥。于是 message_str 仍是 `/爱完美 战绩`，组名 `爱完美`
# 匹配不上，整条指令静默失败。加一个带斜杠的别名，两种写法都能进。
_GROUP_ALIASES = {f"/{_GROUP}"}

# 数据目录必须用插件名。市场审核要求 `data/plugin_data/<plugin_name>`，
# 而 `<plugin_name>` 指插件目录名，不是自造的简称。
_PLUGIN_NAME = "astrbot_plugin_aiwm"
# 0.1.9 及以前用的是这个简称目录，升级时把凭据搬过来。
_LEGACY_DATA_DIR = "aiwm"


def _migrate_legacy_credentials(new_dir: Path) -> None:
    """把 `plugin_data/aiwm` 里的凭据搬到 `plugin_data/astrbot_plugin_aiwm`。

    只搬不覆盖：新目录已有同名文件就保留新的。搬完把空掉的旧目录删掉。
    """
    legacy_dir = new_dir.parent / _LEGACY_DATA_DIR
    if not legacy_dir.is_dir() or legacy_dir.resolve() == new_dir.resolve():
        return

    for file in sorted(legacy_dir.glob("*.json")):
        target = new_dir / file.name
        if target.exists():
            continue
        try:
            shutil.move(str(file), str(target))
            target.chmod(0o600)
        except OSError as exc:
            logger.warning(f"[aiwm] 迁移旧凭据失败 {file.name}：{exc}")

    try:
        legacy_dir.rmdir()
    except OSError:
        pass


# PK 名字要念在提示里，太长挤版面。
_NICKNAME_LIMIT = 16


def _config_int(config: Any, key: str, default: int) -> int:
    """从配置里取正整数。缺项、写错、非正数都退回默认值。"""
    if config is None:
        return default
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _config_flag(config: Any, key: str, default: bool) -> bool:
    if config is None:
        return default
    try:
        return bool(config.get(key, default))
    except Exception:  # noqa: BLE001 - 配置读不到就当默认
        return default


_HELP_TEXT = """爱完美 · CS2 战绩
数据来自 CS2 官方匹配（官匹），不是完美竞技平台。
/爱完美 绑定 <steamid64>
记下你的 SteamID64，网址和启动器参数里粘过来也行。
/爱完美 战绩
查询近期战绩。
/爱完美 锐评
让 bot 基于你的近期战绩进行锐评。
/爱完美 开一局
让 bot 推演你开的下一局。
/爱完美 PK <steamid64 或名字>
与另一个人比近期战绩，对方不用绑定。
/爱完美 昵称 <名字>
设置自己的昵称，不设则默认使用你的 QQ 昵称。
/爱完美 状态
查看自己的绑定状态。
/爱完美 解绑
解除绑定并删除本地记录。
/爱完美 帮助
就是这条。
直接用自然语言问也可以，例如「我的 CS2 战绩怎么样？」"""


class _MissFallbackFilter(CustomFilter):
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
    立刻放行（这一步不能省，见 `aiwm.fallback.以组名开头`），命中就自己给结果。
    写反的后果：正常指令没反应，或者别人的消息被误掐——两个都实际发生过。
    """

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        text = getattr(event, "message_str", "") or ""
        # 这条过滤器对**每一条消息**都会跑（CommandGroupFilter 先跑
        # custom_filter_ok 再检查组名），所以第一件事是判断关不关我事。
        if not starts_with_group(text, _GROUP):
            return True
        if is_bare_command(text, _GROUP):
            # 只发了「/爱完美」：回帮助。交给框架会甩一串「参数不足」加各指令的
            # docstring，用户看到的是内部说明，不是能发什么。
            event.set_result(MessageEventResult().message(_HELP_TEXT))
            event.stop_event()
            return True
        if is_command_miss(text, _GROUP):
            event.set_result(MessageEventResult().message(miss_hint(leftover_arg(text, _GROUP))))
            event.stop_event()
        return True


class Main(Star):
    # `custom_filter_ok` 每次判断时都会问一遍。
    #
    # 别写成 `self.爱完美.add_custom_filter(...)`——`self.爱完美` 是
    # `RegisteringCommandable`，它没有那个方法，会在加载时报 AttributeError。
    @custom_filter(_MissFallbackFilter)
    @command_group(_GROUP, alias=_GROUP_ALIASES)
    def aiwm_group(self):
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
        self._request_timeout = _config_int(config, "request_timeout_seconds", 30)
        self._max_steps = _config_int(config, "llm_max_steps", 8)
        self._pk_enabled = _config_flag(config, "pk_enabled", True)
        self._store = CredentialStore(self._data_dir())

    def _data_dir(self) -> Path:
        from astrbot.core.star.star_tools import StarTools

        directory = StarTools.get_data_dir(_PLUGIN_NAME)
        _migrate_legacy_credentials(directory)
        return directory

    @aiwm_group.command("帮助", alias={"help", "菜单"})
    async def help_cmd(self, event: AstrMessageEvent):
        """列出所有指令。"""
        yield event.plain_result(_HELP_TEXT)

    @aiwm_group.command("绑定", alias={"绑定steamid"})
    async def bind_cmd(self, event: AstrMessageEvent, content: GreedyStr):
        """绑定 steamid64，绑定后就能查这个号的战绩。

        参数接受任意内容：Steam 个人资料页网址、启动器参数、含那串数字的
        消息都行，插件会自己从里面提取 steamid64。
        """
        user_id = event.get_sender_id()
        if not user_id:
            yield event.plain_result("拿不到你的用户标识，无法绑定。")
            return

        existing = self._store.read(user_id)
        if existing:
            yield event.plain_result(
                f"已经绑定了 steamid {existing['steamid']}，换号先发 /爱完美 解绑。"
            )
            return

        try:
            valid = resolve_steamid(str(content))
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return

        # 先探一次接口再落库。用户打错一位数字的话，这里就会失败，
        # 而不是存进去之后每次查询都报错。
        async with WmpvpClient(self._request_timeout) as client:
            try:
                text, stats = await fetch_battle_data(client, valid)
            except ApiError as exc:
                yield event.plain_result(f"接口拒绝了这次查询：{exc}")
                return
            except Exception as exc:
                logger.warning(f"[aiwm] 绑定前查询失败：{type(exc).__name__}: {exc}")
                yield event.plain_result(f"接口查询失败：{exc}")
                return

        if not stats.get("总场次"):
            self._store.write(user_id, valid, nickname=self._nickname(event))
            yield event.plain_result(f"已绑定 steamid {valid}，但这个号没有战绩数据。")
            return

        # 顺手记下平台显示名。PK 时要念出双方的名字，而对手的显示名只能
        # 在对方绑定时留下——事件在 PK 那一刻是拿不到的。
        self._store.write(user_id, valid, nickname=self._nickname(event))
        logger.info(f"[aiwm] 用户绑定 steamid {valid}")
        yield event.plain_result(f"绑定成功，steamid {valid}。\n\n战绩：\n{text}")

    def _nickname(self, event: AstrMessageEvent) -> str:
        """发起绑定那个人的平台显示名。取不到就空着，不猜。"""
        try:
            return clean_nickname(event.get_sender_name() or "")
        except Exception:
            return ""

    @aiwm_group.command("解绑")
    async def unbind_cmd(self, event: AstrMessageEvent):
        """解除绑定并删除记录。"""
        user_id = event.get_sender_id()
        record = self._store.delete(user_id)
        if not record:
            yield event.plain_result("还没绑定。")
            return
        yield event.plain_result(f"已解绑（steamid {record['steamid']}）。")

    @aiwm_group.command("昵称")
    async def nickname(self, event: AstrMessageEvent, name: GreedyStr):
        """改 PK 时被叫的名字。不带参数时看当前是什么。"""
        user_id = event.get_sender_id()
        record = self._store.read(user_id)
        if not record:
            yield event.plain_result("还没绑定，先发 /爱完美 绑定 <steamid64>。")
            return

        # 先洗掉换行与零宽字符：昵称会被拼进 PK 提示词，带换行等于多一行指令。
        new_name = clean_nickname(name)
        if not new_name:
            current = clean_nickname(record.get("昵称") or "")
            yield event.plain_result(f"当前 PK 名字：「{current or '（还没设）'}」。")
            return

        # 名字要念在 PK 的提示里，太长会把版面挤掉，也让人在 PK 时敲不完。
        if len(new_name) > _NICKNAME_LIMIT:
            yield event.plain_result(f"名字太长了，最多 {_NICKNAME_LIMIT} 个字。")
            return

        self._store.write(user_id, record["steamid"], nickname=new_name)
        yield event.plain_result(f"PK 名字改成「{new_name}」。")

    @aiwm_group.command("状态", alias={"status"})
    async def status_cmd(self, event: AstrMessageEvent):
        """看当前绑定情况。排查用。"""
        user_id = event.get_sender_id()
        record = self._store.read(user_id)

        line = [f"你的标识：{user_id or '（拿不到）'}"]
        if record:
            nickname = str(record.get("昵称") or "").strip()
            line.append(
                f"已绑定 steamid {record['steamid']}"
                + (f"，PK 名字「{nickname}」" if nickname else "，还没设 PK 名字")
            )
        else:
            line.append("还没绑定，先发 /爱完美 绑定 <steamid64>。")

        yield event.plain_result("\n".join(line))

    @aiwm_group.command("战绩")
    async def matches_cmd(self, event: AstrMessageEvent):
        """当前绑定的近期战绩摘要。"""
        text, _ = await self._fetch_battles(event.get_sender_id())
        yield event.plain_result(text)

    @llm_tool(name="get_cs2_profile")
    async def profile_tool(self, event: AstrMessageEvent) -> str:
        """读取提问者自己绑定的 CS2 战绩，并给出结构化摘要。

        Returns:
            段位、胜率、KD、ADR、KAST 等统计结果，以及常用地图与武器。
            玩家关闭了战绩展示时返回说明文字。
        """
        text, _ = await self._fetch_battles(event.get_sender_id())
        return text

    @aiwm_group.command("锐评")
    async def review_cmd(self, event: AstrMessageEvent):
        """让模型基于近期战绩给一段评价。"""
        data, stats = await self._fetch_battles(event.get_sender_id())
        if stats is None:
            yield event.plain_result(data)
            return

        try:
            provider_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
        except Exception as exc:
            yield event.plain_result(f"取不到当前对话用的模型：{exc}")
            return

        try:
            result = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=provider_id,
                prompt=review_prompt(data),
                max_steps=self._max_steps,
            )
        except Exception as exc:
            logger.warning(f"[aiwm] 锐评调用模型失败：{type(exc).__name__}: {exc}")
            yield event.plain_result(f"调用模型失败：{exc}")
            return

        yield event.plain_result(result.completion_text or "模型没有返回内容。")

    @aiwm_group.command("开一局", alias={"开局", "来一局"})
    async def play_match_cmd(self, event: AstrMessageEvent):
        """随机生成一局，让模型推演过程与结果。

        数字全是随机生成的，只贴着玩家的真实水平走个形。绑定过的话推演会
        贴近他的实际表现，没绑定就按中等水平来。
        """
        user_id = event.get_sender_id()
        record = self._store.read(user_id)

        stats = None
        if record:
            # 开一局不需要拿到完整战绩，接口失败就退回「无历史数据」那一档，
            # 不要因为查不到战绩就让这条指令整个用不了。
            try:
                async with WmpvpClient(self._request_timeout) as client:
                    _, stats = await fetch_battle_data(client, record["steamid"])
            except Exception as exc:
                logger.info(f"[aiwm] 开一局读战绩失败，按无历史数据推演：{exc}")
                stats = None

        setup = build_match_setup(random.Random(), stats)

        try:
            provider_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
        except Exception as exc:
            yield event.plain_result(f"取不到当前对话用的模型：{exc}")
            return

        try:
            result = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=provider_id,
                prompt=match_prompt(setup_text(setup)),
                max_steps=self._max_steps,
            )
        except Exception as exc:
            logger.warning(f"[aiwm] 开一局调用模型失败：{type(exc).__name__}: {exc}")
            yield event.plain_result(f"调用模型失败：{exc}")
            return

        # 设定先给用户看，模型写崩了至少还有这一局的数字。
        yield event.plain_result(
            f"{setup_text(setup)}\n\n{result.completion_text or '模型没有返回内容。'}"
        )

    @aiwm_group.command("PK", alias={"pk", "对战"})
    async def PK(self, event: AstrMessageEvent, target: GreedyStr):
        """和另一个人比近期战绩。

        对手从三处找，参数优先：参数里含 steamid 就直接用它（对方不用绑定），
        否则试 @ 组件，最后按本机记下的 PK 名字找。
        """
        if not self._pk_enabled:
            yield event.plain_result("PK 已关闭。")
            return
        me = event.get_sender_id()
        my_record = self._store.read(me)
        if not my_record:
            yield event.plain_result("还没绑定，先发 /爱完美 绑定 <steamid64>。")
            return

        arg = str(target).strip()
        # @ 组件那条要把自己排除掉，否则在群里 @ 一下就变成跟自己 PK。
        # 文本要带上命令参数：官方适配器只把「@机器人」转成组件，@别人会原样
        # 留在正文里。
        at_id = self._at_id(event, arg)
        opponent_steam_id, source, opponent_record = resolve_opponent(
            arg, at_id, self._find_by_nickname
        )

        if source == OpponentSource.NOT_FOUND:
            hit_count = self._find_by_nickname(arg)[0]
            if hit_count > 1:
                candidates = "\n".join(
                    f"· {record.get('昵称') or record['steamid']}"
                    for record in self._same_name_candidates(arg)[:5]
                )
                yield event.plain_result(
                    f"有 {hit_count} 个人叫「{arg}」，写完整一点：\n{candidates}"
                )
                return
            yield event.plain_result(
                "没找到要 PK 的人，发他的 steamid64 就行，例如 /爱完美 PK 76561198159976336。"
            )
            return

        # 自己跟自己 PK 没有意义。参数直接给 id 时也拦一下——昵称那条拦不住，
        # 因为昵称可能重名，但同一个 id 一眼就能认出来。
        if opponent_steam_id == my_record["steamid"]:
            yield event.plain_result("不能跟自己 PK。")
            return
        # 昵称那条要额外看用户标识：可能查到的是自己那条记录
        if opponent_record and str(opponent_record.get("用户") or "") == me and me:
            yield event.plain_result("不能跟自己 PK。")
            return

        async with WmpvpClient(self._request_timeout) as client:
            try:
                my_data, my_stats = await fetch_battle_data(client, my_record["steamid"])
            except Exception as exc:
                logger.warning(f"[aiwm] PK 读自己战绩失败：{type(exc).__name__}: {exc}")
                yield event.plain_result(f"读取你的战绩失败：{exc}")
                return

            try:
                opponent_data, opponent_stats = await fetch_battle_data(client, opponent_steam_id)
            except Exception as exc:
                logger.warning(f"[aiwm] PK 读对手战绩失败：{type(exc).__name__}: {exc}")
                yield event.plain_result(f"读取对方的战绩失败：{exc}")
                return

        if not my_stats.get("总场次") or not opponent_stats.get("总场次"):
            yield event.plain_result("有一方没有战绩数据。")
            return

        my_name = self._display_name(str(my_record.get("昵称") or ""), "你")
        # 参数直接给 id 时没有本机记下的昵称，就用接口返回的显示名——那是这人在
        # 平台上的名字，总比「对手」两个字好。
        opponent_name = self._display_name(
            str((opponent_record or {}).get("昵称") or opponent_stats.get("昵称") or ""), "对手"
        )

        # 逐项对比里用真实姓名，不用「甲／乙」。同一份提示里一处写「甲占优」
        # 一处写「老王 3 项」，模型得自己推断甲是老王——这层映射没有必要，
        # 平白多一次出错的机会。
        points = contrast_points(my_stats, opponent_stats)
        if not points:
            yield event.plain_result("两边没有可比的项目。")
            return

        try:
            provider_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
        except Exception as exc:
            yield event.plain_result(f"取不到当前对话用的模型：{exc}")
            return

        try:
            result = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=provider_id,
                prompt=pk_prompt(
                    my_name,
                    opponent_name,
                    contrast_text(points, my_name, opponent_name),
                    advantage_count(points, my_name, opponent_name),
                    my_data,
                    opponent_data,
                ),
                max_steps=self._max_steps,
            )
        except Exception as exc:
            logger.warning(f"[aiwm] PK 调用模型失败：{type(exc).__name__}: {exc}")
            yield event.plain_result(
                f"调用模型失败：{exc}\n\n两人的数据：\n\n{my_data}\n\n{opponent_data}"
            )
            return

        yield event.plain_result(result.completion_text or "模型没有返回内容。")

    def _find_by_nickname(self, arg: str) -> tuple[int, dict[str, Any] | None]:
        """在本机记下的 PK 名字里找，返回 (命中人数, 要用的记录)。

        只有本机绑定过的人在这里。参数直接给 steamid 或 @ 组件那两条路不经过
        这里，所以对方没绑定也能 PK。

        命中人数是给「有几个人叫这个名字」那条回复用的。对真实存在的名字回
        一句「没找到」，等于告诉用户他没绑定。
        """
        matched = self._store.find_by_nickname(arg)
        if len(matched) == 1:
            return 1, matched[0]
        if len(matched) > 1:
            options = "、".join(
                str(record.get("昵称") or record["steamid"]) for record in matched[:5]
            )
            logger.warning(f"[aiwm] PK 按昵称「{arg}」匹配到 {len(matched)} 个人：{options}")
        return len(matched), None

    def _at_id(self, event: AstrMessageEvent, arg: str) -> str | None:
        """从 @ 组件或正文里取被 @ 者的标识。取不到返回 `None`。

        文本是命令参数与消息正文的拼接——正文里的 `<@!id>` 形式要靠它抠。
        """
        return find_opponent(
            event.get_messages(),
            f"{arg} {getattr(event, 'message_str', '') or ''}",
            me=event.get_sender_id(),
            bot_id=self._bot_id(event),
        )

    def _same_name_candidates(self, arg: str) -> list[dict[str, Any]]:
        """按昵称找到的所有记录。给「有几个人叫这个名字」那条回复列候选用。"""
        return self._store.find_by_nickname(arg)

    async def _fetch_battles(self, user_id: str) -> tuple[str, dict[str, Any] | None]:
        """读一个用户的战绩，返回 (给用户看的文本, 统计字典)。

        统计字典为 None 表示没有可用数据——没绑定、读失败，或者对方关闭了
        战绩展示。**调用方要靠这个 None 判断能不能继续，不能靠文本长什么样**：
        「没有战绩数据」和「读取战绩失败」都是给人看的整句话，两者若当成数据
        喂给模型，锐评提示会要求它写够 3 个具体数字，模型只能编。
        """
        record = self._store.read(user_id)
        if not record:
            return "还没绑定，先发 /爱完美 绑定 <steamid64>。", None

        async with WmpvpClient(self._request_timeout) as client:
            try:
                text, stats = await fetch_battle_data(client, record["steamid"])
            except Exception as exc:
                logger.warning(f"[aiwm] 读战绩失败：{type(exc).__name__}: {exc}")
                return f"读取战绩失败：{exc}", None

        if not stats.get("总场次"):
            return text, None
        return text, stats

    @staticmethod
    def _display_name(candidates: str, fallback: str) -> str:
        # 老记录可能是净化之前存的，念之前再洗一次。
        return clean_nickname(candidates) or fallback

    @staticmethod
    def _bot_id(event: AstrMessageEvent) -> str:
        """机器人自己的标识。群里 @机器人 会产生 At 组件，得把它排掉。"""
        try:
            return str(event.get_self_id() or "")
        except Exception:
            return ""
