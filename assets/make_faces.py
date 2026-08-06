#!/usr/bin/env python3
"""BMO face designer.

Draws BMO's Adventure Time screen-face (the classic teal game console with a
mint screen plate) as 1024x1024 RGBA PNGs, with cute cartoon expressions.
Soft mint backdrop so it blends with the app window. Run from assets/:

  python3 make_faces.py
"""

import os

from PIL import Image, ImageDraw

SIZE = 1024

# BMO's show palette
BG = (210, 245, 220, 255)         # soft mint backdrop
BEZEL = (56, 168, 146, 255)       # BMO's teal console bezel ring
SCREEN = (226, 250, 240, 255)     # pale mint screen plate
INK = (36, 40, 44, 255)           # cartoon-safe near-black for eyes/mouth
EYE = (40, 44, 52, 255)
BLUSH = (252, 178, 178, 235)      # soft pink cheeks
WHITE = (255, 255, 255, 255)
LOVE = (244, 96, 116, 255)        # heart red

# screen plate (the face area)
PLATE = (96, 150, SIZE - 96, SIZE - 150)
R = 150

EYE_SEP = int(SIZE * 0.085)
EYE_Y = int(SIZE * 0.34)


def _canvas():
    im = Image.new("RGBA", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(im)
    # teal console body edge (bezel) behind the screen plate
    d.rounded_rectangle([PLATE[0] - 26, PLATE[1] - 26, PLATE[2] + 26, PLATE[3] + 26],
                        radius=R + 14, fill=BEZEL)
    # screen plate
    d.rounded_rectangle(PLATE, radius=R, fill=SCREEN)
    d.rounded_rectangle([PLATE[0] + 12, PLATE[1] + 12, PLATE[2] - 12, PLATE[3] - 12],
                        radius=R - 12, outline=(214, 246, 234, 255), width=3)
    return im, d


def _eye(d, cx, cy, rx, ry):
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=EYE)
    d.ellipse([cx - rx * 0.52, cy - ry * 0.62, cx - rx * 0.1, cy - ry * 0.12],
              fill=WHITE)


def _eyes(d, rx=62, ry=78, blink=None):
    for i in (0, 1):
        cx = int(SIZE * 0.5 + (1 if i else -1) * EYE_SEP)
        if blink == i:
            d.line([cx - rx, EYE_Y, cx + rx, EYE_Y - ry * 0.18], fill=INK, width=16)
        else:
            _eye(d, cx, EYE_Y, rx, ry)


def _cheeks(d):
    for sx in (0.19, 0.81):
        d.ellipse([SIZE * sx - 48, SIZE * 0.58 - 32, SIZE * sx + 48, SIZE * 0.58 + 32],
                  fill=BLUSH)


def _smile(d, box=None):
    box = box or [SIZE * 0.32, SIZE * 0.46, SIZE * 0.68, SIZE * 0.62]
    d.arc(box, start=22, end=158, fill=INK, width=16)


def _laugh(d):
    d.chord([SIZE * 0.28, SIZE * 0.52, SIZE * 0.72, SIZE * 0.76], 0, 180, fill=INK)
    d.ellipse([SIZE * 0.70, SIZE * 0.48, SIZE * 0.76, SIZE * 0.58], fill=INK)


def _surprise(d):
    d.ellipse([SIZE * 0.34, SIZE * 0.44, SIZE * 0.66, SIZE * 0.60], outline=INK, width=12)
    d.ellipse([SIZE * 0.345, SIZE * 0.45, SIZE * 0.655, SIZE * 0.59], fill=INK)


def _heart(d, cx, cy, s):
    d.polygon([(cx, cy + s), (cx - s, cy - s + s * 0.5),
               (cx, cy - s * 0.3), (cx + s, cy - s + s * 0.5)],
              fill=LOVE)


def _save(im, name):
    im.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), name))
    print("wrote", name)


def happy():
    im, d = _canvas()
    _eyes(d)
    _cheeks(d)
    _smile(d)
    _save(im, "face_happy.png")


def wink():
    im, d = _canvas()
    _eyes(d, blink=0)
    _cheeks(d)
    _smile(d, [SIZE * 0.34, SIZE * 0.48, SIZE * 0.72, SIZE * 0.64])
    _save(im, "face_wink.png")


def wow():
    im, d = _canvas()
    _eyes(d, rx=78, ry=96)
    _screwbal(d)
    _save(im, "face_wow.png")


def _screwbal(d):
    d.arc([SIZE * 0.08, SIZE * 0.56, SIZE * 0.92, SIZE * 0.84], 185, 355,
          fill=INK, width=14)


def laugh():
    im, d = _canvas()
    _eyes(d, rx=56, ry=70)
    _cheeks(d)
    _laugh(d)
    _save(im, "face_laugh.png")


def love():
    im, d = _canvas()
    for i in (0, 1):
        cx = int(SIZE * 0.5 + (1 if i else -1) * EYE_SEP)
        _heart(d, cx, EYE_Y, int(56 * 1.5))
    _cheeks(d)
    _smile(d)
    _save(im, "face_love.png")


def sleepy():
    im, d = _canvas()
    for i in (0, 1):
        cx = int(SIZE * 0.5 + (1 if i else -1) * EYE_SEP)
        d.line([cx - 55, EYE_Y, cx + 55, EYE_Y], fill=INK, width=13)
    _smile(d)
    _save(im, "face_sleepy.png")


def normal():
    im, d = _canvas()
    _eyes(d)
    _smile(d)
    _save(im, "face_normal.png")


def main():
    for fn in (happy, wink, wow, laugh, love, sleepy, normal):
        fn()


if __name__ == "__main__":
    main()