"""生成根目录的 logo.png。

源图在 `icon/aiwm-icon.png`，是 1254×1254 的方形徽章。两件事要先处理，
不然圆形裁切后不好看：

1. **徽章要缩到 92%**。AstrBot 的插件列表把图标裁成圆形显示，方形画布上
   贴边的部分会切掉——100% 铺满时皇冠左右两个尖角与底部蓝钻都被削平。
2. **要把源图的方形深蓝底抠掉**。抠掉之后图案四周是透明的，裁成圆形时
   徽章完整，不会露出一圈方形硬边。

背景是深蓝渐变（四角约 RGB(0,18,52)，靠中间偏亮到 (1,30,91)），徽章的
金饰与亮蓝部分亮度远高于背景，所以按亮度设阈值抠。阈值附近留一段过渡带做
软边，硬切会在金饰边缘留锯齿。

规格是 256×256、RGB、无 alpha、PNG 压到几十 KB。WebUI 每次刷新都重新拉
这张图，太大就是纯浪费。

源图是插画性质的图，重采样用 LANCZOS——它对边缘的保持比 NEAREST 好，
缩小后不会一片锯齿。

需要 Pillow，它不在 `requirements.txt` 里（那是给 AstrBot 装的运行时清单）。
换机器后要先 `pip install pillow`：

    python test/做图标.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

仓库根 = Path(__file__).resolve().parent.parent
源图路径 = 仓库根 / "icon" / "aiwm-icon.png"
输出路径 = 仓库根 / "logo.png"

边长 = 256
# 图案占画布的比例。方形徽章按 100% 铺满时皇冠尖角与底部蓝钻会被圆切掉，
# 所以留一点边；但留太多主体就显小，而这张图信息量本就满，再缩就更看不清。
图案占比 = 0.92

# 抠背景的亮度阈值（r+g+b）。源图背景在 53 到 122 之间，而金饰暗面也有
# 150 上下——阈值压到 130 才能既切掉最亮的背景、又不吃掉金饰。
抠图阈值 = 130
过渡带宽 = 45
# 高斯模糊半径，按原图尺寸折算。太小金饰边缘有锯齿，太大徽章会整体发虚。
模糊倍率 = 0.7

画布底色 = (6, 12, 32)


def 抠背景(源: Image.Image) -> Image.Image:
    """把深蓝背景抠成透明，返回带 alpha 的 RGBA 图。

    逐像素算亮度，与阈值比较后映射成 alpha，两端各留一段过渡带做软边。
    模糊半径按原图尺寸折算，所以缩放后软边的粗细看起来一样。
    """
    宽, 高 = 源.size
    带 = Image.new("L", (宽, 高), 0)
    源像素 = 源.load()
    带像素 = 带.load()

    下界 = 抠图阈值 - 过渡带宽
    上界 = 抠图阈值 + 过渡带宽
    for y in range(高):
        for x in range(宽):
            r, g, b = 源像素[x, y][:3]
            亮度 = r + g + b
            if 亮度 <= 下界:
                值 = 0
            elif 亮度 >= 上界:
                值 = 255
            else:
                值 = round((亮度 - 下界) / (上界 - 下界) * 255)
            带像素[x, y] = 值

    带 = 带.filter(ImageFilter.GaussianBlur(宽 / 边长 * 模糊倍率))
    结果 = 源.convert("RGBA")
    结果.putalpha(带)
    return 结果


def 造图标() -> Image.Image:
    源 = Image.open(源图路径).convert("RGB")
    图案 = 抠背景(源)

    边 = round(边长 * (1 - 图案占比) / 2)
    图案边长 = 边长 - 边 * 2
    图案 = 图案.resize((图案边长, 图案边长), Image.LANCZOS)

    画布 = Image.new("RGB", (边长, 边长), 画布底色)
    画布.paste(图案, (边, 边), 图案)
    return 画布


def 主() -> None:
    图 = 造图标()
    # optimize 让 PNG 用最省的压缩方式；256×256 的插画压完通常几十 KB
    图.save(输出路径, format="PNG", optimize=True)
    print(f"{输出路径.relative_to(仓库根)}：{图.size[0]}×{图.size[1]} {图.mode}")
    print(f"{输出路径.stat().st_size} 字节")


if __name__ == "__main__":
    主()
