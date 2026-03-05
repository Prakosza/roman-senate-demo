#!/usr/bin/env python3
"""
Download public-domain English sources into data/*_docs.
Safe fallback: if download fails, keep local authored samples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import httpx

ROOT = Path(__file__).resolve().parents[1]

ROMAN_FOCUS_COMMON = (
    "caesar",
    "julius",
    "pompey",
    "pompeius",
    "cicero",
    "senate",
    "republic",
    "civil war",
    "brutus",
    "crassus",
    "cato",
    "consul",
    "rubicon",
)


@dataclass(frozen=True)
class OutputSpec:
    out: Path
    start_markers: Sequence[str] = ()
    end_markers: Sequence[str] = ()
    keyword_focus: Sequence[str] = ()
    context_paragraphs: int = 1
    min_chars: int = 12000
    max_chars: int | None = None


DOWNLOAD_PLAN: Dict[str, List[OutputSpec]] = {
    # Julius Caesar, "De Bello Gallico" + "Civil War" (English translation)
    "https://www.gutenberg.org/ebooks/10657.txt.utf-8": [
        OutputSpec(
            out=ROOT / "data" / "caesar_docs" / "caesar_commentaries_pg10657_full.txt",
            start_markers=("THE WAR IN GAUL\n\nBOOK I",),
            max_chars=900_000,
        ),
        OutputSpec(
            out=ROOT / "data" / "pompey_docs" / "caesar_commentaries_pg10657_civil_war_context.txt",
            start_markers=("THE CIVIL WAR\n\nBOOK I",),
            max_chars=700_000,
        ),
    ],
    # Suetonius: keep only "Julius Caesar" biography section.
    "https://www.gutenberg.org/ebooks/6400.txt.utf-8": [
        OutputSpec(
            out=ROOT / "data" / "caesar_docs" / "suetonius_twelve_caesars_pg6400.txt",
            start_markers=("CAIUS JULIUS CASAR.", "CAIUS JULIUS CAESAR."),
            end_markers=("D. OCTAVIUS CAESAR AUGUSTUS.",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            min_chars=8000,
            max_chars=450_000,
        ),
    ],
    # Lucan, "Pharsalia" (civil war between Caesar and Pompey)
    "https://www.gutenberg.org/ebooks/602.txt.utf-8": [
        OutputSpec(
            out=ROOT / "data" / "caesar_docs" / "lucan_pharsalia_pg602_caesar_context.txt",
            start_markers=("BOOK I\n\nTHE CROSSING OF THE RUBICON",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            max_chars=500_000,
        ),
        OutputSpec(
            out=ROOT / "data" / "pompey_docs" / "lucan_pharsalia_pg602_pompey_context.txt",
            start_markers=("BOOK I\n\nTHE CROSSING OF THE RUBICON",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            max_chars=500_000,
        ),
    ],
    # Plutarch Parallel Lives (large omnibus): extract targeted sections only.
    "https://www.gutenberg.org/ebooks/674.txt.utf-8": [
        OutputSpec(
            out=ROOT / "data" / "caesar_docs" / "plutarch_lives_pg674_caesar_context.txt",
            start_markers=("CAESAR\n\nAfter Sylla became master of Rome",),
            end_markers=("\n\nPHOCION\n\n",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            max_chars=800_000,
        ),
        OutputSpec(
            out=ROOT / "data" / "pompey_docs" / "plutarch_lives_pg674_pompey_context.txt",
            start_markers=("POMPEY\n\nThe people of Rome seem to have entertained for Pompey",),
            end_markers=("ALEXANDER\n\nIt being my purpose to write the lives of Alexander the king",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            max_chars=800_000,
        ),
    ],
    # Plutarch Vol. III: keep only Pompey section + comparison.
    "https://www.gutenberg.org/ebooks/14140.txt.utf-8": [
        OutputSpec(
            out=ROOT / "data" / "pompey_docs" / "plutarch_lives_vol3_pg14140_full.txt",
            start_markers=("LIFE OF POMPEIUS.",),
            end_markers=("LIFE OF ALEXANDER.",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            max_chars=650_000,
        ),
    ],
    # Plutarch Vol. II: drop Greek lives; keep later Roman section focus.
    "https://www.gutenberg.org/ebooks/14114.txt.utf-8": [
        OutputSpec(
            out=ROOT / "data" / "pompey_docs" / "plutarch_lives_vol2_pg14114_pompey_context.txt",
            start_markers=("LIFE OF LUCULLUS",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            max_chars=650_000,
        ),
    ],
    # Cicero's correspondence: retain only passages with high Roman civil-war signal.
    "https://www.gutenberg.org/ebooks/58418.txt.utf-8": [
        OutputSpec(
            out=ROOT / "data" / "pompey_docs" / "cicero_letters_to_atticus_vol1_pg58418.txt",
            start_markers=("CICERO TO ATTICUS, GREETING.",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            context_paragraphs=1,
            min_chars=10000,
            max_chars=500_000,
        ),
    ],
    "https://www.gutenberg.org/ebooks/50692.txt.utf-8": [
        OutputSpec(
            out=ROOT / "data" / "pompey_docs" / "cicero_letters_to_atticus_vol2_pg50692.txt",
            start_markers=("CICERO TO ATTICUS, GREETING.",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            context_paragraphs=1,
            min_chars=10000,
            max_chars=500_000,
        ),
    ],
    "https://www.gutenberg.org/ebooks/51403.txt.utf-8": [
        OutputSpec(
            out=ROOT / "data" / "pompey_docs" / "cicero_letters_to_atticus_vol3_pg51403.txt",
            start_markers=("CICERO TO ATTICUS, GREETING.",),
            keyword_focus=ROMAN_FOCUS_COMMON,
            context_paragraphs=1,
            min_chars=10000,
            max_chars=500_000,
        ),
    ],
}


def _strip_gutenberg_boilerplate(text: str) -> str:
    start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"

    if start_marker in text:
        text = text.split(start_marker, maxsplit=1)[1]
    if end_marker in text:
        text = text.split(end_marker, maxsplit=1)[0]

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip() + "\n"


def _find_first(text: str, markers: Iterable[str]) -> int:
    positions = [text.find(marker) for marker in markers]
    valid = [pos for pos in positions if pos >= 0]
    return min(valid) if valid else -1


def _trim_by_markers(text: str, starts: Sequence[str], ends: Sequence[str]) -> str:
    if starts:
        start_pos = _find_first(text, starts)
        if start_pos >= 0:
            text = text[start_pos:]
    if ends:
        end_pos = _find_first(text, ends)
        if end_pos > 0:
            text = text[:end_pos]
    return text.strip() + "\n"


def _extract_keyword_passages(text: str, keywords: Sequence[str], context_paragraphs: int = 1) -> str:
    if not keywords:
        return text

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text

    lowered_keywords = tuple(k.lower() for k in keywords)
    selected_indexes: set[int] = set()
    for idx, paragraph in enumerate(paragraphs):
        para_l = paragraph.lower()
        if any(keyword in para_l for keyword in lowered_keywords):
            start = max(0, idx - context_paragraphs)
            end = min(len(paragraphs), idx + context_paragraphs + 1)
            selected_indexes.update(range(start, end))

    if not selected_indexes:
        return text

    filtered = "\n\n".join(paragraphs[idx] for idx in sorted(selected_indexes)).strip()
    return filtered + "\n"


def _strip_obvious_noise(text: str) -> str:
    out_lines: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out_lines.append("")
            continue
        if s.startswith("Produced by "):
            continue
        if s.startswith("[Illustration"):
            continue
        out_lines.append(line)

    cleaned = "\n".join(out_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def _dedupe_repeated_paragraphs(text: str, min_chars: int = 180) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text

    seen: set[str] = set()
    kept: List[str] = []
    for paragraph in paragraphs:
        normalized = " ".join(paragraph.split()).lower()
        if len(normalized) < min_chars:
            kept.append(paragraph)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        kept.append(paragraph)

    return "\n\n".join(kept).strip() + "\n"


def _clamp_size(text: str, max_chars: int | None) -> str:
    if not max_chars or len(text) <= max_chars:
        return text

    cut = text.rfind("\n\n", 0, max_chars)
    if cut < max_chars // 2:
        cut = max_chars
    return text[:cut].strip() + "\n"


def _render_output(raw_text: str, spec: OutputSpec) -> str:
    text = _trim_by_markers(raw_text, spec.start_markers, spec.end_markers)
    text = _extract_keyword_passages(text, spec.keyword_focus, context_paragraphs=spec.context_paragraphs)
    if len(text) < spec.min_chars:
        # Avoid over-trimming: fall back to marker-only trimming if keyword filtering is too aggressive.
        text = _trim_by_markers(raw_text, spec.start_markers, spec.end_markers)
    text = _strip_obvious_noise(text)
    text = _dedupe_repeated_paragraphs(text)
    text = _clamp_size(text, spec.max_chars)
    return text


def fetch_and_clean(client: httpx.Client, url: str) -> str:
    print(f"Downloading {url}")
    response = client.get(url)
    response.raise_for_status()
    return _strip_gutenberg_boilerplate(response.text)


def _dedupe_across_collection(collection_dir: Path, min_chars: int = 220) -> None:
    seen: set[str] = set()
    for file in sorted(collection_dir.glob("*.txt")):
        text = file.read_text(encoding="utf-8", errors="ignore")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        kept: List[str] = []
        removed = 0
        for paragraph in paragraphs:
            normalized = " ".join(paragraph.split()).lower()
            if len(normalized) < min_chars:
                kept.append(paragraph)
                continue
            if normalized in seen:
                removed += 1
                continue
            seen.add(normalized)
            kept.append(paragraph)

        if removed:
            updated = "\n\n".join(kept).strip() + "\n"
            file.write_text(updated, encoding="utf-8")
            print(f"Deduped {file} (removed {removed} repeated paragraphs)")


if __name__ == "__main__":
    downloaded: Dict[str, str] = {}
    with httpx.Client(
        timeout=90.0,
        follow_redirects=True,
        headers={"User-Agent": "roman-senate-demo/1.0"},
    ) as client:
        for url, outputs in DOWNLOAD_PLAN.items():
            try:
                cleaned_text = downloaded.get(url)
                if cleaned_text is None:
                    cleaned_text = fetch_and_clean(client, url)
                    downloaded[url] = cleaned_text
            except Exception as exc:
                print(f"WARN: failed {url}: {exc}")
                continue

            for spec in outputs:
                rendered = _render_output(cleaned_text, spec)
                spec.out.parent.mkdir(parents=True, exist_ok=True)
                spec.out.write_text(rendered, encoding="utf-8")
                print(f"Saved {spec.out} ({len(rendered)} chars)")

    _dedupe_across_collection(ROOT / "data" / "caesar_docs")
    _dedupe_across_collection(ROOT / "data" / "pompey_docs")

    # Remove legacy noisy duplicates that were not reliable RAG sources.
    legacy_files = [
        ROOT / "data" / "caesar_docs" / "appian_civil_wars_pg28334_selected.txt",
        ROOT / "data" / "pompey_docs" / "appian_civil_wars_pg28334_selected.txt",
        ROOT / "data" / "caesar_docs" / "caesar_commentaries_pg10657_selected.txt",
        ROOT / "data" / "pompey_docs" / "plutarch_lives_vol3_pg14140_selected.txt",
    ]
    for legacy in legacy_files:
        try:
            if legacy.exists():
                legacy.unlink()
                print(f"Removed legacy file: {legacy}")
        except Exception as exc:
            print(f"WARN: failed to remove legacy file {legacy}: {exc}")

    print("Done.")
