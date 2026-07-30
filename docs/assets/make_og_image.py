#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render the repository social-preview card (docs/assets/og-image.png).

    python docs/assets/make_og_image.py

GitHub shows this at 1280x640 wherever the repo URL is pasted — chat clients,
link unfurls, directory listings. Text is sized to stay legible when that gets
scaled down to a few hundred pixels wide, so there is deliberately little of it.

Fonts are resolved from the system; on a machine without Malgun Gothic pass
--font to point at any Korean-capable TTF.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
BG = (11, 16, 32)
ACCENT = (138, 43, 226)          # the SKILL.md badge purple from the README
WHITE = (255, 255, 255)
GREY = (167, 176, 196)
DIM = (108, 118, 140)
PANEL = (20, 27, 48)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]
BOLD_CANDIDATES = [
    r"C:\Windows\Fonts\malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]
MONO_CANDIDATES = [
    r"C:\Windows\Fonts\consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def pick(candidates, override=None):
    for path in ([override] if override else []) + candidates:
        if path and os.path.exists(path):
            return path
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", help="Korean-capable TTF to use instead of the default")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "og-image.png"))
    args = ap.parse_args()

    regular = pick(FONT_CANDIDATES, args.font)
    bold = pick(BOLD_CANDIDATES, args.font) or regular
    mono = pick(MONO_CANDIDATES) or regular
    if not regular:
        sys.exit("No Korean-capable font found. Pass --font /path/to/font.ttf")

    f_eyebrow = ImageFont.truetype(regular, 22)
    f_title = ImageFont.truetype(bold, 72)
    f_ko = ImageFont.truetype(bold, 39)
    f_en = ImageFont.truetype(regular, 27)
    f_mono = ImageFont.truetype(mono, 25)
    f_foot = ImageFont.truetype(regular, 23)
    f_caught_head = ImageFont.truetype(bold, 24)
    f_caught = ImageFont.truetype(regular, 26)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # accent bar down the left edge
    d.rectangle([0, 0, 12, H], fill=ACCENT)

    x = 78
    d.text((x, 74), "A G E N T   S K I L L   ·   M I T", font=f_eyebrow, fill=DIM)
    d.text((x, 116), "HWPX Editing Skill", font=f_title, fill=WHITE)

    d.rectangle([x, 232, x + 96, 236], fill=ACCENT)

    d.text((x, 274), "한글 .hwpx 파일을 안 깨고 편집한다", font=f_ko, fill=WHITE)
    d.text((x, 330), "Edit Hangul documents without corrupting them —", font=f_en, fill=GREY)
    d.text((x, 366), "byte-identical repack, render-level layout audit.", font=f_en, fill=GREY)

    # what the render audit actually catches — the differentiator, so it earns
    # the right-hand space instead of decoration
    cx = 812
    d.text((cx, 124), "렌더해서 잡는 결함", font=f_caught_head, fill=GREY)
    for i, label in enumerate(["셀 줄바꿈", "빈 페이지", "목차 페이지번호", "글꼴 혼재"]):
        ty = 162 + i * 40
        d.ellipse([cx, ty + 11, cx + 8, ty + 19], fill=ACCENT)
        d.text((cx + 22, ty), label, font=f_caught, fill=DIM)

    # install line, in a panel so it reads as something you type
    panel_top, panel_h = 442, 66
    d.rounded_rectangle([x, panel_top, W - 78, panel_top + panel_h], radius=10, fill=PANEL)
    d.text((x + 24, panel_top + 20), "/plugin install hwpx-editing@kangdacool",
           font=f_mono, fill=(214, 222, 240))

    d.text((x, 552), "Claude Code · Codex · Cursor · Gemini CLI · lxml only",
           font=f_foot, fill=DIM)

    img.save(args.out, "PNG", optimize=True)
    print("wrote", args.out, img.size)


if __name__ == "__main__":
    main()
