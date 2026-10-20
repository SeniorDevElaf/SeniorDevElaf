#!/usr/bin/env python3
"""Build the animated SVGs for the profile README.

    python3 scripts/build.py                  every static asset into assets/
    python3 scripts/build.py stats --out dist the activity card only (run daily by the Action)

Stdlib only. Each SVG is a self contained dark card: system fonts, no external
resources, animated with CSS and SMIL, both of which keep running when GitHub
serves the file through an <img>. Visible text never uses a dash.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import random
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER = "SeniorDevElaf"

VIOLET, PINK, CYAN, GREEN, AMBER = "#8B5CF6", "#EC4899", "#06B6D4", "#22C55E", "#F59E0B"
TINT = {VIOLET: "#C4B5FD", PINK: "#F9A8D4", CYAN: "#67E8F9", GREEN: "#86EFAC", AMBER: "#FCD34D"}
TEXT, MUTED, DIM, LINE, PANEL = "#E6EDF3", "#9BA3B4", "#5B6478", "#222B3D", "#0F1524"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
MONO_W = 0.6  # advance of one monospace glyph in em; text that has to line up also gets textLength

BASE_CSS = (
    f".s{{font-family:{SANS}}}.m{{font-family:{MONO}}}"
    ".blink{animation:blink 1.05s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
    ".comet{animation:comet 8s linear infinite}"
    "@keyframes comet{from{stroke-dashoffset:1000}to{stroke-dashoffset:0}}"
    ".pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.6s ease-out infinite}"
    "@keyframes pulse{from{transform:scale(1);opacity:.7}to{transform:scale(2.3);opacity:0}}"
    ".rise{animation:rise .9s cubic-bezier(.2,.8,.2,1) both}"
    "@keyframes rise{from{opacity:0;transform:translateY(14px)}}"
    ".pop{transform-box:fill-box;transform-origin:center;animation:pop .7s cubic-bezier(.3,1.6,.5,1) both}"
    "@keyframes pop{from{opacity:0;transform:scale(0)}}"
    "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
)

# 24px line icons, drawn with stroke="currentColor"-style attributes set by the caller.
ICONS = {
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "layout": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "trend": '<path d="M22 7l-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
    "truck": '<path d="M2 5h12v10H2z"/><path d="M14 9h4l3 3v3h-7"/><circle cx="6" cy="17.5" r="2"/><circle cx="17" cy="17.5" r="2"/>',
    "receipt": '<path d="M5 2v20l2.5-1.5L10 22l2-1.5 2 1.5 2.5-1.5L19 22V2l-2.5 1.5L14 2l-2 1.5L10 2 7.5 3.5z"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    "bank": '<path d="M3 21h18"/><path d="M5 21V11M9.5 21V11M14.5 21V11M19 21V11"/><path d="M2 9l10-6 10 6z"/>',
    "message": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "cloud": '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9z"/>',
    "cpu": '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
    "mic": '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1"/><path d="M12 18v4M8 22h8"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/>',
    "route": '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
    "gamepad": '<path d="M6 11h4M8 9v4M15 12h.01M18 10h.01"/><path d="M17.32 5H6.68a4 4 0 0 0-3.98 3.59l-.9 7.9A3 3 0 0 0 4.8 20a3 3 0 0 0 2.13-.88L9 17h6l2.07 2.12A3 3 0 0 0 19.2 20a3 3 0 0 0 3-3.51l-.9-7.9A4 4 0 0 0 17.32 5z"/>',
    "parking": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 17V7h4a3 3 0 0 1 0 6H9"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 6L2 7"/>',
    "linkedin": '<rect x="2" y="2" width="20" height="20" rx="4"/><path d="M8 10.5v6M8 7.5v.01M12 16.5v-6M12 13a2.5 2.5 0 0 1 5 0v3.5"/>',
}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def n(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def text_width(s: str, size: float, bold: bool = False) -> float:
    """Rough advance width of proportional sans text, good enough to size pills."""
    w = 0.0
    for c in s:
        if c == " ":
            w += 0.28
        elif c in "iljI.,:;'!|":
            w += 0.27
        elif c in "ftr()[]":
            w += 0.36
        elif c in "mwMW":
            w += 0.85
        elif c.isupper() or c in "+&%@":
            w += 0.66
        elif c.isdigit():
            w += 0.58
        else:
            w += 0.54
    return w * size * (1.06 if bold else 1)


def icon(name: str, x: float, y: float, color: str, scale: float = 1.0, width: float = 1.8) -> str:
    return (
        f'<g transform="translate({n(x)},{n(y)}) scale({n(scale)})" fill="none" stroke="{color}" '
        f'stroke-width="{n(width)}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>'
    )


def rr_path(x: float, y: float, w: float, h: float, r: float) -> str:
    """Rounded rect as a path, so pathLength works in every browser."""
    return (
        f"M{n(x + r)},{n(y)}H{n(x + w - r)}A{n(r)},{n(r)} 0 0 1 {n(x + w)},{n(y + r)}"
        f"V{n(y + h - r)}A{n(r)},{n(r)} 0 0 1 {n(x + w - r)},{n(y + h)}"
        f"H{n(x + r)}A{n(r)},{n(r)} 0 0 1 {n(x)},{n(y + h - r)}V{n(y + r)}A{n(r)},{n(r)} 0 0 1 {n(x + r)},{n(y)}Z"
    )


def comet(d: str, color: str, dur: float = 8, delay: float = 0) -> str:
    """A spark of light running around a border: faint tail plus a bright head."""
    common = (
        f'd="{d}" pathLength="1000" fill="none" stroke="{color}" stroke-linecap="round" class="comet" '
        f'style="animation-duration:{n(dur)}s;animation-delay:-{n(delay)}s"'
    )
    return (
        f'<path {common} stroke-width="5" stroke-opacity=".18" stroke-dasharray="160 840"/>'
        f'<path {common} stroke-width="2" stroke-dasharray="0 90 70 840"/>'
    )


def svg(w: int, h: int, label: str, body: str, css: str = "", defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{esc(label)}"><title>{esc(label)}</title>'
        f"<style>{BASE_CSS}{css}</style><defs>{defs}</defs>{body}</svg>\n"
    )


def card(w: int, h: int, label: str, body: str, css: str = "", defs: str = "", r: float = 20,
         comet_color: str | None = None, comet_delay: float = 0) -> str:
    """Dark rounded card with a faint dot grid and a gradient edge; body is clipped to it."""
    defs = (
        f'<clipPath id="clip"><rect width="{w}" height="{h}" rx="{n(r)}"/></clipPath>'
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#090D17"/>'
        '<stop offset="1" stop-color="#0E1323"/></linearGradient>'
        f'<linearGradient id="edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".6"/>'
        f'<stop offset=".5" stop-color="{LINE}"/><stop offset="1" stop-color="{CYAN}" stop-opacity=".5"/></linearGradient>'
        '<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
        '<circle cx="2" cy="2" r="1" fill="#fff" fill-opacity=".06"/></pattern>' + defs
    )
    edge = rr_path(0.75, 0.75, w - 1.5, h - 1.5, r - 0.75)
    out = (
        f'<g clip-path="url(#clip)"><rect width="{w}" height="{h}" fill="url(#bg)"/>'
        f'<rect width="{w}" height="{h}" fill="url(#dots)"/>{body}</g>'
        f'<path d="{edge}" fill="none" stroke="url(#edge)" stroke-width="1.5"/>'
    )
    if comet_color:
        out += comet(edge, comet_color, delay=comet_delay)
    return svg(w, h, label, out, css, defs)


def discrete(attr: str, events: list[tuple[float, float]], total: float) -> str:
    """SMIL step animation of one attribute through (time, value) events over a looping cycle."""
    events = sorted(events)
    if events[0][0] > 0:
        events.insert(0, (0.0, events[0][1]))
    times = ";".join(f"{min(t / total, 1):.4f}" for t, _ in events)
    values = ";".join(n(v) for _, v in events)
    return (
        f'<animate attributeName="{attr}" values="{values}" keyTimes="{times}" calcMode="discrete" '
        f'dur="{n(total)}s" repeatCount="indefinite"/>'
    )


# ---------------------------------------------------------------- hero


def typing(phrases: list[str], x: float, y: float, size: float, uid: str = "ty",
           cps: float = 14, hold: float = 1.9, dcps: float = 45, gap: float = 0.35) -> tuple[str, str]:
    """Cycle through phrases, typing and deleting each, with a cursor that follows."""
    cw = size * MONO_W
    px = x + 2 * cw
    slots, t = [], 0.0
    for p in phrases:
        slots.append((t, p))
        t += len(p) / cps + hold + len(p) / dcps + gap
    total = t
    defs, texts, cursor = [], [], [(0.0, 0.0)]
    for i, (start, p) in enumerate(slots):
        k = len(p)
        ev = [(0.0, 0.0)]
        ev += [(start + c / cps, c) for c in range(1, k + 1)]
        ev += [(start + k / cps + hold + c / dcps, k - c) for c in range(1, k + 1)]
        cursor += ev[1:]
        widths = [(tt, c * cw) for tt, c in ev]
        defs.append(
            f'<clipPath id="{uid}{i}"><rect x="{n(px)}" y="{n(y - size)}" height="{n(size * 1.45)}" width="0">'
            f"{discrete('width', widths, total)}</rect></clipPath>"
        )
        texts.append(
            f'<text x="{n(px)}" y="{n(y)}" textLength="{n(k * cw)}" lengthAdjust="spacing" '
            f'clip-path="url(#{uid}{i})">{esc(p)}</text>'
        )
    body = (
        f'<g class="m" font-size="{n(size)}"><text x="{n(x)}" y="{n(y)}" fill="{PINK}">❯</text>'
        f'<g fill="{TEXT}">{"".join(texts)}</g>'
        f'<g class="blink"><rect x="{n(px)}" y="{n(y - size * 0.8)}" width="{n(cw * 0.55)}" '
        f'height="{n(size * 1.02)}" rx="1.5" fill="{CYAN}">'
        f"{discrete('x', [(tt, px + c * cw) for tt, c in cursor], total)}</rect></g></g>"
    )
    return "".join(defs), body


def orbit(cx: float, cy: float, rx: float, k: float, phi: float, dur: float,
          nodes: list[tuple[float, str, str]], reverse: bool = False, dashed: bool = False) -> str:
    """Pills riding a tilted ellipse while staying upright and unsquashed.

    The chain rotate(phi) scale(1,k) rotate(a) spin translate(rx) unspin rotate(-a) scale(1,1/k)
    rotate(-phi) cancels to the identity, so only the position travels along the ellipse.
    """
    style = f"animation-duration:{n(dur)}s" + (";animation-direction:reverse" if reverse else "")

    def depth(ang: float) -> str:
        # Phase the shared depth keyframes so they start at this node's angle.
        lag = dur * (1 - ang / 360) if reverse else dur * ang / 360
        return f'{style};animation-delay:-{n(lag)}s'

    ring = (
        f'<ellipse cx="{n(cx)}" cy="{n(cy)}" rx="{n(rx)}" ry="{n(rx * k)}" transform="rotate({n(phi)} {n(cx)} {n(cy)})" '
        f'fill="none" stroke="url(#ring)" stroke-width="1.2"' + (' stroke-dasharray="3 6"' if dashed else "") + "/>"
    )
    items = []
    for ang, label, color in nodes:
        if label:
            tw = len(label) * 12.5 * MONO_W
            w = tw + 34
            inner = (
                f'<rect x="{n(-w / 2)}" y="-14" width="{n(w)}" height="28" rx="14" fill="{PANEL}" '
                f'stroke="{color}" stroke-opacity=".8"/><circle cx="{n(-w / 2 + 14)}" cy="0" r="3.2" fill="{color}"/>'
                f'<text x="{n(-w / 2 + 24)}" y="4.4" class="m" font-size="12.5" fill="{TEXT}" '
                f'textLength="{n(tw)}" lengthAdjust="spacing">{esc(label)}</text>'
            )
        else:
            inner = f'<circle r="7" fill="{color}" fill-opacity=".25"/><circle r="3" fill="{color}"/>'
        items.append(
            f'<g transform="rotate({n(ang)})"><g class="spin" style="{style}"><g transform="translate({n(rx)},0)">'
            f'<g class="unspin" style="{style}"><g transform="rotate({n(-ang)}) scale(1,{n(1 / k)}) rotate({n(-phi)})">'
            f'<g class="depth" style="{depth(ang)}">{inner}</g></g></g></g></g></g>'
        )
    return ring + f'<g transform="translate({n(cx)},{n(cy)}) rotate({n(phi)}) scale(1,{n(k)})">{"".join(items)}</g>'


def hero() -> str:
    W, H = 1000, 380
    rnd = random.Random(11)
    stars = "".join(
        f'<circle class="tw" cx="{rnd.uniform(8, W - 8):.0f}" cy="{rnd.uniform(8, H - 8):.0f}" '
        f'r="{rnd.uniform(0.5, 1.5):.1f}" style="animation-delay:-{rnd.uniform(0, 6):.1f}s;'
        f'animation-duration:{rnd.uniform(3, 6.5):.1f}s"/>'
        for _ in range(60)
    )
    phrases = [
        "Software Engineer in clean energy",
        "Full stack: Python, TypeScript, GCP",
        "Shipping with AI agents every day",
        "450+ pull requests merged in 2026",
    ]
    tdefs, tbody = typing(phrases, 60, 244, 22)
    pill_text = "NOW BUILDING SOFTWARE FOR CLEAN ENERGY"
    pill_tw = len(pill_text) * (12 * MONO_W + 1.4)
    cx, cy = 775, 192
    defs = (
        tdefs
        + "".join(
            f'<radialGradient id="g{k}"><stop offset="0" stop-color="{c}" stop-opacity="{o}"/>'
            f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient>'
            for k, c, o in (("v", VIOLET, ".55"), ("p", PINK, ".38"), ("c", CYAN, ".32"))
        )
        + f'<linearGradient id="nm" x1="0" y1="0" x2=".5" y2="0" spreadMethod="repeat">'
        f'<stop offset="0" stop-color="{TINT[VIOLET]}"/><stop offset=".33" stop-color="{PINK}"/>'
        f'<stop offset=".66" stop-color="{CYAN}"/><stop offset="1" stop-color="{TINT[VIOLET]}"/>'
        '<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to=".5 0" '
        'dur="6s" repeatCount="indefinite"/></linearGradient>'
        f'<linearGradient id="ring" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".55"/>'
        f'<stop offset="1" stop-color="{CYAN}" stop-opacity=".25"/></linearGradient>'
        f'<radialGradient id="core" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="{TINT[VIOLET]}"/>'
        f'<stop offset=".45" stop-color="{VIOLET}"/><stop offset="1" stop-color="#9D174D"/></radialGradient>'
        '<linearGradient id="shoot" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#fff"/></linearGradient>'
    )
    css = (
        ".tw{fill:#fff;fill-opacity:.5;animation:tw 4s ease-in-out infinite}"
        "@keyframes tw{0%,100%{opacity:.15}50%{opacity:1}}"
        ".d1{animation:d1 18s ease-in-out infinite}@keyframes d1{50%{transform:translate(150px,60px)}}"
        ".d2{animation:d2 22s ease-in-out infinite}@keyframes d2{50%{transform:translate(-170px,-60px)}}"
        ".d3{animation:d3 26s ease-in-out infinite}@keyframes d3{50%{transform:translate(-90px,100px)}}"
        ".spin{animation:spin 40s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}"
        ".unspin{animation:unspin 40s linear infinite}@keyframes unspin{to{transform:rotate(-360deg)}}"
        # Nodes on the near half of an orbit (sin > 0, lower on screen) grow and brighten.
        ".depth{animation:depth 40s linear infinite}@keyframes depth{"
        + "".join(
            f"{p}%{{opacity:{0.42 + 0.58 * (1 + math.sin(math.radians(3.6 * p))) / 2:.2f};"
            f"transform:scale({0.82 + 0.2 * (1 + math.sin(math.radians(3.6 * p))) / 2:.3f})}}"
            for p in range(0, 101, 10)
        )
        + "}"
        ".turn{transform-box:fill-box;transform-origin:center;animation:spin 24s linear infinite}"
        ".breathe{transform-box:fill-box;transform-origin:center;animation:breathe 5s ease-in-out infinite}"
        "@keyframes breathe{50%{transform:scale(1.12);opacity:.75}}"
        ".shoot{opacity:0;animation:shoot 9s ease-out infinite 2s}"
        "@keyframes shoot{0%{opacity:0;transform:translate(40px,10px)}2%{opacity:1}"
        "10%{opacity:0;transform:translate(560px,190px)}100%{opacity:0;transform:translate(560px,190px)}}"
    )
    left = (
        f'<g class="rise" style="animation-delay:.1s">'
        f'<rect x="60" y="42" width="{n(pill_tw + 46)}" height="30" rx="15" fill="{GREEN}" fill-opacity=".1" '
        f'stroke="{GREEN}" stroke-opacity=".4"/>'
        f'<circle cx="80" cy="57" r="4" fill="{GREEN}"/><circle class="pulse" cx="80" cy="57" r="4" fill="none" '
        f'stroke="{GREEN}" stroke-width="1.5"/>'
        f'<text x="94" y="61.5" class="m" font-size="12" letter-spacing="1.4" fill="{TINT[GREEN]}" '
        f'textLength="{n(pill_tw)}" lengthAdjust="spacing">{pill_text}</text></g>'
        f'<text class="s rise" style="animation-delay:.25s" x="62" y="122" font-size="21" fill="{MUTED}">Hi there, I\'m</text>'
        f'<text class="s rise" style="animation-delay:.4s" x="58" y="190" font-size="70" font-weight="800" '
        f'letter-spacing="-1.5" fill="url(#nm)">Elaf Alzoubi</text>'
        f'<g class="rise" style="animation-delay:.6s">{tbody}</g>'
        f'<g class="s rise" style="animation-delay:.8s" font-size="16.5" fill="{MUTED}">'
        f'<text x="61" y="290">I turn messy, real world operations into clean,</text>'
        f'<text x="61" y="314">automated software that teams rely on every day.</text></g>'
        f'<text class="m rise" style="animation-delay:1s" x="61" y="352" font-size="11.5" letter-spacing="2.2" '
        f'fill="{DIM}">STOCKHOLM, SWEDEN   59.33°N  18.07°E</text>'
    )
    core = (
        f'<circle class="breathe" cx="{cx}" cy="{cy}" r="120" fill="url(#gv)"/>'
        + orbit(cx, cy, 64, 0.5, 8, 14, [(0, "", CYAN), (120, "", PINK), (240, "", GREEN)], dashed=True)
        + f'<circle class="pulse" cx="{cx}" cy="{cy}" r="40" fill="none" stroke="{PINK}" stroke-width="1.5"/>'
        f'<circle class="pulse" cx="{cx}" cy="{cy}" r="40" fill="none" stroke="{VIOLET}" stroke-width="1.5" '
        f'style="animation-delay:1.3s"/>'
        f'<circle class="turn" cx="{cx}" cy="{cy}" r="52" fill="none" stroke="{CYAN}" stroke-opacity=".6" '
        f'stroke-dasharray="2 7"/>'
        f'<circle cx="{cx}" cy="{cy}" r="40" fill="url(#core)"/>'
        f'<text x="{cx}" y="{cy + 9}" class="s" font-size="25" font-weight="800" fill="#fff" text-anchor="middle" '
        f'letter-spacing="1">EA</text>'
        + orbit(cx, cy, 116, 0.42, 24, 26, [(30, "Claude Code", PINK), (210, "TypeScript", CYAN)], reverse=True)
        + orbit(cx, cy, 150, 0.36, -14, 40, [(0, "FastAPI", GREEN), (90, "Next.js", TEXT),
                                            (180, "Google Cloud", AMBER), (270, "PostgreSQL", VIOLET)])
    )
    body = (
        f'<circle class="d1" cx="190" cy="30" r="290" fill="url(#gv)"/>'
        f'<circle class="d2" cx="880" cy="340" r="300" fill="url(#gp)"/>'
        f'<circle class="d3" cx="600" cy="-30" r="240" fill="url(#gc)"/>'
        f"{stars}"
        '<g class="shoot"><line x1="0" y1="0" x2="110" y2="36" stroke="url(#shoot)" stroke-width="1.8" '
        'stroke-linecap="round"/></g>'
        f"{core}{left}"
    )
    return card(W, H, "Elaf Alzoubi, Software Engineer in Stockholm", body, css, defs, r=22,
                comet_color=VIOLET)


# ---------------------------------------------------------------- terminal


def terminal() -> str:
    W, H = 1000, 352
    size, lh, x0, y0 = 17, 30, 30, 88
    cw = size * MONO_W
    script = [
        ("cmd", "whoami"),
        ("out", [("Elaf Alzoubi", TINT[CYAN], True), ("  ·  ", MUTED, False), ("Software Engineer", TEXT, True),
                 ("  ·  clean energy  ·  Stockholm", MUTED, False)]),
        ("cmd", "cat now.txt"),
        ("out", [("◆ ", VIOLET, False), ("Building ", TEXT, False), ("Atlas", TINT[VIOLET], True),
                 (", the ops platform for heat pump, solar and battery installs", TEXT, False)]),
        ("out", [("◆ ", PINK, False), ("Automating supplier orders, invoicing and bank payments end to end", TEXT, False)]),
        ("out", [("◆ ", CYAN, False), ("Shipping daily with AI agents that plan, test, review and release", TEXT, False)]),
        ("cmd", "cat shipped.txt"),
        ("out", [("✔ ", GREEN, False), ("450+", TINT[GREEN], True),
                 (" pull requests merged in 2026 across 6 repos", TEXT, False)]),
        ("cmd", ""),
    ]
    total = 16.0
    t = 0.4
    defs, lines = [], []
    cursor_x, cursor_y, cursor_on = [(0.0, x0 + 2 * cw)], [(0.0, y0 - size * 0.8)], [(0.0, 0.0)]
    for i, (kind, payload) in enumerate(script):
        y = y0 + i * lh
        appear = (
            f'<animate attributeName="opacity" values="0;0;1;1" keyTimes="0;{t / total:.4f};'
            f'{(t + 0.25) / total:.4f};1" dur="{n(total)}s" repeatCount="indefinite"/>'
        )
        if kind == "cmd":
            lines.append(f'<text x="{x0}" y="{y}" fill="{PINK}" opacity="0">❯{appear}</text>')
            cursor_x.append((t, x0 + 2 * cw))
            cursor_y.append((t, y - size * 0.8))
            cursor_on.append((t, 1))
            k = len(payload)
            if k:
                start = t + 0.35
                ev = [(0.0, 0.0)] + [(start + c / 13, c * cw) for c in range(1, k + 1)]
                defs.append(
                    f'<clipPath id="c{i}"><rect x="{n(x0 + 2 * cw)}" y="{n(y - size)}" height="{n(size * 1.45)}" '
                    f'width="0">{discrete("width", ev, total)}</rect></clipPath>'
                )
                lines.append(
                    f'<text x="{n(x0 + 2 * cw)}" y="{y}" fill="{TEXT}" textLength="{n(k * cw)}" lengthAdjust="spacing" '
                    f'clip-path="url(#c{i})">{esc(payload)}</text>'
                )
                cursor_x += [(start + c / 13, x0 + (2 + c) * cw) for c in range(1, k + 1)]
                t = start + k / 13 + 0.3
                cursor_on.append((t, 0))
                t += 0.15
        else:
            chars = sum(len(s) for s, _, _ in payload)
            spans = "".join(
                f'<tspan fill="{c}"' + (' font-weight="700"' if b else "") + f">{esc(s)}</tspan>" for s, c, b in payload
            )
            lines.append(
                f'<text x="{x0}" y="{y}" xml:space="preserve" textLength="{n(chars * cw)}" lengthAdjust="spacing" '
                f'opacity="0">{spans}{appear}</text>'
            )
            t += 0.4
    cursor = (
        f'<g class="blink"><rect width="{n(cw * 0.6)}" height="{n(size * 1.05)}" rx="1.5" fill="{CYAN}">'
        f'{discrete("x", cursor_x, total)}{discrete("y", cursor_y, total)}{discrete("opacity", cursor_on, total)}'
        "</rect></g>"
    )
    fade = (
        f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;{(total - 0.8) / total:.4f};'
        f'{(total - 0.25) / total:.4f};1" dur="{n(total)}s" repeatCount="indefinite"/>'
    )
    title = "elaf@stockholm: ~/now"
    body = (
        f'<rect width="{W}" height="46" fill="#111726"/><rect y="46" width="{W}" height="1" fill="{LINE}"/>'
        '<circle cx="26" cy="23" r="6.5" fill="#FF5F57"/><circle cx="48" cy="23" r="6.5" fill="#FEBC2E"/>'
        '<circle cx="70" cy="23" r="6.5" fill="#28C840"/>'
        f'<text x="{W / 2}" y="28" class="m" font-size="13" fill="{MUTED}" text-anchor="middle">{esc(title)}</text>'
        f'<g class="m" font-size="{size}">{"".join(lines)}{cursor}{fade}</g>'
    )
    return card(W, H, "What Elaf is working on now", body, defs="".join(defs), r=16)


# ---------------------------------------------------------------- system map


def system() -> str:
    W, H = 1000, 528
    nw, nh, gap, top = 250, 70, 22, 64
    ys = [top + i * (nh + gap) for i in range(4)]
    core_cx, core_cy = 500, ys[0] + (ys[3] - ys[0]) / 2 + nh / 2
    left = [
        ("user", "Customers", "Portal, SMS login", CYAN),
        ("wrench", "Installers", "Bookings, messages", AMBER),
        ("layout", "Ops team", "Atlas workflows, SLAs", VIOLET),
        ("trend", "Sales", "Offers, product catalog", PINK),
    ]
    right = [
        ("truck", "Suppliers", "Material orders by API", CYAN),
        ("receipt", "Accounting", "Invoices, bookkeeping", GREEN),
        ("bank", "Banks", "Open banking payments", AMBER),
        ("message", "Messaging", "SMS and email flows", PINK),
    ]

    def node(x: float, y: float, ic: str, title: str, sub: str, color: str, delay: float) -> str:
        return (
            f'<g class="rise" style="animation-delay:{n(delay)}s"><g transform="translate({n(x)},{n(y)})">'
            f'<rect width="{nw}" height="{nh}" rx="14" fill="{PANEL}" stroke="{color}" stroke-opacity=".45"/>'
            f'<rect x="15" y="{n((nh - 42) / 2)}" width="42" height="42" rx="11" fill="{color}" fill-opacity=".14"/>'
            + icon(ic, 24, (nh - 42) / 2 + 9, color)
            + f'<text x="72" y="{n(nh / 2 - 4)}" class="s" font-size="16" font-weight="700" fill="{TEXT}">{esc(title)}</text>'
            f'<text x="72" y="{n(nh / 2 + 16)}" class="s" font-size="13" fill="{MUTED}">{esc(sub)}</text></g></g>'
        )

    lx, rx = 28, W - 28 - nw
    cw, ch = 220, 136
    cl, cr = core_cx - cw / 2, core_cx + cw / 2
    links, packets = [], []
    for i, y in enumerate(ys):
        yc = y + nh / 2
        for side, (d, color) in enumerate((
            (f"M{lx + nw},{n(yc)} C{n((lx + nw + cl) / 2)},{n(yc)} {n((lx + nw + cl) / 2)},{n(core_cy)} {n(cl)},{n(core_cy)}", left[i][3]),
            (f"M{n(cr)},{n(core_cy)} C{n((cr + rx) / 2)},{n(core_cy)} {n((cr + rx) / 2)},{n(yc)} {rx},{n(yc)}", right[i][3]),
        )):
            links.append(
                f'<path d="{d}" fill="none" stroke="#273049" stroke-width="1.6"/>'
                f'<path d="{d}" fill="none" stroke="{color}" stroke-opacity=".55" stroke-width="1.6" '
                f'stroke-dasharray="3 9" class="flow"/>'
            )
            for j, rev in enumerate((False, True)):
                begin = i * 0.55 + side * 0.3 + j * 1.5
                kp = ' keyPoints="1;0" keyTimes="0;1" calcMode="linear"' if rev else ""
                packets.append(
                    f'<g opacity="0"><circle r="7" fill="{color}" fill-opacity=".22"/><circle r="3.2" fill="{color}"/>'
                    f'<animateMotion path="{d}" dur="3s" begin="{n(begin)}s" repeatCount="indefinite"{kp}/>'
                    f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.12;.88;1" dur="3s" '
                    f'begin="{n(begin)}s" repeatCount="indefinite"/></g>'
                )
    bar_y = ys[3] + nh + 36
    down = f"M{core_cx},{n(core_cy + ch / 2)} V{bar_y}"
    links.append(
        f'<path d="{down}" stroke="#273049" stroke-width="1.6"/>'
        f'<path d="{down}" stroke="{CYAN}" stroke-opacity=".55" stroke-width="1.6" stroke-dasharray="3 9" class="flow"/>'
    )
    for j, rev in enumerate((False, True)):
        kp = ' keyPoints="1;0" keyTimes="0;1" calcMode="linear"' if rev else ""
        packets.append(
            f'<g opacity="0"><circle r="7" fill="{CYAN}" fill-opacity=".22"/><circle r="3.2" fill="{CYAN}"/>'
            f'<animateMotion path="{down}" dur="1.8s" begin="{n(j * 0.9)}s" repeatCount="indefinite"{kp}/>'
            f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.15;.85;1" dur="1.8s" '
            f'begin="{n(j * 0.9)}s" repeatCount="indefinite"/></g>'
        )
    core_path = rr_path(cl, core_cy - ch / 2, cw, ch, 20)
    core = (
        f'<circle class="breathe" cx="{core_cx}" cy="{n(core_cy)}" r="150" fill="url(#glow)"/>'
        f'<path d="{core_path}" fill="#121A2E" stroke="url(#coreEdge)" stroke-width="1.6"/>'
        + comet(core_path, PINK, dur=5)
        + f'<rect x="{core_cx - 23}" y="{n(core_cy - 50)}" width="46" height="46" rx="13" fill="{VIOLET}" fill-opacity=".18"/>'
        + icon("cpu", core_cx - 12, core_cy - 39, TINT[VIOLET])
        + f'<text x="{core_cx}" y="{n(core_cy + 22)}" class="s" font-size="21" font-weight="800" fill="{TEXT}" '
        f'text-anchor="middle">Core API</text>'
        f'<text x="{core_cx}" y="{n(core_cy + 44)}" class="m" font-size="12" fill="{MUTED}" text-anchor="middle">'
        "FastAPI · Python · Postgres</text>"
    )
    chips = ["Cloud Run", "Cloud SQL", "Cloud Build", "Terraform"]
    cx, chip_svg = W - 28 - 20, []
    for c in reversed(chips):
        w = len(c) * 12.5 * MONO_W + 26
        cx -= w
        chip_svg.append(
            f'<rect x="{n(cx)}" y="{bar_y + 14}" width="{n(w)}" height="28" rx="14" fill="#141C2E" stroke="{LINE}"/>'
            f'<text x="{n(cx + w / 2)}" y="{bar_y + 32.5}" class="m" font-size="12.5" fill="{TEXT}" text-anchor="middle">{c}</text>'
        )
        cx -= 10
    bar = (
        f'<g class="rise" style="animation-delay:.9s"><rect x="28" y="{bar_y}" width="{W - 56}" height="56" rx="14" '
        f'fill="{PANEL}" stroke="{CYAN}" stroke-opacity=".35"/>'
        + icon("cloud", 46, bar_y + 16, CYAN)
        + f'<text x="82" y="{bar_y + 34}" class="s" font-size="16" font-weight="700" fill="{TEXT}">Google Cloud</text>'
        f'<text x="196" y="{bar_y + 34}" class="s" font-size="13" fill="{MUTED}">infrastructure as code, deployed per engineer</text>'
        + "".join(chip_svg) + "</g>"
    )
    heads = "".join(
        f'<text x="{n(x)}" y="40" class="m" font-size="11.5" letter-spacing="2.4" fill="{DIM}" text-anchor="{a}">{t}</text>'
        for x, a, t in ((lx + 2, "start", "WHO USES IT"), (core_cx, "middle", "THE CORE"), (W - 30, "end", "WHAT IT TALKS TO"))
    )
    defs = (
        f'<radialGradient id="glow"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="coreEdge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{VIOLET}"/>'
        f'<stop offset="1" stop-color="{CYAN}"/></linearGradient>'
    )
    css = (
        ".flow{animation:flow 1.2s linear infinite}@keyframes flow{to{stroke-dashoffset:-24}}"
        ".breathe{transform-box:fill-box;transform-origin:center;animation:breathe 5s ease-in-out infinite}"
        "@keyframes breathe{50%{transform:scale(1.15);opacity:.7}}"
    )
    nodes = "".join(node(lx, y, *left[i], 0.1 + i * 0.12) for i, y in enumerate(ys)) + "".join(
        node(rx, y, *right[i], 0.3 + i * 0.12) for i, y in enumerate(ys)
    )
    body = heads + "".join(links) + core + nodes + "".join(packets) + bar
    return card(W, H, "What Elaf builds at work", body, css, defs)


# ---------------------------------------------------------------- project cards

PROJECTS = [
    ("atlas", "layout", "Atlas Ops Platform", "CLEAN ENERGY", "IN PRODUCTION", GREEN, VIOLET,
     ["Runs every heat pump, solar and battery install:", "workflow engine, SLAs, tasks and live pipeline."],
     ["Python", "FastAPI", "Next.js", "PostgreSQL", "GCP"]),
    ("voice", "mic", "Offline Voice to Text", "DESKTOP APP", "OPEN SOURCE", CYAN, CYAN,
     ["Hold a hotkey, speak, and text appears in any app.", "Whisper.cpp runs fully offline on your machine."],
     ["Python", "Whisper.cpp", "Desktop"]),
    ("resume", "file", "ResumeFlow", "LLM PIPELINE", "OPEN SOURCE", CYAN, PINK,
     ["Reads a job post and writes a tailored resume", "and cover letter, exported as a polished PDF."],
     ["Python", "LangChain", "OpenAI", "Streamlit", "LaTeX"]),
    ("caire", "route", "Caire Scheduling", "FIELD SERVICE", "LIVE", GREEN, AMBER,
     ["Field service planning with drag and drop", "scheduling and route optimization via Timefold."],
     ["Next.js", "TypeScript", "Bryntum", "Timefold"]),
    ("gameshub", "gamepad", "GamesHub", "MULTIPLAYER", "LIVE", GREEN, PINK,
     ["Multiplayer gaming platform: create lobbies,", "invite friends and compete in real time matches."],
     ["React", "Node.js", "Firebase", "TypeScript"]),
    ("parkingtime", "parking", "ParkingTime Dashboard", "PARKINGTIME AB", "INTERNSHIP", AMBER, CYAN,
     ["Operations dashboard for a Swedish parking", "company, with Auth0 login and Python AI features."],
     ["Go", "React", "Auth0", "Python", "MUI"]),
]


def project_card(i: int, ic: str, title: str, kicker: str, status: str, status_color: str,
                 accent: str, desc: list[str], tech: list[str]) -> str:
    W, H = 480, 250
    sw = len(status) * (11 * MONO_W + 1.2) + 22
    chips, x = [], 28.0
    for t in tech:
        w = len(t) * 12.5 * MONO_W + 22
        chips.append(
            f'<rect x="{n(x)}" y="190" width="{n(w)}" height="28" rx="14" fill="#141C2E" stroke="{LINE}"/>'
            f'<text x="{n(x + w / 2)}" y="208.5" class="m" font-size="12.5" fill="#C9D1D9" text-anchor="middle">{esc(t)}</text>'
        )
        x += w + 8
    defs = (
        f'<radialGradient id="halo"><stop offset="0" stop-color="{accent}" stop-opacity=".28"/>'
        f'<stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient>'
    )
    css = (
        ".halo{transform-box:fill-box;transform-origin:center;animation:halo 7s ease-in-out infinite}"
        "@keyframes halo{50%{transform:translate(40px,20px) scale(1.2)}}"
    )
    body = (
        '<circle class="halo" cx="60" cy="40" r="170" fill="url(#halo)"/>'
        f'<rect x="28" y="28" width="52" height="52" rx="14" fill="{accent}" fill-opacity=".16" stroke="{accent}" stroke-opacity=".5"/>'
        + icon(ic, 39, 39, TINT[accent], 1.25, 1.6)
        + f'<text x="96" y="52" class="s" font-size="21" font-weight="700" fill="#F0F3F8">{esc(title)}</text>'
        f'<text x="97" y="74" class="m" font-size="11.5" letter-spacing="1.6" fill="{TINT[accent]}">{esc(kicker)}</text>'
        f'<rect x="{n(W - 28 - sw)}" y="27" width="{n(sw)}" height="24" rx="12" fill="{status_color}" fill-opacity=".12" '
        f'stroke="{status_color}" stroke-opacity=".5"/>'
        f'<text x="{n(W - 28 - sw / 2)}" y="43" class="m" font-size="11" font-weight="700" letter-spacing="1.2" '
        f'fill="{TINT[status_color]}" text-anchor="middle">{esc(status)}</text>'
        + "".join(
            f'<text x="28" y="{122 + k * 24}" class="s" font-size="15" fill="{MUTED}">{esc(line)}</text>'
            for k, line in enumerate(desc)
        )
        + "".join(chips)
    )
    return card(W, H, title, body, css, defs, r=18, comet_color=accent, comet_delay=i * 1.3)


def button(i: int, ic: str, label: str, sub: str, color: str) -> str:
    W, H = 320, 74
    body = (
        f'<rect x="16" y="15" width="44" height="44" rx="12" fill="{color}" fill-opacity=".16" stroke="{color}" stroke-opacity=".5"/>'
        + icon(ic, 26, 25, TINT[color])
        + f'<text x="76" y="34" class="s" font-size="17" font-weight="700" fill="{TEXT}">{esc(label)}</text>'
        f'<text x="76" y="55" class="m" font-size="12.5" fill="{MUTED}">{esc(sub)}</text>'
        f'<text x="{W - 22}" y="44" class="s" font-size="20" fill="{TINT[color]}" text-anchor="end">↗</text>'
    )
    return card(W, H, label, body, r=16, comet_color=color, comet_delay=i * 2.1)


# ---------------------------------------------------------------- timeline


def timeline() -> str:
    W, H = 1000, 236
    xs, ly = [125, 375, 625, 875], 106
    items = [
        ("2020", "FutureGames", "Frontend Developer Program", CYAN),
        ("2022", "KTH", "BSc Computer Science", PINK),
        ("2024", "ParkingTime AB", "AI Full Stack Developer", AMBER),
        ("2026 · NOW", "Clean Energy Tech", "Software Engineer", VIOLET),
    ]
    draw, start = 2.6, 0.3
    span = xs[-1] - xs[0]
    parts = []
    for (year, title, sub, color), x in zip(items, xs):
        delay = start + draw * (x - xs[0]) / span
        now = year.endswith("NOW")
        parts.append(
            f'<text class="m rise" style="animation-delay:{n(delay)}s" x="{x}" y="70" font-size="14" '
            f'letter-spacing="2" fill="{TINT[color]}" text-anchor="middle" font-weight="700">{year}</text>'
            + (f'<circle class="pulse" cx="{x}" cy="{ly}" r="14" fill="none" stroke="{color}" stroke-width="2"/>' if now else "")
            + f'<g class="pop" style="animation-delay:{n(delay)}s"><circle cx="{x}" cy="{ly}" r="14" fill="#0B1020" '
            f'stroke="{color}" stroke-width="2"/><circle cx="{x}" cy="{ly}" r="6" fill="{color}"/></g>'
            f'<g class="rise" style="animation-delay:{n(delay + 0.15)}s">'
            f'<text x="{x}" y="156" class="s" font-size="18" font-weight="700" fill="{TEXT}" text-anchor="middle">{esc(title)}</text>'
            f'<text x="{x}" y="181" class="s" font-size="14" fill="{MUTED}" text-anchor="middle">{esc(sub)}</text></g>'
        )
    defs = (
        f'<linearGradient id="prog" x1="{xs[0]}" y1="0" x2="{xs[-1]}" y2="0" gradientUnits="userSpaceOnUse">'
        + "".join(f'<stop offset="{k / 3:.3f}" stop-color="{c}"/>' for k, (_, _, _, c) in enumerate(items))
        + "</linearGradient>"
    )
    line = (
        f'<line x1="{xs[0]}" y1="{ly}" x2="{xs[-1]}" y2="{ly}" stroke="{LINE}" stroke-width="2"/>'
        f'<line x1="{xs[0]}" y1="{ly}" x2="{xs[-1]}" y2="{ly}" stroke="url(#prog)" stroke-width="3" '
        f'stroke-linecap="round" stroke-dasharray="{span}" stroke-dashoffset="{span}">'
        f'<animate attributeName="stroke-dashoffset" from="{span}" to="0" dur="{draw}s" begin="{start}s" '
        'fill="freeze" calcMode="spline" keyTimes="0;1" keySplines=".4 0 .2 1"/></line>'
        f'<g opacity="0"><circle r="9" fill="#fff" fill-opacity=".18"/><circle r="3.5" fill="#fff"/>'
        f'<animateMotion path="M{xs[0]},{ly} H{xs[-1]}" dur="4.5s" begin="{start + draw}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.1;.85;1" dur="4.5s" '
        f'begin="{start + draw}s" repeatCount="indefinite"/></g>'
    )
    return card(W, H, "Elaf's journey from 2020 to now", line + "".join(parts), defs=defs)


# ---------------------------------------------------------------- tech stack


def fetch_icon(name: str) -> str:
    """One skillicons.dev icon as a <symbol>, with its ids prefixed so icons cannot collide."""
    req = urllib.request.Request(f"https://skillicons.dev/icons?i={name}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
    inner = raw[raw.index("<svg", 5): raw.rindex("</g>")].strip()
    pfx = f"{name}_"
    inner = inner.replace("xlink:href=", "href=")
    inner = re.sub(r'id="([^"]+)"', lambda m: f'id="{pfx}{m.group(1)}"', inner)
    inner = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{pfx}{m.group(1)})", inner)
    inner = re.sub(r'href="#([^"]+)"', lambda m: f'href="#{pfx}{m.group(1)}"', inner)
    content = inner[inner.index(">") + 1: inner.rindex("</svg>")]
    return f'<symbol id="ic_{name}" viewBox="0 0 256 256">{content}</symbol>'


def stack() -> str:
    W, H = 1000, 262
    rows = [
        ["py", "ts", "js", "react", "nextjs", "nodejs", "fastapi", "go", "html", "css", "tailwind", "supabase"],
        ["gcp", "aws", "docker", "terraform", "postgres", "mongodb", "redis", "firebase", "githubactions", "vercel", "git", "linux"],
    ]
    ai = [("Claude Code", VIOLET), ("OpenAI API", GREEN), ("LangChain", CYAN), ("Whisper.cpp", PINK),
          ("Gemini", AMBER), ("MCP servers", VIOLET), ("AI agents", PINK), ("Prompt engineering", CYAN),
          ("Cursor", GREEN), ("PyTorch", AMBER), ("Pandas", CYAN)]
    size, step = 60, 78
    symbols = "".join(fetch_icon(i) for row in rows for i in row)
    css, out = "", []
    for r, row in enumerate(rows):
        width = len(row) * step
        copies = math.ceil((W + width) / width) + 1
        uses = "".join(
            f'<use href="#ic_{name}" x="{c * width + k * step}" y="0" width="{size}" height="{size}"/>'
            for c in range(copies) for k, name in enumerate(row)
        )
        css += f"@keyframes mq{r}{{from{{transform:translateX({0 if r % 2 == 0 else -width}px)}}to{{transform:translateX({-width if r % 2 == 0 else 0}px)}}}}"
        out.append(
            f'<g transform="translate(20,{28 + r * 80})"><g style="animation:mq{r} {34 + r * 6}s linear infinite">{uses}</g></g>'
        )
    chip_w = [len(t) * 14 * MONO_W + 44 for t, _ in ai]
    width = sum(chip_w) + 12 * len(ai)
    copies = math.ceil((W + width) / width) + 1
    chips, x = [], 0.0
    for _ in range(copies):
        for (t, c), w in zip(ai, chip_w):
            chips.append(
                f'<rect x="{n(x)}" y="0" width="{n(w)}" height="38" rx="19" fill="#121A2B" stroke="{c}" stroke-opacity=".45"/>'
                f'<circle cx="{n(x + 18)}" cy="19" r="4" fill="{c}"/>'
                f'<text x="{n(x + 30)}" y="24" class="m" font-size="14" fill="{TEXT}">{esc(t)}</text>'
            )
            x += w + 12
    css += f"@keyframes mq2{{to{{transform:translateX(-{n(width)}px)}}}}"
    out.append(f'<g transform="translate(0,{28 + 2 * 80 + 10})"><g style="animation:mq2 46s linear infinite">{"".join(chips)}</g></g>')
    defs = (
        symbols
        + '<linearGradient id="fade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#000"/>'
        '<stop offset=".09" stop-color="#fff"/><stop offset=".91" stop-color="#fff"/><stop offset="1" stop-color="#000"/></linearGradient>'
        f'<mask id="edges"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>'
    )
    return card(W, H, "Tech stack", f'<g mask="url(#edges)">{"".join(out)}</g>', css, defs)


# ---------------------------------------------------------------- activity card


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def fetch_calendar() -> tuple[int, list[tuple[str, int]]]:
    query = (
        '{ user(login: "%s") { contributionsCollection { contributionCalendar { totalContributions '
        "weeks { contributionDays { date contributionCount } } } } } }" % USER
    )
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {token()}", "Content-Type": "application/json", "User-Agent": USER},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        cal = json.load(r)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [(d["date"], d["contributionCount"]) for w in cal["weeks"] for d in w["contributionDays"]]
    return cal["totalContributions"], days


def odometer(value: str, x: float, y: float, size: float, color: str, delay: float, uid: str) -> str:
    """Digits roll into place like a mechanical counter."""
    cw, lh = size * MONO_W, size * 1.2
    parts = []
    for i, ch in enumerate(value):
        cx = x + i * cw
        if not ch.isdigit():
            parts.append(f'<text x="{n(cx)}" y="{n(y)}">{esc(ch)}</text>')
            continue
        shift = (10 + int(ch)) * lh
        strip = "".join(f'<text x="{n(cx)}" y="{n(y + k * lh)}">{k % 10}</text>' for k in range(20))
        parts.append(
            f"<g>{strip}<animateTransform attributeName=\"transform\" type=\"translate\" values=\"0 0;0 {n(-shift)}\" "
            f'keyTimes="0;1" calcMode="spline" keySplines=".15 .7 .2 1" dur="{n(1.6 + i * 0.18)}s" '
            f'begin="{n(delay)}s" fill="freeze"/></g>'
        )
    return (
        f'<clipPath id="{uid}"><rect x="{n(x - 2)}" y="{n(y - size * 0.86)}" width="{n(len(value) * cw + 4)}" '
        f'height="{n(size * 1.08)}"/></clipPath>'
        f'<g clip-path="url(#{uid})" class="m" font-size="{n(size)}" font-weight="800" fill="{color}">{"".join(parts)}</g>'
    )


def activity() -> str:
    total, days = fetch_calendar()
    today = dt.date.fromisoformat(days[-1][0])
    counts = [c for _, c in days]
    active = sum(1 for c in counts if c)
    best_week = max(sum(counts[i:i + 7]) for i in range(0, len(counts), 7))
    best_day, best = max(days, key=lambda d: d[1])
    bd = dt.date.fromisoformat(best_day)
    months, (yy, mm) = [], (today.year, today.month)
    for _ in range(12):
        months.append((yy, mm))
        yy, mm = (yy - 1, 12) if mm == 1 else (yy, mm - 1)
    months.reverse()
    per = dict.fromkeys(months, 0)
    for d, c in days:
        key = (int(d[:4]), int(d[5:7]))
        if key in per:
            per[key] += c

    W, H = 1000, 300
    metrics = [
        (f"{total:,}", "Contributions", TINT[VIOLET]),
        (str(active), "Active days", TINT[PINK]),
        (str(best_week), "Best week", TINT[CYAN]),
        (str(best), f"Busiest day, {bd.day} {bd:%b}", TINT[GREEN]),
    ]
    cells = []
    for i, (value, label, color) in enumerate(metrics):
        x, y = 44 + (i % 2) * 240, 126 + (i // 2) * 104
        cells.append(
            odometer(value, x, y, 42, color, 0.3 + i * 0.15, f"od{i}")
            + f'<text x="{x + 1}" y="{y + 30}" class="s" font-size="14" fill="{MUTED}">{esc(label)}</text>'
        )
    x0, x1, base, maxh = 566, 962, 244, 138
    slot = (x1 - x0) / 12
    peak = max(per.values()) or 1
    bars = []
    for i, key in enumerate(months):
        v = per[key]
        h = max(v / peak * maxh, 3 if v else 0)
        bx = x0 + i * slot + (slot - 16) / 2
        delay = 0.4 + i * 0.07
        top = v == peak
        bars.append(
            f'<rect x="{n(bx)}" y="{base - maxh}" width="16" height="{maxh}" rx="8" fill="#fff" fill-opacity=".035"/>'
            + (f'<rect class="bar" style="animation-delay:{n(delay)}s" x="{n(bx)}" y="{n(base - h)}" width="16" '
               f'height="{n(h)}" rx="{n(min(8, h / 2))}" fill="url(#{"barTop" if top else "bar"})"/>' if v else "")
            + f'<text class="val m" style="animation-delay:{n(delay + 0.6)}s" x="{n(bx + 8)}" y="{n(base - h - 8)}" '
            f'font-size="11" text-anchor="middle" fill="{TEXT if top else DIM}"' + (' font-weight="700"' if top else "")
            + f">{v}</text>"
            f'<text x="{n(bx + 8)}" y="{base + 22}" class="m" font-size="11" text-anchor="middle" fill="{DIM}">'
            f"{dt.date(key[0], key[1], 1):%b}</text>"
        )
    defs = (
        f'<linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{PINK}"/>'
        f'<stop offset="1" stop-color="{VIOLET}" stop-opacity=".7"/></linearGradient>'
        f'<linearGradient id="barTop" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{CYAN}"/>'
        f'<stop offset="1" stop-color="{VIOLET}"/></linearGradient>'
    )
    css = (
        ".bar{transform-box:fill-box;transform-origin:50% 100%;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both}"
        "@keyframes grow{from{transform:scaleY(0)}}"
        ".val{animation:fade .6s ease both}@keyframes fade{from{opacity:0}}"
    )
    stamp = f"UPDATED {today.day} {today:%b %Y}".upper()
    body = (
        f'<text x="44" y="46" class="m" font-size="12" letter-spacing="2.4" fill="{DIM}">GITHUB ACTIVITY · LAST 12 MONTHS</text>'
        f'<text x="{W - 40}" y="46" class="m" font-size="12" letter-spacing="2.4" fill="{DIM}" text-anchor="end">{stamp}</text>'
        f'<rect x="526" y="76" width="1" height="190" fill="{LINE}"/>'
        + "".join(cells) + "".join(bars)
    )
    return card(W, H, f"{total:,} contributions in the last 12 months", body, css, defs)


# ---------------------------------------------------------------- footer


def footer() -> str:
    W, H = 1000, 176

    def wave(amp: float, base: float, period: float, phase: float) -> str:
        pts = " L".join(f"{x},{base + amp * math.sin(2 * math.pi * x / period + phase):.1f}" for x in range(0, 2001, 10))
        return f"M0,{H} L{pts} L2000,{H} Z"

    layers = [(10, 128, 500, 0, VIOLET, ".35", 16), (12, 138, 500, 1.6, PINK, ".3", 11), (8, 150, 250, 3.1, CYAN, ".35", 8)]
    waves = "".join(
        f'<g style="animation:wave {s}s linear infinite"><path d="{wave(a, b, p, ph)}" fill="{c}" fill-opacity="{o}"/></g>'
        for a, b, p, ph, c, o, s in layers
    )
    defs = (
        f'<linearGradient id="nm" x1="0" y1="0" x2=".5" y2="0" spreadMethod="repeat">'
        f'<stop offset="0" stop-color="{TINT[VIOLET]}"/><stop offset=".33" stop-color="{PINK}"/>'
        f'<stop offset=".66" stop-color="{CYAN}"/><stop offset="1" stop-color="{TINT[VIOLET]}"/>'
        '<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to=".5 0" '
        'dur="6s" repeatCount="indefinite"/></linearGradient>'
    )
    css = "@keyframes wave{to{transform:translateX(-1000px)}}"
    body = (
        waves
        + f'<text x="{W / 2}" y="62" class="s" font-size="30" font-weight="800" fill="url(#nm)" text-anchor="middle">'
        "Thanks for stopping by</text>"
        f'<text x="{W / 2}" y="94" class="s" font-size="16" fill="{MUTED}" text-anchor="middle">'
        "Let's build something people actually use.</text>"
    )
    return card(W, H, "Thanks for stopping by", body, css, defs)


# ---------------------------------------------------------------- main


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}  {len(content) / 1024:.1f} KB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", choices=["all", "stats"], default="all")
    ap.add_argument("--out", type=Path, default=ROOT / "dist", help="where the activity card goes")
    args = ap.parse_args()
    if args.target == "all":
        assets = ROOT / "assets"
        write(assets / "hero.svg", hero())
        write(assets / "now.svg", terminal())
        write(assets / "system.svg", system())
        write(assets / "timeline.svg", timeline())
        write(assets / "stack.svg", stack())
        write(assets / "footer.svg", footer())
        for i, p in enumerate(PROJECTS):
            write(assets / f"card-{p[0]}.svg", project_card(i, *p[1:]))
        for i, b in enumerate((("globe", "Portfolio", "elafalzoubi.vercel.app", VIOLET),
                               ("linkedin", "LinkedIn", "Elaf Alzoubi", CYAN),
                               ("mail", "Email", "elaffree85@gmail.com", PINK))):
            write(assets / f"btn-{b[1].lower()}.svg", button(i, *b))
    write(args.out / "stats.svg", activity())


if __name__ == "__main__":
    main()
