#!/usr/bin/env python3
"""Generate simple SVG avatars for the debate UI."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)

caesar = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="48" fill="#8B0000" stroke="#DAA520" stroke-width="3"/>
  <text x="50" y="55" font-family="serif" font-size="40" fill="#DAA520" text-anchor="middle" dominant-baseline="middle">C</text>
</svg>"""

pompey = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="48" fill="#1B3A5C" stroke="#C0C0C0" stroke-width="3"/>
  <text x="50" y="55" font-family="serif" font-size="40" fill="#C0C0C0" text-anchor="middle" dominant-baseline="middle">P</text>
</svg>"""

senate = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="48" fill="#4A3728" stroke="#DAA520" stroke-width="3"/>
  <text x="50" y="55" font-family="serif" font-size="40" fill="#DAA520" text-anchor="middle" dominant-baseline="middle">S</text>
</svg>"""

(OUT / "caesar.svg").write_text(caesar, encoding="utf-8")
(OUT / "pompey.svg").write_text(pompey, encoding="utf-8")
(OUT / "senate.svg").write_text(senate, encoding="utf-8")
print("Avatars written to", OUT)
