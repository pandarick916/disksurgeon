#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""纯代码画专家头像：32x32 像素网格 → NEAREST 放大 16 倍 = 512x512。

风格：古早街机（吃豆人那一代）。
主体：张着嘴的黄色吃豆人，正咬住一张「文件」——带折角和文字行的纸。

逐像素决定颜色，不用任何矢量/抗锯齿 —— 放大后边缘是硬的，才是真像素画。
"""
import math
import os

from PIL import Image

N = 32
SCALE = 16

BG = (6, 8, 14)
YEL = (255, 205, 0)
PAPER = (228, 241, 251)          # 纸张
PAPER_EDGE = (122, 152, 178)     # 纸的边
FOLD = (168, 198, 222)           # 折角背面
LINE = (26, 138, 168)            # 纸上的字（青，呼应「数据」）
INK = (12, 14, 22)

CX, CY = 12.2, 16.0              # 圆心
R = 11.4                         # 半径
MOUTH = 45.0                     # 嘴半角（度）

# 文件：竖着的纸，左边缘探进嘴里
FX, FY, FW, FH = 15, 11, 7, 10


def main():
    img = [[BG] * N for _ in range(N)]
    body = [[False] * N for _ in range(N)]

    # ── 先画文件（后面身体会压上来，才有「被咬住」的感觉）──────
    for y in range(FY, FY + FH):
        for x in range(FX, FX + FW):
            img[y][x] = PAPER
    for x in range(FX, FX + FW):                 # 上下描边
        img[FY][x] = PAPER_EDGE
        img[FY + FH - 1][x] = PAPER_EDGE
    for y in range(FY, FY + FH):                 # 只描右边：左边要伸进嘴里，不画边
        img[y][FX + FW - 1] = PAPER_EDGE
    # 纸上的三行字：右端长短不一，才像字，不像进度条
    for y, cut in ((FY + 3, 1), (FY + 5, 2), (FY + 7, 1)):
        for x in range(FX + 1, FX + FW - cut):
            img[y][x] = LINE

    # ── 吃豆人：圆 - 楔形嘴（画在文件之上，压住纸的左边两角）───
    for y in range(N):
        for x in range(N):
            dx, dy = x + 0.5 - CX, y + 0.5 - CY
            if math.hypot(dx, dy) > R:
                continue
            ang = math.degrees(math.atan2(dy, dx))     # 0 = 正右
            if abs(ang) < MOUTH:                       # 嘴：向右开口
                continue
            body[y][x] = True
            img[y][x] = YEL

    # 眼睛
    for yy in (8, 9):
        for xx in (9, 10):
            if body[yy][xx]:
                img[yy][xx] = INK

    # ── 居中：按「着墨范围」对齐，不靠手调圆心 ──────────────
    # 手调过一次，图形整块偏左、右边空一大片。BBox 居中才可靠。
    xs = [x for y in range(N) for x in range(N) if img[y][x] != BG]
    ys = [y for y in range(N) for x in range(N) if img[y][x] != BG]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    dx = round((N - (x1 - x0 + 1)) / 2) - x0
    dy = round((N - (y1 - y0 + 1)) / 2) - y0
    if dx or dy:
        moved = [[BG] * N for _ in range(N)]
        for y in range(N):
            for x in range(N):
                if img[y][x] == BG:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < N and 0 <= ny < N:
                    moved[ny][nx] = img[y][x]
        img = moved

    # ── 放大：NEAREST，保住硬边 ─────────────────────
    out = Image.new("RGB", (N, N))
    out.putdata([tuple(img[y][x]) for y in range(N) for x in range(N)])
    return out, out.resize((N * SCALE, N * SCALE), Image.NEAREST)


if __name__ == "__main__":
    _small, big = main()
    here = os.path.dirname(os.path.abspath(__file__))
    dst = os.path.join(os.path.dirname(here), "avatars", "pacman.png")
    big.save(dst)
    print("✓ %s  (%dx%d)" % (dst, big.size[0], big.size[1]))
