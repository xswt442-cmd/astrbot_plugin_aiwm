"""指令落空时的兜底。

`/爱完美 <任意内容>` 而内容没匹配上任何子命令时，`CommandGroupFilter.filter`
返回 False，指令被跳过，**消息原样进模型**。模型收到的是一句普通提问，于是
自己编答案：实测用户发 `/爱完美 <steam 个人资料页链接>`，模型回「打不开Steam，
你发链接干嘛，考验我视力？」，还自称「我又没权限爬Steam」——它并不在查 Steam，
它在编。

用户没打错指令，是这条指令没接住。所以指令组挂一个兜底过滤器：匹配了组名但
没匹配任何子命令时，自己回一句提示，把消息拦在这里。

只拦「以组名开头」的。只发了组名（`/爱完美`）也归这里管：框架会给一份
「参数不足」加全部子命令的 docstring，又长又不像是说给用户听的，直接回帮助
更省事。
"""

from __future__ import annotations

__all__ = [
    "SUBCOMMANDS",
    "starts_with_group",
    "leftover_arg",
    "is_command_miss",
    "is_bare_command",
    "miss_hint",
]

# 全部子命令与别名。少一个别名，用户打那个别名时就落空了。
# 改 main.py 里的指令或别名，这里要跟着改——`test_main_wiring.py` 会核对。
SUBCOMMANDS = frozenset(
    {
        # 子命令
        "战绩",
        "锐评",
        "开一局",
        "PK",
        "昵称",
        "解绑",
        "状态",
        "帮助",
        "绑定",
        # 别名
        "绑定steamid",
        "pk",
        "对战",
        "开局",
        "来一局",
        "help",
        "菜单",
        "status",
    }
)


def starts_with_group(message: str, group: str) -> bool:
    """这条消息是不是以指令组名开头。

    **必须有这一层判断**。`CommandGroupFilter.filter` 的执行顺序是
    先跑 `custom_filter_ok()`、之后才检查组名是否匹配，所以挂在指令组上的
    过滤器对**每一条消息**都会执行——包括别的插件的指令和纯聊天。
    没有这道闸，`取落空参数` 对不属于自己的消息会原样返回，于是「在吗」
    被判定成「爱完美的子命令落空」，`stop_event()` 把整条掐死。
    实测过一次：老狗因此对所有消息都不理人，比插件本身故障还严重。
    """
    text = (message or "").strip()
    return text.startswith(f"/{group}") or text.startswith(group)


def leftover_arg(message: str, group: str) -> str:
    """取出组名后面的内容。

    组名可能带 `/` 前缀也可能不带——QQ 官方适配器有时会把 `message_str` 里的
    `/` 去掉，所以两种都得认。

    不以组名开头时返回空串，**不是原样返回**：调用方靠这一点判断「这条消息
    根本不归我管」。
    """
    text = (message or "").strip()
    for prefix in (f"/{group}", group):
        if text.startswith(prefix):
            remainder = text[len(prefix) :].strip()
            # 组名重复出现时（`/爱完美 /爱完美 战绩`）只取第一处之后的
            return remainder
    return ""


def is_command_miss(message: str, group: str) -> bool:
    """这条消息是不是「匹配了组名但没匹配任何子命令」。

    判据必须与 `CommandGroupFilter.startswith` 一致——**字面前缀匹配**，否则
    会吃掉正常指令。

    消息完全等于组名（`/爱完美`）不算落空：`filter` 那时会抛错列出全部子
    指令，不归这里管，不然两组提示会叠着发。
    """
    if not starts_with_group(message, group):
        # 不是发给我的，放行。别碰别人的指令和普通聊天。
        return False
    arg = leftover_arg(message, group)
    if not arg:
        return False
    return not any(arg.startswith(name) for name in SUBCOMMANDS)


def is_bare_command(message: str, group: str) -> bool:
    """只发了指令组名，一个参数都没带。

    `/爱完美` 以前交给 AstrBot 处理，它回的是「参数不足」加全部子命令和各自的
    docstring——用户看到一大段内部说明，还得自己找能发什么。这里改成回帮助。
    """
    return starts_with_group(message, group) and not leftover_arg(message, group)


def miss_hint(arg: str) -> str:
    """没有子命令匹配时回什么。

    带参数就当用户是想绑定——实测落空绝大多数是这个：打了 id 或链接，以为
    `/爱完美 <id>` 就等于绑定。不带参数就列几个子命令。
    """
    cleaned = (arg or "").strip()
    if not cleaned:
        return "没认出要做什么。全部指令发 /爱完美 帮助。"

    # 参数短就原样带回去让用户复制，太长就只说清楚该怎么做——一整段日志回显
    # 出来没意义
    echo = cleaned if len(cleaned) <= 40 else f"{cleaned[:40]}…"
    return f"「{echo}」不是子命令。要绑定这个号用：/爱完美 绑定 {echo}"
