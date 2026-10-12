# Agent guide

`aiwm` 是 AstrBot 插件，通过完美世界竞技平台接口读取 CS2 战绩，交给模型。

## 约定

- 包内一律用相对导入。插件目录被 AstrBot 当成包加载，顶层包名在容器里
  import 不到。
- 指令全在 `爱完美` 指令组下（`/爱完美 战绩`），不占用通用名字。改动指令时
  提示文本里的示例要一起改。
- `requirements.txt` **手写**，理由与检查项见 `docs/RELEASING.md`。
- 网络请求只用 `aiohttp`。
- 持久化数据放 AstrBot 的 `data/plugin_data/aiwm/`，不放插件目录。
- 凭据不写日志、不进异常消息、不进提交。解绑时删文件，不保留。
- **改图标改 `icon/aiwm-icon.png` 源图，然后跑 `python test/做图标.py`**，
  不手改 `logo.png`——手改的那份下次重新生成就被覆盖了。脚本里的比例、亮度
  阈值各有注释说明为什么是这个数，规格与发布包的排除项见
  `docs/RELEASING.md`。

## `__init__` 的 config 必须可省

AstrBot 的 `star_manager` 这样注入配置：

```python
if plugin_config and metadata.star_cls_type:
    metadata.star_cls = metadata.star_cls_type(context=self.context, config=plugin_config)
elif metadata.star_cls_type:
    metadata.star_cls = metadata.star_cls_type(context=self.context)
```

`plugin_config` 来自 `_conf_schema.json`。**仓库里没有这个文件时它读不到任何
配置项，那一个 `if` 分支就不走，只传 `context`。** 所以写成
`def __init__(self, context, config)` 会得到
`TypeError: missing 1 required positional argument: 'config'`，插件整个加载
不起来，而本地跑不了 `main.py`，本地也测不出来。

正确写法是 `config: AstrBotConfig | None = None`。

`test/test_main_wiring.py` 里有一条按 AstrBot 的实际调用方式绑定参数，只传
self 与 context——它验的是参数能不能少传，而不只是签名长什么样。改回必需参数
那条会直接抛 TypeError。

**别删 `_conf_schema.json` 却留着必需 config**，也别在没配置文件时留着必需
config。这两条是同一件事的两面。

## 结构

AstrBot 的 `star_manager` 这样注入配置：

```python
if plugin_config and metadata.star_cls_type:
    metadata.star_cls = metadata.star_cls_type(context=self.context, config=plugin_config)
elif metadata.star_cls_type:
    metadata.star_cls = metadata.star_cls_type(context=self.context)
```

`plugin_config` 来自 `_conf_schema.json`。**仓库里没有这个文件时它读不到任何
配置项，那一个 `if` 分支就不走，只传 `context`。** 所以写成
`def __init__(self, context, config)` 会得到
`TypeError: missing 1 required positional argument: 'config'`。

正确写法是 `config: AstrBotConfig | None = None`。

`test/test_main_wiring.py` 里有一条按 AstrBot 的实际调用方式绑定参数，只传
self 与 context——它验的是参数能不能少传，而不只是签名长什么样。改回必需参数
那条会直接抛 TypeError。

**别删 `_conf_schema.json` 却留着必需 config**，也别在没配置文件时留着必需
config。这两条是同一件事的两面。

## 结构

```
main.py             插件入口，指令组与指令
aiwm/transport.py   完美接口的传输层：请求头、业务码
aiwm/battles.py     读战绩的编排：接口响应接上 stats
aiwm/stats.py       战绩统计与文本汇总、逐项对比
aiwm/prompts.py     锐评与 PK 的提示词（放这儿是为了能跑单测）
aiwm/pk.py          PK 对手标识的解析
aiwm/storage.py     绑定记录与 steamid 提取校验
test/               pytest 用例、字段核对规则、手工验证脚本
docs/               更新日志与术语表
```

## 接口的三个必填项

`/api/csgo/home/official/detailStats` 少任何一个都返回
`{"statusCode":14,"errorMessage":"参数错误"}`：

1. 请求头 `gameType: 1,2` 与 `gameTypeStr: 1,2`（表示要 CS:GO 与 CS2 的数据）。
2. 请求头 `t`（秒级时间戳）。
3. 请求体里 `toSteamId` 与 `mySteamId` **两个都填**——只填 `mySteamId` 也报错。

`accessToken` 留空字符串能拿到完整统计。它只影响
`/api/csgo/home/match/list`（完整对局历史分页），不影响主页统计。

**接口不要签名。** 网上流传的 HMAC-SHA256 签名说法经实测证伪，那个私有签名
wheel 只服务赛事 demo 下载，与战绩查询无关。

## 三条只有拿真实响应才能发现的量纲

这三条都是照着字段名想当然、拿真实响应一量就错的。**改协议相关代码前先
`curl` 打一遍，别按名字推断。**

**`kast` 给的是 74 不是 0.74。** 其余比率字段（`winRate` 0.48、
`headShotRatio` 0.547、`entryKillRatio` 0.17）都是 0 到 1 的小数，只有 `kast`
直接给百分数。套同一个换算会输出 KAST 7400%，所以 `stats.py` 为它单开了
`_已是百分数`。

**`cnt` 与 `historyWinCount` 不是同一个池子。** 实测同一个响应里 `cnt` 是
100、`historyWinCount` 是 679，拿后者减前者算负场会得到「负场 0」，而胜率 0.48
反推出来是 48 胜 52 负。所以负场由 `cnt` 乘 `winRate` 算，生涯胜场单列一个
字段。

**`historyRatings` 与 `historyDates` 不是一一对应的。** 实测评分 30 条、日期
100 条——日期覆盖全部场次，评分只有最近 30 场。而且序列里混着 0 与 14 这类
未定级与定级赛的记录，说明它还会跳过那些场次，按索引对齐会配错。所以只取
评分序列本身。

## 取不到就不显示，不许填 0

玩家在完美平台关闭战绩展示时，接口返回的是空壳数据（有昵称，统计全是空的）。
`stats.py` 的 `_取数` 取不到时返回 `None`，由 `汇总文本` 让那一项从文本里
消失，**不能填 0**——0 是合法数据（「爆头率 0%」「这把枪真的没爆头」都可能），
「没有这个字段」不是，混起来模型会把「没这个字段」读成「这项就是 0」，凭空
编出结论。

武器池里的爆头数是这条规则最容易漏的地方：整条武器行要按爆头数有没有来
决定加不加括号，写成「爆头 0」等于说这把枪一个爆头都没有。

新增统计维度时，测试里必须有一条是「缺字段时不出现在文本里」，并且要覆盖到
**每一层**嵌套，不只顶层字段。

## 有没有数据靠返回值判断，不靠文本长相

`main._读战绩` 返回 `(文本, 统计字典)`，没有数据时统计字典是 `None`，调用方
靠这个 `None` 决定能不能继续。

**不要改成靠文本前缀判断。** 玩家关闭战绩展示时 `汇总文本` 返回的是一句
「数据是空的」，它既不以「提问者还没有」也不以「读取战绩失败」开头。锐评提示
要求「全文至少出现 3 个具体数字」，把这句当数据喂进去，模型只能编。

## 段位分里的 0、13、14 不是段位

接口的 `historyRanks` 序列里混着这三种小值（那个号当时段位 20620，序列里却
夹着这三个），它们是未定级与定级赛的标记。照着显示等于告诉模型「这人段位 14
分」。`stats.段位名` 把 1000 分以下的一律显示成「未定级」。

**这三种值各自对应哪个定级赛区间没有依据可查**，所以不编映射。要加更细的档位
得先拿对应分数的真实响应来验。`_段位区间` 的分数阈值同样是从真实响应比对
出来的——完美平台没有公开的段位表文档。

## 绑定只要一个 steamid，没有登录态

完美接口查战绩不校验身份，所以绑定只是记一个 id：没有扫码、没有 token、没有
凭据过期。这是这个插件与同类插件最大的区别，别按需要登录的思路去加。

`steamid64` 的形式是 17 位十进制、首位为 7。`storage.取有效steamid` 在存之前
校验——用户在聊天里手打 steamid，错一位是常事。

**只校验形式，不校验存在。** 前八位 `76561198` 是所有 64 位账号的共同前缀，
第 9 位是账号编号本身，取值本就多样——**不要对中间的数字位做白名单**（写过
一个「第 8 位只能是 0 或 1」的规则，实测那个号第 8 位是 8，直接把真实用户
挡在门外）。格式合法却不存在的号要等接口回应才知道，绑定前的探测就是干这个的。

## 绑定接受任意文本，不要求用户自己挑数字

`取有效steamid` 接受任意内容，从里面正则提取 steamid64。用户手上本来就有含
这串数字的东西——Steam 个人资料页网址、启动器参数、聊天记录里提过的号——让他
自己挑出 17 位抄一遍容易抄错。

正则两侧各留一位边界（`(?<![\d.])` 与 `(?![\d.])`），**别去掉**：18 位数字里截
一段 17 位会得到一个看起来合法、实际是别人的号，小数里也会。这个边界有测试
钉着，去掉会红。

**没有接口能自动取到用户的 steamid64**，别去设计这种功能。实测：

- Steam 官方接口按账号名反查要 access_token，且只能查自己
- 完美平台的好友码（`AG25Z-X7AQ` 这种）没有反查端点，几个候选路径全 404
- 完美平台的 `search/user` 要 token，无凭据报「服务繁忙」

平台没理由开放「任意人 → 任意人的 steamid」，那是隐私。所有平台都只支持正向
查询。所以这条路的正确做法是**让用户少抄一串数字**，不是加接口。

## PK 的对手从消息里捡，再按昵称找

`@` 在多数平台是消息组件，但 QQ 官方平台**只把「@机器人」转成组件**，@别人
会原样留在正文里（`<@!openid>`）。而实测连这一条也不成立——被 @ 的人在事件里
完全没有痕迹，正文里也没有 `<@!id>`。**QQ 官方平台上没有任何办法拿到另一个
用户的标识。**

所以 `main._找对手记录` 有两条路径：先按标识找（`aiwm/pk.py`），再按昵称找
（`storage.按昵称找`）。昵称路径是实际能走通的，必须留着。

昵称路径命中的是**记录**而不是标识，所以查到后直接用记录里的 `steamid`，
不要试图拼一个用户标识出来。

绑定时自动取的 `get_sender_name()` 在 QQ 官方给的是 **QQ 昵称而不是群昵称**，
照那个名字往往点不到人，所以 `/爱完美 昵称` 必须存在，绑定时要提示。

## 对比由代码算，不交给模型

让模型自己比两个人的数据，它最省事的答案就是「各有千秋」。`stats.对比要点`
逐项算清谁占优、双方数字多少，提示词里再写死「不许推翻对比结论」，模型的活
只剩解说。

## 验证

```sh
uv run pytest                    # 测试
uv run ruff check .              # lint
uv run ruff format --check .     # 格式
```

测试只覆盖不需要凭据、不发网络请求的纯逻辑：字段映射、百分数换算、段位名、
对比计算、steamid 校验。

测试用构造的数据，不录真实响应快照。**代价是字段名与量纲没有真实响应兜底**——
接口哪天把 `kast` 从 74 改成 0.74，构造数据照样能过。所以有一条核对：

```sh
uv run python test/verify_wmpvp.py <steamid64>            # 看数据
uv run python test/verify_wmpvp.py <steamid64> --检查     # 核对字段与量纲，退出码表态
```

`--检查` 打真实接口，与 `test/核对规则.py` 里的样例对照：字段在不在、量纲对不对、
数字有没有变字符串、`historyWinCount` 与 `cnt` 的关系还成不成立。退出码 0 表示
对得上，1 表示接口改了字段或量纲（会报出是哪个），2 表示接口打不通。

改协议相关代码时先跑它，拿打印的字段核对 `test/test_stats.py` 的 `_完整响应`
再改实现。**顺序不能反**：接口改版时照着旧断言改实现，容易把错误当成新行为。

核对规则本身由 `test/test_verify_rules.py` 覆盖，包括「接口改版时它会不会报出来」
——把 `核对规则.核对` 改成永远返回空列表，那批用例会全红。

持续集成里每天跑一次这条。它只在一个 steamid 上跑，那个号是公开的，
数据不写进任何地方。

## 文档

只写中文。`README.md` 说明安装与配置，术语在 `docs/GLOSSARY.md`。

提交用 Conventional Commit 前缀，一次提交一个类型，推送与分支操作需要明确要求。
发版流程在 `docs/RELEASING.md`；改版本号时 `metadata.yaml` 与 `docs/CHANGELOG.md`
要一起改。
