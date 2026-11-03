#!/usr/bin/env python3
"""Tile downloaded reference images into numbered contact sheets for review.

Usage: python3 contact_sheet.py <images_dir> <out_dir> [per_sheet=20] [cols=5]
"""
import os, sys
from PIL import Image, ImageDraw

src, out = sys.argv[1], sys.argv[2]
per = int(sys.argv[3]) if len(sys.argv) > 3 else 20
cols = int(sys.argv[4]) if len(sys.argv) > 4 else 5
cell = 300
files = sorted(f for f in os.listdir(src) if f.lower().endswith((".jpg", ".png")))
os.makedirs(out, exist_ok=True)
for s in range(0, len(files), per):
    chunk = files[s:s + per]
    rows = (len(chunk) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), "white")
    draw = ImageDraw.Draw(sheet)
    for i, f in enumerate(chunk):
        try:
            im = Image.open(os.path.join(src, f)).convert("RGB")
        except Exception:
            continue
        im.thumbnail((cell - 8, cell - 24))
        x, y = (i % cols) * cell, (i // cols) * cell
        sheet.paste(im, (x + (cell - im.width) // 2, y + 20 + (cell - 24 - im.height) // 2))
        draw.rectangle([x + 2, y + 2, x + 44, y + 18], fill="black")
        draw.text((x + 6, y + 4), os.path.splitext(f)[0], fill="yellow")
    sheet.save(os.path.join(out, f"sheet_{s // per + 1:02d}.jpg"), quality=80)
print("sheets:", (len(files) + per - 1) // per)
