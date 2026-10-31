"""Generate the Dice mascot sprite sheet for the dashboard.

Dice is a chibi salaryman with a d20 for a head. The art is drawn on a native
48x52 pixel grid per frame (the dashboard's `sm` display size) and upscaled 4x
with NEAREST, so every display size stays crisp:

    sheet  = 8 columns x 9 rows of 192x208 frames (1536x1872, transparent)
    rows   = walk, trot, sit, wave, type, gesture, focus, work, read

Frame counts per row match the `@keyframes dice-*` rules in
dashboard/web/src/styles/app.css. Output is lossless WebP. Deterministic: no
randomness, so re-running produces the same file.

Usage:  .venv/bin/python scripts/make_dice_sprite.py [output-path]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image

FW, FH = 48, 52  # native frame size
SCALE = 4  # 48x52 -> 192x208
COLS, ROWS = 8, 9
ROW_ORDER = ["walk", "trot", "sit", "wave", "type", "gesture", "focus", "work", "read"]
FRAME_COUNTS = {
    "walk": 6, "trot": 8, "sit": 8, "wave": 4, "type": 5,
    "gesture": 8, "focus": 6, "work": 6, "read": 6,
}

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "dashboard/static/assets/dice-spritesheet.webp"


def hexc(value: str) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255)


# ---- palette -------------------------------------------------------------
OUTLINE = hexc("#1A1A1A")
CRIMSON = hexc("#C41230")
# d20 facets (lit from the upper left). Centre face is the brand off-white.
DIE_FACE = hexc("#F4F1EA")
DIE_EDGE = hexc("#8E8679")
DIE_SPOKE = hexc("#B3AA9B")
DIE_TL = hexc("#EFEBE2")
DIE_TR = hexc("#E5E0D6")
DIE_L = hexc("#E9E4DA")
DIE_LL = hexc("#DCD6CB")
DIE_R = hexc("#D9D3C7")
DIE_RR = hexc("#C8C1B4")
DIE_B = hexc("#E3DDD2")
DIE_BL = hexc("#D5CEC2")
DIE_BR = hexc("#C1B9AB")
SUIT = hexc("#6E7178")
SUIT_HI = hexc("#878A92")
SUIT_SH = hexc("#565960")
SUIT_DK = hexc("#45474D")
SHIRT = hexc("#FFFFFF")
SHIRT_SH = hexc("#D5D7DD")
TIE = hexc("#242733")
SHOE = hexc("#1F1F22")
SHOE_HI = hexc("#45454B")
SKIN = hexc("#EDC4A3")
SKIN_SH = hexc("#D29E7E")
LAPTOP = hexc("#C9CDD3")
LAPTOP_SH = hexc("#A7ACB4")
LAPTOP_HI = hexc("#E4E7EB")
CASE = hexc("#6B4226")
CASE_HI = hexc("#8A5A36")
CASE_SH = hexc("#4E2F1A")
METAL = hexc("#D8B65A")
PAPER = hexc("#FFFFFF")
PAPER_SH = hexc("#DADCE2")
INK = hexc("#9AA0AA")


# ---- layers --------------------------------------------------------------
class Layer:
    """A part of the figure: a sparse pixel map that gets its own 1px outline."""

    def __init__(self, outline: bool = True):
        self.px: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        self.outline = outline

    def set(self, x: int, y: int, c) -> None:
        self.px[(x, y)] = c

    def rect(self, x0: int, y0: int, x1: int, y1: int, c) -> None:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.px[(x, y)] = c

    def recolor(self, x: int, y: int, c) -> None:
        if (x, y) in self.px:
            self.px[(x, y)] = c

    def line(self, p0, p1, c, w: int = 1) -> None:
        """Bresenham line stamped with a w x w square brush."""
        x0, y0 = p0
        x1, y1 = p1
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        lo = -(w // 2)
        hi = lo + w - 1
        while True:
            self.rect(x0 + lo, y0 + lo, x0 + hi, y0 + hi, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy


def composite(layers: list[Layer]) -> Image.Image:
    img = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    pix = img.load()
    for layer in layers:
        if layer.outline:
            for (x, y) in layer.px:
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if (nx, ny) not in layer.px and 0 <= nx < FW and 0 <= ny < FH:
                        pix[nx, ny] = OUTLINE
        for (x, y), c in layer.px.items():
            if 0 <= x < FW and 0 <= y < FH:
                pix[x, y] = c
    return img


# ---- the d20 head ----------------------------------------------------------
GLYPHS = {
    "2": ["111", "001", "111", "100", "111"],
    "0": ["111", "101", "101", "101", "111"],
}


def _in_tri(p, a, b, c) -> bool:
    def s(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


# Pointy-top hexagon, 23 wide x 25 tall, built from clean 2:1 pixel steps.
HEX_HALF = [1, 3, 5, 7, 9, 11] + [11] * 13 + [11, 9, 7, 5, 3, 1]
HEAD_CX = 11

EYES = True


def head_layer(ox: int, oy: int, blink: bool = False) -> Layer:
    """d20 seen face-on: hexagon silhouette, shaded facets, centre face '20'."""
    L = Layer()
    cx = HEAD_CX
    top, ul, ll = (cx, 0), (0, 5), (0, 19)
    bot, ur, lr = (cx, 24), (22, 5), (22, 19)
    apex, bl, br = (cx, 3), (cx - 7, 17), (cx + 7, 17)
    facets = [
        ((apex, bl, br), DIE_FACE),
        ((apex, top, ul), DIE_TL),
        ((apex, top, ur), DIE_TR),
        ((apex, ul, bl), DIE_L),
        ((ul, ll, bl), DIE_LL),
        ((apex, ur, br), DIE_R),
        ((ur, lr, br), DIE_RR),
        ((bl, br, bot), DIE_B),
        ((bl, ll, bot), DIE_BL),
        ((br, lr, bot), DIE_BR),
    ]
    for r, hw in enumerate(HEX_HALF):
        for x in range(cx - hw, cx + hw + 1):
            col = DIE_LL
            for tri, c in facets:
                if _in_tri((x, r), *tri):
                    col = c
                    break
            L.set(ox + x, oy + r, col)
    # facet edges: the three radial spokes, then the centre face outline
    spokes = Layer(outline=False)
    spokes.line((ox + apex[0], oy + 1), (ox + apex[0], oy + apex[1]), DIE_SPOKE)
    spokes.line((ox + bl[0], oy + bl[1]), (ox + 1, oy + ll[1]), DIE_SPOKE)
    spokes.line((ox + br[0], oy + br[1]), (ox + 21, oy + lr[1]), DIE_SPOKE)
    spokes.line((ox + apex[0], oy + apex[1]), (ox + bl[0], oy + bl[1]), DIE_EDGE)
    spokes.line((ox + apex[0], oy + apex[1]), (ox + br[0], oy + br[1]), DIE_EDGE)
    spokes.line((ox + bl[0], oy + bl[1]), (ox + br[0], oy + br[1]), DIE_EDGE)
    L.px.update(spokes.px)
    # the number, crimson, low in the centre face where it is widest
    nx, ny = ox + cx - 3, oy + 10
    for i, ch in enumerate("20"):
        for gy, row in enumerate(GLYPHS[ch]):
            for gx, bit in enumerate(row):
                if bit == "1":
                    L.set(nx + i * 4 + gx, ny + gy, CRIMSON)
    if EYES:
        for ex in (cx - 3, cx + 3):
            if blink:
                L.set(ox + ex, oy + 20, OUTLINE)
                L.set(ox + ex - 1, oy + 20, OUTLINE)
            else:
                L.set(ox + ex, oy + 19, OUTLINE)
                L.set(ox + ex, oy + 20, OUTLINE)
    return L


# ---- body parts --------------------------------------------------------------
CX = 24  # horizontal centre of the frame
HEAD_TOP = 1
TORSO_TOP = 22  # shoulders tuck under the die's lower slopes
TORSO_H = 15
HIP = TORSO_TOP + TORSO_H  # 37
GROUND = 47  # top row of the shoes when standing


def torso_layer(dy: int) -> Layer:
    L = Layer()
    t = TORSO_TOP + dy
    for y in range(t, t + TORSO_H):
        half = 5 if y == t else 6 if y == t + 1 else 7
        L.rect(CX - half, y, CX + half, y, SUIT)
    for y in range(t + 2, t + TORSO_H):
        L.recolor(CX - 7, y, SUIT_HI)
        L.recolor(CX + 7, y, SUIT_SH)
        L.recolor(CX + 6, y, SUIT_SH)
    # shirt V below the die's tip
    v0 = t + 2
    for i in range(7):
        half = 3 - i // 2
        for x in range(CX - half, CX + half + 1):
            L.recolor(x, v0 + i, SHIRT)
        L.recolor(CX + half, v0 + i, SHIRT_SH)
        # lapels
        L.recolor(CX - half - 1, v0 + i, SUIT_DK)
        L.recolor(CX + half + 1, v0 + i, SUIT_DK)
    # thin tie
    L.rect(CX - 1, v0 + 2, CX + 1, v0 + 2, TIE)
    L.rect(CX, v0 + 3, CX, v0 + 8, TIE)
    L.rect(CX - 1, v0 + 7, CX + 1, v0 + 8, TIE)
    # jacket front: seam, button, hem split
    L.recolor(CX, v0 + 9, SUIT_DK)
    L.recolor(CX + 1, v0 + 9, SUIT_DK)
    L.recolor(CX + 2, v0 + 10, SHIRT_SH)
    for y in range(v0 + 11, t + TORSO_H):
        L.recolor(CX, y, SUIT_DK)
    # pocket flaps
    L.rect(CX - 5, v0 + 10, CX - 3, v0 + 10, SUIT_DK)
    L.rect(CX + 3, v0 + 10, CX + 5, v0 + 10, SUIT_DK)
    return L


def standing_leg(hip_x: int, hip_y: int, foot_x: int, foot_y: int, side: int) -> list[Layer]:
    """Trouser leg from hip to ankle, then a shoe. side=-1 left, +1 right."""
    leg = Layer()
    leg.line((hip_x, hip_y), (foot_x, foot_y - 1), SUIT, w=4)
    rows: dict[int, list[int]] = {}
    for (x, y) in leg.px:
        rows.setdefault(y, []).append(x)
    for y, xs in rows.items():
        leg.px[(min(xs), y)] = SUIT_HI if side < 0 else SUIT
        leg.px[(max(xs), y)] = SUIT_SH
    shoe = Layer()
    sx0 = foot_x - 2 + (-1 if side < 0 else 0)
    sx1 = foot_x + 1 + (0 if side < 0 else 1)
    shoe.rect(sx0, foot_y, sx1, foot_y + 1, SHOE)
    shoe.rect(sx0 + 1, foot_y, sx1 - 1, foot_y, SHOE_HI)
    return [leg, shoe]


def arm(points, hand: str = "fist", sleeve_w: int = 3) -> list[Layer]:
    """Sleeve along a polyline (shoulder -> ... -> wrist), then a hand."""
    sl = Layer()
    for a, b in zip(points, points[1:]):
        sl.line(a, b, SUIT, w=sleeve_w)
    hx, hy = points[-1]
    hd = Layer()
    if hand == "fist":
        hd.rect(hx - 1, hy - 1, hx + 1, hy + 1, SKIN)
        hd.set(hx + 1, hy + 1, SKIN_SH)
    elif hand == "open":  # palm out, fingers up, thumb to the side
        hd.rect(hx - 1, hy - 2, hx + 1, hy + 1, SKIN)
        hd.set(hx - 1, hy - 3, SKIN)
        hd.set(hx + 1, hy - 3, SKIN)
        hd.set(hx + 2, hy, SKIN)
        hd.set(hx + 1, hy + 1, SKIN_SH)
    elif hand == "none":
        return [sl]
    return [sl, hd]


# ---- poses -------------------------------------------------------------------
def standing_legs(dy: int, lift_l: int = 0, lift_r: int = 0):
    hip_y = HIP + dy
    return (
        standing_leg(CX - 3, hip_y, CX - 3, GROUND - lift_l, -1)
        + standing_leg(CX + 3, hip_y, CX + 3, GROUND - lift_r, 1)
    )


SEAT_TOP = 40


def seat() -> list[Layer]:
    """A big off-white d6 to sit on: top face, front face, crimson pips."""
    L = Layer()
    x0, x1 = CX - 12, CX + 12
    L.rect(x0 + 1, SEAT_TOP - 1, x1 - 1, SEAT_TOP + 1, DIE_FACE)
    L.rect(x0, SEAT_TOP + 2, x1, 49, DIE_L)
    L.rect(x1 - 1, SEAT_TOP + 2, x1, 49, DIE_RR)
    L.rect(x0, SEAT_TOP + 2, x1, SEAT_TOP + 2, DIE_EDGE)
    L.rect(x0, 49, x1, 49, DIE_BL)
    for px, py in ((x0 + 2, SEAT_TOP + 5), (x1 - 4, SEAT_TOP + 5)):
        L.rect(px, py, px + 1, py + 1, CRIMSON)
    return [L]


def sitting_legs(swing_l: int = 0, swing_r: int = 0):
    """Seated on the d6: knees toward the viewer, shins down, shoes in front."""
    layers = []
    hip_y = SEAT_TOP + 1
    for side, swing in ((-1, swing_l), (1, swing_r)):
        kx = CX + side * 4
        thigh = Layer()
        thigh.rect(kx - 2, hip_y, kx + 2, hip_y + 2, SUIT)
        thigh.rect(kx - 2, hip_y, kx + 2, hip_y, SUIT_HI)
        shin = Layer()
        shin.rect(kx - 2 + (1 if side > 0 else 0), hip_y + 3, kx + 1 + (1 if side > 0 else 0), hip_y + 5 - swing, SUIT_SH)
        shoe = Layer()
        sy = hip_y + 6 - swing
        shoe.rect(kx - 3, sy, kx + 2 + (1 if side > 0 else 0), sy + 1, SHOE)
        shoe.rect(kx - 2, sy, kx + 1, sy, SHOE_HI)
        layers += [shin, shoe, thigh]
    return layers


SIT_DY = SEAT_TOP + 1 - HIP  # lowers the upper body onto the seat


def shoulder(side: int, dy: int) -> tuple[int, int]:
    return (CX + side * 8, TORSO_TOP + 3 + dy)


def arms_down(dy: int, swing_l: int = 0, swing_r: int = 0):
    """Arms hanging at the sides; swing raises the hand (forward/back read)."""
    l0, r0 = shoulder(-1, dy), shoulder(1, dy)
    left = arm([l0, (l0[0], l0[1] + 5), (l0[0] + (1 if swing_l > 0 else 0), l0[1] + 10 - abs(swing_l))])
    right = arm([r0, (r0[0], r0[1] + 5), (r0[0] - (1 if swing_r > 0 else 0), r0[1] + 10 - abs(swing_r))])
    return left, right


def figure(body_dy: int, legs: list[Layer], front: list[Layer], head_dy: int = 0,
           blink: bool = False, back: list[Layer] | None = None) -> Image.Image:
    head = head_layer(CX - HEAD_CX, HEAD_TOP + body_dy + head_dy, blink)
    return composite((back or []) + legs + [torso_layer(body_dy), head] + front)


def pose_walk(i: int, n: int, trot: bool = False) -> Image.Image:
    s = math.sin(i / n * 2 * math.pi)
    lift = 3 if trot else 2
    lift_l = round(max(0.0, s) * lift)
    lift_r = round(max(0.0, -s) * lift)
    bob = 0 if abs(s) > 0.7 else 1  # dip on the passing frames
    if trot:
        bob = -1 if abs(s) > 0.7 else 1
    swing = round(s * (3 if trot else 2))
    legs = standing_legs(bob, lift_l, lift_r)
    al, ar = arms_down(bob, swing_l=-swing, swing_r=swing)
    return figure(bob, legs, al + ar, blink=(not trot and i == 4))


def pose_sit(i: int) -> Image.Image:
    breathe = 1 if i in (3, 4, 5) else 0
    dy = SIT_DY + breathe
    legs = sitting_legs(1 if i in (1, 2) else 0, 1 if i in (5, 6) else 0)
    l0, r0 = shoulder(-1, dy), shoulder(1, dy)
    al = arm([l0, (l0[0], l0[1] + 5), (CX - 5, SEAT_TOP + 1)])
    ar = arm([r0, (r0[0], r0[1] + 5), (CX + 5, SEAT_TOP + 1)])
    return figure(dy, legs, al + ar, blink=(i == 6), back=seat())


def pose_wave(i: int) -> Image.Image:
    # character's right arm (viewer's left) waves above the head
    hands = [(CX - 16, 12), (CX - 14, 9), (CX - 17, 13), (CX - 14, 9)]
    l0 = shoulder(-1, 0)
    al = arm([l0, (l0[0] - 4, l0[1] - 3), hands[i]], hand="open")
    _, ar = arms_down(0)
    return figure(0, standing_legs(0), al + ar)


def laptop(top_y: int) -> Layer:
    L = Layer()
    x0, x1 = CX - 7, CX + 7
    L.rect(x0, top_y, x1, top_y + 7, LAPTOP)
    L.rect(x0, top_y, x1, top_y, LAPTOP_HI)
    L.rect(x0, top_y + 7, x1, top_y + 7, LAPTOP_SH)
    L.rect(x1, top_y + 1, x1, top_y + 7, LAPTOP_SH)
    L.rect(CX - 1, top_y + 3, CX, top_y + 4, CRIMSON)  # sticker on the lid
    return L


def pose_type(i: int) -> Image.Image:
    dy = SIT_DY
    legs = sitting_legs()
    l0, r0 = shoulder(-1, dy), shoulder(1, dy)
    tap = [(0, 1), (1, 0), (0, 0), (1, 1), (0, 1)][i]
    al = arm([l0, (l0[0], l0[1] + 5), (CX - 7, SEAT_TOP - tap[0])])
    ar = arm([r0, (r0[0], r0[1] + 5), (CX + 7, SEAT_TOP - tap[1])])
    lap = laptop(SEAT_TOP - 8)
    return figure(dy, legs, [lap] + al + ar, head_dy=1 if i == 2 else 0, back=seat())


def pose_gesture(i: int) -> Image.Image:
    bob = 1 if i in (2, 3, 6, 7) else 0
    push = [0, 1, 1, 0, 0, 1, 1, 0][i]
    r0 = shoulder(1, bob)
    ar = arm([r0, (r0[0] + 4, r0[1] + 4), (r0[0] + 9 + push, r0[1] + 1)], hand="open")
    al, _ = arms_down(bob)
    return figure(bob, standing_legs(bob), al + ar, blink=(i == 5))


def thinking_dots(img: Image.Image, n: int) -> None:
    pix = img.load()
    for d in range(n):
        x, y = CX + 14 + d * 3, 4 - d
        for px in range(x - 1, x + 3):
            for py in range(y - 1, y + 3):
                pix[px, py] = OUTLINE
        for px, py in ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)):
            pix[px, py] = DIE_FACE


def pose_focus(i: int) -> Image.Image:
    # right hand (viewer's left) to the chin, other arm folded under its elbow
    l0, r0 = shoulder(-1, 0), shoulder(1, 0)
    lift = 1 if i in (2, 3) else 0
    across = arm([r0, (r0[0], r0[1] + 7), (CX - 5, TORSO_TOP + 10)])
    chin = arm([l0, (CX - 7, TORSO_TOP + 10), (CX - 3, TORSO_TOP + 4 - lift)])
    img = figure(0, standing_legs(0), across + chin, head_dy=-lift)
    thinking_dots(img, [0, 1, 2, 3, 3, 0][i])
    return img


def briefcase(cx: int, top: int) -> list[Layer]:
    L = Layer()
    L.rect(cx - 5, top + 2, cx + 5, top + 8, CASE)
    L.rect(cx - 5, top + 2, cx + 5, top + 2, CASE_HI)
    L.rect(cx - 5, top + 8, cx + 5, top + 8, CASE_SH)
    L.rect(cx - 5, top + 5, cx + 5, top + 5, CASE_SH)
    L.set(cx, top + 5, METAL)
    handle = Layer()
    handle.rect(cx - 2, top, cx + 2, top, CASE_SH)
    handle.set(cx - 2, top + 1, CASE_SH)
    handle.set(cx + 2, top + 1, CASE_SH)
    return [handle, L]


def pose_work(i: int) -> Image.Image:
    s = math.sin(i / 6 * 2 * math.pi)
    lift_l = round(max(0.0, s) * 2)
    lift_r = round(max(0.0, -s) * 2)
    bob = 0 if abs(s) > 0.7 else 1
    legs = standing_legs(bob, lift_l, lift_r)
    al, _ = arms_down(bob, swing_l=round(-s * 2))
    r0 = shoulder(1, bob)
    hand = (r0[0] + 1 + round(s), r0[1] + 10)
    ar = arm([r0, (r0[0], r0[1] + 5), hand])
    return figure(bob, legs, al + briefcase(hand[0] + 1, hand[1] + 1) + ar, blink=(i == 3))


def paper(top: int, line: int) -> Layer:
    L = Layer()
    L.rect(CX - 6, top, CX + 5, top + 11, PAPER)
    L.rect(CX + 5, top + 1, CX + 5, top + 11, PAPER_SH)
    L.rect(CX - 6, top + 11, CX + 5, top + 11, PAPER_SH)
    for k, y in enumerate(range(top + 2, top + 10, 2)):
        L.rect(CX - 4, y, CX - 4 + (7 if k % 2 == 0 else 5), y, INK)
    L.set(CX - 5, top + 2 + 2 * (line % 4), CRIMSON)  # reading marker walks down
    return L


def pose_read(i: int) -> Image.Image:
    bob = 1 if i in (2, 3) else 0
    top = TORSO_TOP + 5 + bob
    l0, r0 = shoulder(-1, 0), shoulder(1, 0)
    al = arm([l0, (l0[0], l0[1] + 6), (CX - 7, top + 5)])
    ar = arm([r0, (r0[0], r0[1] + 6), (CX + 6, top + 5)])
    return figure(0, standing_legs(0), [paper(top, i)] + al + ar, head_dy=1 if i in (3, 4) else 0)


POSES = {
    "walk": lambda i: pose_walk(i, FRAME_COUNTS["walk"]),
    "trot": lambda i: pose_walk(i, FRAME_COUNTS["trot"], trot=True),
    "sit": pose_sit,
    "wave": pose_wave,
    "type": pose_type,
    "gesture": pose_gesture,
    "focus": pose_focus,
    "work": pose_work,
    "read": pose_read,
}


def build_sheet() -> Image.Image:
    native = Image.new("RGBA", (FW * COLS, FH * ROWS), (0, 0, 0, 0))
    for r, state in enumerate(ROW_ORDER):
        for i in range(FRAME_COUNTS[state]):
            native.alpha_composite(POSES[state](i), (i * FW, r * FH))
    return native.resize((native.width * SCALE, native.height * SCALE), Image.NEAREST)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet = build_sheet()
    sheet.save(out, "WEBP", lossless=True, quality=100, method=6)
    print(f"{out} {sheet.width}x{sheet.height}")


if __name__ == "__main__":
    main()
