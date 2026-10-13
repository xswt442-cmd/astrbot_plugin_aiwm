<div align="center">
  <img src="logo.png" alt="爱完美" width="128">
</div>

# 爱完美

[![AstrBot](https://img.shields.io/badge/AstrBot-插件-4D7AFF)](https://github.com/AstrBotDevs/AstrBot)
[![QQ](https://img.shields.io/badge/QQ-支持-12B7F5?logo=qq&logoColor=white)](https://github.com/AstrBotDevs/AstrBot)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/许可-WTFPL-9CA3AF?logo=open-source-initiative&logoColor=white)](LICENSE)

查 CS2 官方匹配战绩，让模型替你锐评。

AstrBot 插件。绑定一个 SteamID64 就能查战绩，由对话模型给出评价。

## 数据来自哪

`https://api.wmpvp.com/api/csgo/home/official/detailStats`。

域名是完美世界竞技平台的，但**返回的是 CS2 官方匹配（官匹）的数据**，不是
完美平台的对局记录。三条实测证据：

1. 地图池含大量非竞技地图——`de_warden`（恶魔岛）、`de_golden`（黄金之岛）、
   `de_mills`（风情磨坊）、`de_thera`（假日锡拉）不在任何竞技地图池里。
   完美平台的官方比赛地图池（PNL 规则）是荒漠迷城、炙热沙城2、阿努比斯、
   远古遗迹、炼狱小镇、核子危机、死亡游乐园。
2. 请求头里的 `gameType` 传 `1`、`2`、`3`、`1,2` 返回的数据完全一样，服务端
   没按模式区分。
3. `cnt` 恒为 100，`rank` 随账号变——这是 Valve 官匹 API 的形状。

完美自己的战绩在 `appengine.wmpvp.com` 那套接口上，要 accessToken，无凭据
查不到。所以段位是**官匹的分数段**，不是完美平台的段位名。

接口对查询目标不校验身份，所以插件**不需要登录、没有扫码、没有 token**。

## 主要功能

- 绑定一个 SteamID64，只有本人能查自己
- `/爱完美 战绩`：分数段与综合分、胜率、KD、Rating、ADR、KAST、RWS、
  爆头率与首杀率、常用地图、常用武器与击杀分布、多杀次数、最近十场评分
- `/爱完美 锐评`：先给一句称号，再说打得好／问题／建议
- `/爱完美 PK <steamid64 或名字>`：和另一个人比，模型给趣味分并点评胜负手
- `/爱完美 开一局`：推演他下一局的过程与结果
- 每人一份记录，互不可见，解绑即删

ADR（每回合平均伤害）、KAST（每回合有贡献的比例）、RWS（队伍胜率中由该选手
贡献的比例）是 FPS 特有的深度指标，MOB 类游戏没有对应物。术语见
[docs/GLOSSARY.md](docs/GLOSSARY.md)。

## 安装

把仓库放进 AstrBot 的 `data/plugins/` 目录，重载插件。AstrBot 会读取
`requirements.txt` 自动装依赖，需要 Python 3.10 以上。

只依赖 `aiohttp`，不需要额外服务。

也可以在 AstrBot 面板的插件市场里按仓库地址安装。

## 配置

没有配置项。

## 使用

指令都在 `爱完美` 指令组下，不占用通用名字。

```
/爱完美 绑定 <steamid64 或任何含它的内容>    绑定要查的号
/爱完美 战绩                                近期战绩
/爱完美 锐评                                让模型基于近期战绩写一段锐评（带称号）
/爱完美 PK <steamid64 或名字>               和另一个人比一把
/爱完美 开一局                              推演一局
/爱完美 昵称 <名字>                         改 PK 时被叫的名字
/爱完美 状态                                看绑定情况
/爱完美 解绑                                删除本地记录
/爱完美 帮助                                列出全部指令
```

也可以直接用自然语言问，模型会调用本插件提供的工具读取提问者自己的战绩。

`/爱完美 战绩` 给的是分数段与综合分、胜率、KD、Rating、ADR、KAST、RWS、
爆头率与首杀率、常用地图、常用武器与击杀分布、多杀次数、最近十场评分。
接口没返回的维度会直接不显示，不会用 0 充数。

### 绑定时不用自己挑数字

steamid64 是一串 17 位数字、以 7 开头。`/爱完美 绑定` 接受任意内容，会自己从
里面提取，下面这些都能直接粘：

- Steam 个人资料页的网址（`.../profiles/76561198159976336`）
- 启动器参数（`steam.exe -login 76561198159976336`）
- 那串数字本身

找不到时报错会告诉你怎么找。内容里有好几个 id 时会问你发哪个，不瞎猜。

**没有接口能自动取到用户的 steamid64**——所有平台都只支持正向查询，
按账号名反查要 token 且只能查自己，好友码也没有反查端点。所以这里做的是
让用户少抄一串数字，不是加接口。

### 开一局是编的

`/爱完美 开一局` 随机生成一局，再让模型推演过程与结果。**数字全是随机生成的**，
输出第一行会写明这一点——它是娱乐功能，不是战绩查询。

绑定过的话，推演会贴着你的实际水平走（KD、爆头率、段位决定这一局打得像不像
你）；没绑定就按中等水平来。

### 关于 PK

对方**不用绑定**：直接发他的 steamid64 或含它的网址就行。发本机记下的 PK 名字
也行，但对方得先绑定过。

```
/爱完美 昵称 老王
/爱完美 PK 老王
```

**@ 别人这条路走不通。** QQ 官方机器人收不到被 @ 的人的标识（适配器只把
「@机器人」转成消息组件，被 @ 的人在事件里完全没有痕迹），所以只能靠名字点人。
名字默认取绑定时的平台显示名，可以自己改。

## 开发

```sh
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

手工验证整条链路：

```sh
uv run python test/verify_wmpvp.py <steamid64>            # 打印数据与原始响应
uv run python test/verify_wmpvp.py <steamid64> --检查     # 核对字段名与量纲
```

测试用构造的数据。完美平台的接口没有公开文档，字段与量纲随时可能变——改协议
相关代码前先跑 `--检查`，它会报出是哪个字段变了。持续集成里每天也跑一次。

协作约定见 [AGENTS.md](AGENTS.md)，更新日志见 [docs/CHANGELOG.md](docs/CHANGELOG.md)，
术语定义见 [docs/GLOSSARY.md](docs/GLOSSARY.md)，发版流程见
[docs/RELEASING.md](docs/RELEASING.md)。

## License

[WTFPL](LICENSE)。
