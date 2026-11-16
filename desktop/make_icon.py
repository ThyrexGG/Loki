"""Generate Loki's logo and app icons: a two-headed Norse serpent coiled into an S.

Inspired by Urnes-style knotwork serpents (Jormungandr, Loki's child): a double-outlined band
filled with triangle / spiral / scale ornament, sharp dorsal spines, wolf-dragon heads, and two
gold strands that weave over and under the body in a figure-8 knot through the middle.

The serpent has 180-degree rotational symmetry around (50, 50): only the top half of the body
centre-line and one strand are defined; the rest is the same geometry rotated. All geometry is
sampled into polylines in Python so ornament, offsets and interlace crossings can be computed.

Outputs:
    static/loki-logo.svg  - detailed mark, transparent background (welcome screen, 88 px)
    static/loki-mark.svg  - simplified mark, transparent background (sidebar, chat avatar)
    static/loki.png       - 192 px favicon on tile
    desktop/loki.ico      - Windows icon (detailed art for >= 48 px, simplified art below)

Rasterises the SVG with Microsoft Edge headless (no new dependencies) and packs the .ico with Pillow:
    python desktop\\make_icon.py            # write assets
    python desktop\\make_icon.py <dir>      # previews only
"""
from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
CX, CY = 50.0, 50.0  # centre of rotational symmetry

INK = "#06080d"
HEAD_SCALE = 0.86
BONE = "#f3e6bf"

# Top half of the body centre-line, from the top head's neck to the centre (cubic Bezier segments).
HALF = [
    ((72, 25), (79, 16), (65, 6.5), (49, 6.5)),
    ((49, 6.5), (32, 6.5), (22, 17), (24.5, 29.5)),
    ((24.5, 29.5), (27, 41), (40, 46), (50, 50)),
]

# Gold strand trailing from behind the top head; its twin is the 180-degree rotation.
STRAND = [
    ((64, 36), (56, 42), (41, 41), (36, 33)),
    ((36, 33), (31, 25), (39, 15), (47, 19)),
    ((47, 19), (54, 23), (51, 37), (47, 48)),
    ((47, 48), (43, 59), (50, 68), (58, 72)),
    ((58, 72), (66, 76), (65, 86), (57, 85)),
    ((57, 85), (52, 84), (52, 78), (56, 78.5)),
]


# ----------------------------------------------------------------------------- geometry helpers
def rot(p):
    return (2 * CX - p[0], 2 * CY - p[1])


def bez(seg, t):
    p0, p1, p2, p3 = seg
    u = 1 - t
    return tuple(u**3 * p0[i] + 3 * u * u * t * p1[i] + 3 * u * t * t * p2[i] + t**3 * p3[i] for i in range(2))


def sample(segs, n=60):
    """Bezier list -> dense polyline."""
    pts = [segs[0][0]]
    for s in segs:
        pts += [bez(s, k / n) for k in range(1, n + 1)]
    return pts


class Line:
    """Polyline with arc-length parameterisation, tangents and normals."""

    def __init__(self, pts):
        self.p = pts
        self.s = [0.0]
        for a, b in zip(pts, pts[1:]):
            self.s.append(self.s[-1] + math.dist(a, b))
        self.L = self.s[-1]

    def at(self, s):
        """Point, unit tangent, unit normal (left of travel) at arc length s."""
        s = max(0.0, min(self.L, s))
        lo, hi = 0, len(self.s) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.s[mid] <= s:
                lo = mid
            else:
                hi = mid
        a, b = self.p[lo], self.p[hi]
        seg = self.s[hi] - self.s[lo] or 1e-9
        f = (s - self.s[lo]) / seg
        x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        tx, ty = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
        return (x, y), (tx, ty), (ty, -tx)

    def local(self, s, u, v):
        """Point at arc length s + u along the tangent, offset v along the normal."""
        (x, y), (tx, ty), (nx, ny) = self.at(s)
        return (x + tx * u + nx * v, y + ty * u + ny * v)

    def offset(self, v, s0=0.0, s1=None, step=0.5):
        s1 = self.L if s1 is None else s1
        n = max(2, int((s1 - s0) / step))
        return [self.local(s0 + (s1 - s0) * k / n, 0, v) for k in range(n + 1)]

    def sub(self, s0, s1, step=0.4):
        return self.offset(0, max(0, s0), min(self.L, s1), step)


def crossings(a: Line, b: Line):
    """Arc lengths (sa, sb, sin_angle) where polylines a and b intersect."""
    out = []
    for i in range(len(a.p) - 1):
        p, q = a.p[i], a.p[i + 1]
        for j in range(len(b.p) - 1):
            r, t = b.p[j], b.p[j + 1]
            d1 = (q[0] - p[0], q[1] - p[1])
            d2 = (t[0] - r[0], t[1] - r[1])
            den = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(den) < 1e-12:
                continue
            w = (r[0] - p[0], r[1] - p[1])
            u = (w[0] * d2[1] - w[1] * d2[0]) / den
            v = (w[0] * d1[1] - w[1] * d1[0]) / den
            if 0 <= u < 1 and 0 <= v < 1:
                la, lb = math.dist(p, q), math.dist(r, t)
                sin = abs(den) / (la * lb)
                out.append((a.s[i] + u * la, b.s[j] + v * lb, sin))
    return out


def pd(pts, close=False):
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    return d + (" Z" if close else "")


def path(d, **attrs):
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<path d="{d}" {a}/>'


# ----------------------------------------------------------------------------- body ornament
def ornament(body: Line, w: float, s0: float, s1: float) -> str:
    """Triangle, spiral and scale zones inside the inner channel of the band, between s0 and s1."""
    c = w - 1.55  # inner channel half-width
    zones = [("tri", 11.0), ("spiral", 8.0), ("scale", 9.0), ("spiral", 8.0)]
    dark, light, gold, lines = [], [], [], []
    s, zi = s0, 0
    while s < s1:
        kind, length = zones[zi % len(zones)]
        e = min(s1, s + length)
        # divider: two cross bars
        for off in (0.0, 0.9):
            lines.append(pd([body.local(s + off, 0, -c), body.local(s + off, 0, c)]))
        a, b = s + 1.6, e - 0.7
        if b - a > 2:
            if kind == "tri":
                n = max(2, round((b - a) / 2.3))
                cell = (b - a) / n
                for k in range(n):
                    x0 = a + k * cell
                    # dark triangle hanging from one edge, light one rising from the other
                    dark.append(pd([body.local(x0, 0, c), body.local(x0 + cell, 0, c), body.local(x0 + cell / 2, 0, -c * 0.15)], True))
                    light.append(pd([body.local(x0 + cell / 2, 0, -c), body.local(x0 + cell * 1.5 if k < n - 1 else x0 + cell, 0, -c),
                                     body.local(x0 + cell, 0, c * 0.15)], True) if k < n - 1 else "")
                    # small inner notch triangle for the double-ink look
                    dark.append(pd([body.local(x0 + cell * 0.5, 0, -c), body.local(x0 + cell, 0, -c * 0.35),
                                    body.local(x0 + cell * 1.5, 0, -c)], True) if k < n - 1 else "")
            elif kind == "spiral":
                n = max(1, round((b - a) / (2 * c + 0.6)))
                cell = (b - a) / n
                for k in range(n):
                    m = a + cell * (k + 0.5)
                    r0 = c * 0.82
                    pts = []
                    turns = 1.75
                    for q in range(0, 61):
                        th = q / 60 * turns * 2 * math.pi
                        r = r0 * (1 - q / 60 * 0.85)
                        pts.append(body.local(m, r * math.cos(th + k * math.pi), r * math.sin(th + k * math.pi)))
                    gold.append(pd(pts))
                    if k < n - 1:  # tiny triangles between spirals
                        x = a + cell * (k + 1)
                        dark.append(pd([body.local(x - 0.8, 0, c), body.local(x + 0.8, 0, c), body.local(x, 0, c - 1.4)], True))
                        dark.append(pd([body.local(x - 0.8, 0, -c), body.local(x + 0.8, 0, -c), body.local(x, 0, -c + 1.4)], True))
            else:  # scales: two offset rows of arcs
                rows = 2
                h = 2 * c / rows
                for r_ in range(rows):
                    v0 = -c + h * r_
                    n = max(2, round((b - a) / 2.0))
                    cell = (b - a) / n
                    shift = cell / 2 if r_ % 2 else 0
                    for k in range(n):
                        x0 = a + k * cell + shift
                        if x0 + cell > b + 0.01:
                            continue
                        pts = [body.local(x0 + cell / 2 - cell / 2 * math.cos(th), 0, v0 + h * math.sin(th) * 0.95)
                               for th in [i / 12 * math.pi for i in range(13)]]
                        lines.append(pd(pts))
        s, zi = e, zi + 1
    out = []
    out.append(path(" ".join(x for x in light if x), fill="#7ef0c4", fill_opacity="0.55"))
    out.append(path(" ".join(x for x in dark if x), fill=INK, fill_opacity="0.78"))
    out.append(path(" ".join(lines), fill="none", stroke=INK, stroke_width="0.42", stroke_linecap="round", stroke_opacity="0.9"))
    out.append(path(" ".join(gold), fill="none", stroke=INK, stroke_width="1.15", stroke_linecap="round"))
    out.append(path(" ".join(gold), fill="none", stroke="url(#gold)", stroke_width="0.5", stroke_linecap="round"))
    return "".join(out)


def chevrons(body: Line, w: float, s0: float, s1: float, gap: float = 4.2) -> str:
    """Minimal band ornament: a sparse row of chevrons pointing along the body."""
    c = w - 1.9
    out = []
    n = int((s1 - s0) / gap)
    for k in range(n + 1):
        m = s0 + k * gap
        out.append(pd([body.local(m - 1.1, 0, -c), body.local(m + 0.9, 0, 0), body.local(m - 1.1, 0, c)]))
    return path(" ".join(out), fill="none", stroke=INK, stroke_opacity="0.55", stroke_width="0.7",
                stroke_linecap="round", stroke_linejoin="round")


# ----------------------------------------------------------------------------- spines
def spines(body: Line, w: float, s0: float, s1: float, n: int, length: float, side: int, simple: bool) -> str:
    """Sharp, slightly back-swept dorsal spines on one side of the band."""
    out = []
    for k in range(n):
        s = s0 + (s1 - s0) * (k + 0.5) / n
        # taper spine length towards the ends of the run
        f = math.sin(math.pi * (k + 0.5) / n) ** 0.5
        L = length * (0.55 + 0.45 * f)
        bw = 2.2 if not simple else 2.6
        base = w - 0.8
        a = body.local(s - bw, 0, side * base)
        b = body.local(s + bw, 0, side * base)
        tip = body.local(s - L * 0.38, 0, side * (base + L))
        c1 = body.local(s - bw * 0.2 - L * 0.08, 0, side * (base + L * 0.55))
        c2 = body.local(s + bw * 0.4 - L * 0.2, 0, side * (base + L * 0.6))
        out.append(f"M{a[0]:.2f},{a[1]:.2f} Q{c1[0]:.2f},{c1[1]:.2f} {tip[0]:.2f},{tip[1]:.2f} "
                   f"Q{c2[0]:.2f},{c2[1]:.2f} {b[0]:.2f},{b[1]:.2f} Z")
    return " ".join(out)


# ----------------------------------------------------------------------------- head
# Wolf-dragon head facing +x, neck centred on the origin; y < 0 is the skull side.
MANE = (
    "M2,-6 C-2,-8.5 -6,-10 -12,-10.6 C-6,-12.4 0,-11.6 4.6,-9.6 "
    "C2.6,-13 -0.4,-15.6 -5,-17.6 C2.6,-17 8,-14 10.6,-9.6 L9,-7 Z"
)
UPPER = (
    "M0,-6.4 C3.5,-7.4 7,-9.8 11.5,-10.2 C15,-10.5 17,-8.4 19.5,-7.4 "     # skull, brow
    "C22.5,-6.5 26,-6.6 28.4,-6 C30.6,-5.4 31,-3 29.4,-2 "                 # snout ridge, tip
    "L27.6,-1.2 C23,-1.2 17,-0.9 11.6,0.2 C8,0.9 4,1.4 0,1.6 Z"            # upper lip back to neck
)
LOWER = (
    "M0,1.4 C4,1.6 8,1.3 11.6,0.4 C16.5,2.2 21,3.8 25.6,5 "               # mouth corner, lower lip
    "C27.4,5.5 27.2,7.3 25.4,7.6 C20,8.6 14,8.6 9,8.2 C5.5,7.9 2.6,7.4 0,6.6 Z"
)
UPPER_TEETH = [(20.5, -0.9), (24.6, -1.1)]
LOWER_TEETH = [(22.6, 4.4)]
SNOUT_CURL = "M28.6,-5.8 C31.6,-7.6 32.4,-11.4 29.6,-12.4 C27.4,-13.1 26,-11 27.4,-9.8 C28.3,-9.1 29.2,-9.9 28.8,-10.6"
CHIN_CURL = "M25.8,7.4 C27.8,8.6 28,11.2 26,11.6 C24.6,11.9 24,10.4 25,9.9"
NOSTRIL = "M25.4,-4.6 C26.6,-5.6 27.9,-4.8 27.2,-3.8 C26.7,-3.2 25.9,-3.6 26.2,-4.2"
EYE = "M11.6,-5.6 C13,-7.6 16.2,-7.8 18,-5.8 C16.4,-4.6 13.4,-4.4 11.6,-5.6 Z"
BROW = "M10,-8.2 C13,-10.4 17.4,-10 20.4,-7.2"
CHEEK = "M4.2,-1.8 C4.2,-4.6 8,-4.8 8.4,-2.6 C8.7,-1 6.6,-0.4 6,-1.6 C5.6,-2.4 6.6,-3 7,-2.4"
JAW_LINE = "M3,5 C9,5.8 16,5.8 23.6,6.2"
TONGUE = "M12,1 C17,2.4 21,3 25,3.3 C26.6,3.4 27.8,2.6 28.8,1.8 M25,3.3 C26.4,4 27.4,4.8 28,6"


def teeth(points, up):
    out = []
    for i, (x, y) in enumerate(points):
        h = 1.6 + 0.25 * i
        if i == len(points) - 1:
            h += 0.9  # fang
        tip = y - h if up else y + h
        out.append(f"M{x - 0.75:.2f},{y:.2f} L{x + 0.15:.2f},{tip:.2f} L{x + 0.85:.2f},{y:.2f} Z")
    return " ".join(out)


def head_group(anchor, angle_deg, flip, detail):
    sy = -1 if flip else 1
    t = f"translate({anchor[0]:.2f} {anchor[1]:.2f}) rotate({angle_deg:.2f}) scale({HEAD_SCALE} {HEAD_SCALE * sy})"
    sw = 1.0
    g = []
    if detail:
        g.append(path(MANE, fill="url(#spine)", stroke=INK, stroke_width=sw, stroke_linejoin="round"))
        g.append(path(LOWER, fill="url(#head)", stroke=INK, stroke_width=sw, stroke_linejoin="round"))
        g.append(path(teeth(LOWER_TEETH, True), fill=BONE, stroke=INK, stroke_width="0.35", stroke_linejoin="round"))
        g.append(path(teeth(UPPER_TEETH, False), fill=BONE, stroke=INK, stroke_width="0.35", stroke_linejoin="round"))
        g.append(path(UPPER, fill="url(#head)", stroke=INK, stroke_width=sw, stroke_linejoin="round"))
        for d, wdt in ((SNOUT_CURL, 2.2),):
            g.append(path(d, fill="none", stroke=INK, stroke_width=wdt, stroke_linecap="round"))
            g.append(path(d, fill="none", stroke="url(#gold)", stroke_width=wdt - 1.1, stroke_linecap="round"))
        g.append(path(NOSTRIL, fill="none", stroke=INK, stroke_width="0.6", stroke_linecap="round"))
        g.append(path(BROW, fill="none", stroke=INK, stroke_width="0.9", stroke_linecap="round"))
        g.append(path(EYE, fill="#f6d77a", stroke=INK, stroke_width="0.6"))
        g.append('<ellipse cx="14.8" cy="-5.9" rx="0.55" ry="1.3" fill="#06080d"/>')
    else:
        g.append(path("M1,-5.6 L-6,-15 L6,-9 Z", fill="url(#gold)", stroke=INK, stroke_width="1.4", stroke_linejoin="round"))
        g.append(path(LOWER, fill="url(#head)", stroke=INK, stroke_width="1.4", stroke_linejoin="round"))
        g.append(path(UPPER, fill="url(#head)", stroke=INK, stroke_width="1.4", stroke_linejoin="round"))
        g.append('<ellipse cx="15" cy="-5.4" rx="2.6" ry="1.6" fill="#f6d77a" stroke="#06080d" stroke-width="0.6"/>')
    return f'<g transform="{t}">{"".join(g)}</g>'


# ----------------------------------------------------------------------------- strands / interlace
def strand_stroke(pts, wide=2.5, core=1.1, cap="round"):
    """Gold strand with ink edges. Over-pieces use butt caps so their ends blend into the strand below."""
    d = pd(pts)
    return (path(d, fill="none", stroke=INK, stroke_width=wide, stroke_linecap=cap, stroke_linejoin="round")
            + path(d, fill="none", stroke="url(#gold)", stroke_width=core, stroke_linecap=cap, stroke_linejoin="round"))


def build_svg(size: int, tile: bool, detail: bool) -> str:
    body_segs = HALF + [tuple(rot(p) for p in reversed(seg)) for seg in reversed(HALF)]
    body = Line(sample(body_segs))
    w = 6.0 if detail else 7.4
    d_body = pd(body.p)
    rot180 = f"rotate(180 {CX} {CY})"

    # spines along the outside of the top bowl (and, rotated, the bottom bowl)
    half_len = body.L / 2
    spine_d = spines(body, w, half_len * 0.10, half_len * 0.72, 8 if detail else 6, 7.2 if detail else 6.8, -1, not detail)
    spine_svg = (path(spine_d, fill="url(#spine)", stroke=INK, stroke_width="0.9" if detail else "1.3", stroke_linejoin="round")
                 + path(spine_d, fill="url(#spine)", stroke=INK, stroke_width="0.9" if detail else "1.3", stroke_linejoin="round",
                        transform=rot180))

    # body band: ink outline, gradient fill, double inner outline
    band = (path(d_body, fill="none", stroke=INK, stroke_width=f"{2 * w + 2.4:.2f}", stroke_linecap="round")
            + path(d_body, fill="none", stroke="url(#body)", stroke_width=f"{2 * w:.2f}", stroke_linecap="round"))
    if detail:
        inner = w - 1.55
        band += path(pd(body.offset(inner)) + " " + pd(body.offset(-inner)), fill="none", stroke=INK, stroke_opacity="0.75", stroke_width="0.5")
        band += chevrons(body, w, 6.0, body.L - 6.0)
    else:
        band += path(d_body, fill="none", stroke=INK, stroke_opacity="0.55", stroke_width="1.2",
                     stroke_dasharray="0.01 3.2", stroke_linecap="round")

    # heads at both ends, pointing back along the curve into the bowls
    (p0, t0, _) = body.at(0)
    ang = math.degrees(math.atan2(-t0[1], -t0[0]))
    head_top = head_group(p0, ang, flip=False, detail=detail)
    head_bot = f'<g transform="{rot180}">{head_top}</g>'

    strands_under = strands_over = ""
    if detail:
        a = Line(sample(STRAND, 80))
        b = Line([rot(p) for p in a.p])
        under = [strand_stroke(a.p), strand_stroke(b.p)]
        over = []
        # strand / body crossings alternate over-under along each strand
        for ln in (a, b):
            xs = sorted(crossings(ln, body))
            for i, (sa, _sb, sin) in enumerate(xs):
                if i % 2 == 0:
                    half = (w + 2.2) / max(sin, 0.35)
                    over.append(strand_stroke(ln.sub(sa - half, sa + half), cap="butt"))
        # strand / strand crossings: a goes over b at its first crossing, under at the next
        for i, (sa, sb, sin) in enumerate(sorted(crossings(a, b))):
            top, s = (a, sa) if i % 2 == 0 else (b, sb)
            half = 3.2 / max(sin, 0.35)
            over.append(strand_stroke(top.sub(s - half, s + half), cap="butt"))
        strands_under, strands_over = "".join(under), "".join(over)

    scale = 0.86 if detail else 0.9
    bg = ""
    if tile:
        bg = ('<rect x="0" y="0" width="100" height="100" rx="22" fill="url(#tile)"/>'
              '<rect x="0.75" y="0.75" width="98.5" height="98.5" rx="21.3" fill="none" stroke="#ffffff" stroke-opacity="0.07" stroke-width="1.5"/>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}">
<defs>
  <linearGradient id="body" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#34d399"/><stop offset="0.48" stop-color="#10a37f"/><stop offset="1" stop-color="#6366f1"/>
  </linearGradient>
  <linearGradient id="head" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#10a37f"/><stop offset="1" stop-color="#34d399"/>
  </linearGradient>
  <linearGradient id="spine" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#2bc08f"/><stop offset="1" stop-color="#4f55d8"/>
  </linearGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#f6d77a"/><stop offset="1" stop-color="#c99a3b"/>
  </linearGradient>
  <linearGradient id="tile" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#151b26"/><stop offset="1" stop-color="#0a0d14"/>
  </linearGradient>
</defs>
{bg}<g transform="translate(50 50) scale({scale}) translate(-50 -50)">{strands_under}{spine_svg}{band}{strands_over}{head_top}{head_bot}</g>
</svg>'''


# ----------------------------------------------------------------------------- rasterising
def render(svg: str, px: int, out: Path) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "icon.html"
        src.write_text(f'<html><body style="margin:0;background:transparent">{svg}</body></html>', encoding="utf-8")
        shot = Path(tmp) / "shot.png"
        subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--default-background-color=00000000", f"--window-size={px},{px}",
                        f"--user-data-dir={Path(tmp) / 'prof'}", f"--screenshot={shot}", src.as_uri()],
                       check=True, capture_output=True, timeout=60)
        img = Image.open(shot).convert("RGBA").crop((0, 0, px, px))
    img.save(out)
    return img


if __name__ == "__main__":
    import sys
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if out_dir:  # preview mode
        out_dir.mkdir(parents=True, exist_ok=True)
        detail = render(build_svg(512, True, True), 512, out_dir / "preview_detail.png")
        simple = render(build_svg(512, True, False), 512, out_dir / "preview_simple.png")
        (out_dir / "preview_detail.svg").write_text(build_svg(512, True, True), encoding="utf-8")
        # strip of small sizes: simplified 16/24/32, detailed 48/64/88
        sizes = [(16, simple), (24, simple), (32, simple), (48, detail), (64, detail), (88, detail)]
        strip = Image.new("RGBA", (sum(s for s, _ in sizes) + 10 * len(sizes) + 10, 98), (40, 44, 52, 255))
        x = 10
        for s, src in sizes:
            strip.alpha_composite(src.resize((s, s), Image.LANCZOS), (x, 5))
            x += s + 10
        strip.resize((strip.width * 4, strip.height * 4), Image.NEAREST).save(out_dir / "preview_small.png")
        print("previews written to", out_dir)
    else:
        (ROOT / "static" / "loki-logo.svg").write_text(build_svg(96, False, True), encoding="utf-8")
        (ROOT / "static" / "loki-mark.svg").write_text(build_svg(32, False, False), encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            big = render(build_svg(512, True, True), 512, Path(tmp) / "big.png")
            small = render(build_svg(256, True, False), 256, Path(tmp) / "small.png")
            big.resize((192, 192), Image.LANCZOS).save(ROOT / "static" / "loki.png")
            frames = [(s, big if s >= 48 else small) for s in (16, 24, 32, 48, 64, 128, 256)]
            imgs = [src.resize((s, s), Image.LANCZOS) for s, src in frames]
            imgs[-1].save(ROOT / "desktop" / "loki.ico", format="ICO", sizes=[(s, s) for s, _ in frames],
                          append_images=imgs[:-1])
        print("wrote static/loki-logo.svg, static/loki-mark.svg, static/loki.png, desktop/loki.ico")
