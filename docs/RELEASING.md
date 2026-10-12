# 发版

AstrBot 插件市场从仓库的 `metadata.yaml` 读插件信息，版本号也在那里。发版
前把 `metadata.yaml` 与 `docs/CHANGELOG.md` 一起改，版本号对不上市场会拒绝
更新。

## 步骤

1. 确认本地干净：`git status` 没有未提交的改动，跑一遍测试与 lint。

   ```sh
   uv run pytest
   uv run ruff check .
   uv run ruff format --check .
   ```

2. 改 `metadata.yaml` 的 `version`。版本号带 `v` 前缀，与 `metadata.yaml`
   现有格式一致。

3. 在 `docs/CHANGELOG.md` 顶部加一节，写清这一版有什么变化。只写当前存在的
   变化，不记录已删除的尝试与此前被否决的方案。

4. 提交。用 Conventional Commit 前缀，一次提交只属于一个类型：

   ```
   release: v0.1.1
   ```

5. 打标签并推送。标签格式 `v*`：

   ```sh
   git tag v0.1.1
   git push origin main --tags
   ```

   推送需要明确要求才执行。

## 兼容性

`astrbot_version` 是插件声明支持的 AstrBot 版本区间，填错了市场会显示不兼容。
当前声明 `>=4.16,<5`，用到的 API（`command_group`、`llm_tool`、`tool_loop_agent`）
都是 4.x 引入的。升到 AstrBot 5 时先确认这些 API 有没有变。

`requirements.txt` 是**手写**的，不要用 `uv export` 生成。原因：

- `uv export` 会把每个包钉成 `==`。AstrBot 装插件时把这份清单喂给 pip，
  而 pip 装在与核心同一的环境里；核心给这些包装了版本护栏，插件若要求精确
  版本，护栏会拦下 pip，安装整体失败。
- 它还会把传递依赖全部展开写进去，而插件只需要声明直接依赖。

加了依赖时**两边一起改**：`pyproject.toml` 的 `dependencies` 与
`requirements.txt`。约束由 `test/test_requirements.py` 钉住，跑测试就能发现
漏改。

`requirements.txt` 的版本下界要与 AstrBot 核心的声明对齐（当前 `aiohttp` 按
核心写 `>=3.11.18`），比 `pyproject.toml` 更严是可以的，更松会让 pip 去动核心
的包。

## 图标

`logo.png` 在仓库根目录，文件名与位置都是 AstrBot 硬编码的（`star_manager.py`
里的 `logo_fname`），不要另建目录。WebUI 通过一个 300 秒有效的文件 token 拉图，
所以体积要小——超过几百 KB 每次刷新都会重传。

规格是 256×256、RGB 无 alpha，与爱农一致。

**改图标改 `icon/aiwm-icon.png`，然后跑 `python test/做图标.py` 重新生成。**
脚本会缩到 92%（让皇冠尖角在圆形裁切下不被切掉）并抠掉源图的方形底。手改
`logo.png` 的话，下次重新生成就被覆盖了。

`test/做图标.py` 需要 Pillow，它不在 `requirements.txt` 里——那是给 AstrBot
装的运行时清单，而做图标是手工操作。

源图 1.8 MB，是开发时用的。**部署与发布包要排掉 `icon/`**，否则装插件时带上
一张用不上的大图。仓库里要留着它，改图标时要用。

## 市场分类

`category` 填市场自己定的那几个中文，「战绩查询」这类归「娱乐」。填错不影响
安装，只是插件详情页的分类标签不对。
