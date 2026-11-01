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

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO_ROOT / "icon" / "aiwm-icon.png"
OUTPUT_PATH = REPO_ROOT / "logo.png"

side = 256
# 图案占画布的比例。方形徽章按 100% 铺满时皇冠尖角与底部蓝钻会被圆切掉，
# 所以留一点边；但留太多主体就显小，而这张图信息量本就满，再缩就更看不清。
artwork_ratio = 0.92

# 抠背景的亮度阈值（r+g+b）。源图背景在 53 到 122 之间，而金饰暗面也有
# 150 上下——阈值压到 130 才能既切掉最亮的背景、又不吃掉金饰。
cut_threshold = 130
transition_width = 45
# 高斯模糊半径，按原图尺寸折算。太小金饰边缘有锯齿，太大徽章会整体发虚。
blur_factor = 0.7

canvas_bg = (6, 12, 32)


def cut_background(source: Image.Image) -> Image.Image:
    """把深蓝背景抠成透明，返回带 alpha 的 RGBA 图。

    逐像素算亮度，与阈值比较后映射成 alpha，两端各留一段过渡带做软边。
    模糊半径按原图尺寸折算，所以缩放后软边的粗细看起来一样。
    """
    width, height = source.size
    with_ = Image.new("L", (width, height), 0)
    source_pixels = source.load()
    with_pixel = with_.load()

    lower = cut_threshold - transition_width
    upper = cut_threshold + transition_width
    for y in range(height):
        for x in range(width):
            r, g, b = source_pixels[x, y][:3]
            brightness = r + g + b
            if brightness <= lower:
                value = 0
            elif brightness >= upper:
                value = 255
            else:
                value = round((brightness - lower) / (upper - lower) * 255)
            with_pixel[x, y] = value

    with_ = with_.filter(ImageFilter.GaussianBlur(width / side * blur_factor))
    result = source.convert("RGBA")
    result.putalpha(with_)
    return result


def make_icon() -> Image.Image:
    source = Image.open(SOURCE_PATH).convert("RGB")
    artwork = cut_background(source)

    edge = round(side * (1 - artwork_ratio) / 2)
    artwork_side = side - edge * 2
    artwork = artwork.resize((artwork_side, artwork_side), Image.LANCZOS)

    canvas = Image.new("RGB", (side, side), canvas_bg)
    canvas.paste(artwork, (edge, edge), artwork)
    return canvas


def main() -> None:
    image = make_icon()
    # optimize 让 PNG 用最省的压缩方式；256×256 的插画压完通常几十 KB
    image.save(OUTPUT_PATH, format="PNG", optimize=True)
    print(f"{OUTPUT_PATH.relative_to(REPO_ROOT)}：{image.size[0]}×{image.size[1]} {image.mode}")
    print(f"{OUTPUT_PATH.stat().st_size} 字节")


if __name__ == "__main__":
    main()
