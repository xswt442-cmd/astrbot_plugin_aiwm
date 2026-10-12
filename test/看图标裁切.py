"""看一眼图标在圆形裁切下的效果。

AstrBot 的插件列表把图标裁成圆形显示。方形画布上的内容贴着边的部分会切掉，
所以压缩之前得先确认要留哪些。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

原图 = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("icon/aiwm-icon.png")
输出目录 = Path(".workbuddy/icon-preview")

原图路径 = 原图
图 = Image.open(原图路径).convert("RGBA")
宽, 高 = 图.size
print(f"原图 {宽}x{高} {原图路径.stat().st_size} 字节")

输出目录.mkdir(parents=True, exist_ok=True)

# 三种留白比例：100% 铺满、85%、70%。数字越小留白越多，越不容易被圆形切掉。
for 比例, 名 in ((1.0, "满"), (0.85, "八五"), (0.7, "七成")):
    边 = int(min(宽, 高) * (1 - 比例) / 2)
    画布 = Image.new("RGBA", (宽, 高), (0, 0, 0, 0))
    缩放后 = 图.resize((宽 - 边 * 2, 高 - 边 * 2), Image.LANCZOS)
    画布.paste(缩放后, (边, 边))

    # 叠一个圆形遮罩，看裁切后剩什么
    圆形 = Image.new("RGBA", (宽, 高), (0, 0, 0, 0))
    ImageDraw.Draw(圆形).ellipse((0, 0, 宽 - 1, 高 - 1), fill=(255, 255, 255, 255))
    预览 = Image.new("RGBA", (宽, 高), (40, 40, 40, 255))
    预览.alpha_composite(Image.composite(画布, 预览, 圆形.split()[3]))

    路径 = 输出目录 / f"{名}.png"
    预览.convert("RGB").save(路径, optimize=True)
    print(f"  {名}（{比例:.0%}）：{路径}")

# 顺便看一眼缩小到 256 之后的清晰度
小图 = 图.resize((256, 256), Image.LANCZOS)
小图.convert("RGB").save(输出目录 / "256.png", optimize=True, quality=92)
print(f"  256：{输出目录 / '256.png'}")
