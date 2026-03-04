#!/usr/bin/env python3
"""
Download a small set of public-domain texts into data/*_docs.
Safe fallback: if download fails, keep local authored samples.
"""

from __future__ import annotations

from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]

SOURCES = [
    (
        "https://www.gutenberg.org/cache/epub/10657/pg10657.txt",
        ROOT / "data" / "caesar_docs" / "caesar_gallic_war_pg.txt",
    ),
    (
        "https://www.gutenberg.org/cache/epub/674/pg674.txt",
        ROOT / "data" / "pompey_docs" / "plutarch_lives_pg.txt",
    ),
]


def fetch(url: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} -> {out}")
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        out.write_text(r.text, encoding="utf-8")


if __name__ == "__main__":
    for url, out in SOURCES:
        try:
            fetch(url, out)
        except Exception as e:
            print(f"WARN: failed {url}: {e}")
    print("Done.")
