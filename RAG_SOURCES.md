# RAG Sources (Roman Senate Demo)

This file documents all sources currently used by the RAG corpora in `data/`.
Last refresh: 2026-03-05.

## Processing Rules

- All external texts are fetched via `scripts/fetch_public_domain_sources.py`.
- Project Gutenberg boilerplate is stripped.
- Sections are trimmed by marker boundaries (to keep relevant chapters only).
- Keyword-focused filtering keeps Roman late-republic context.
- Repeated paragraphs are deduplicated within each file and across each corpus (`caesar_docs`, `pompey_docs`).
- Legacy noisy duplicates are removed automatically.

## Public-Domain English Sources

| Source | URL | Why included | Output files |
|---|---|---|---|
| Julius Caesar, *De Bello Gallico* and *Civil War* (PG 10657) | https://www.gutenberg.org/ebooks/10657.txt.utf-8 | Core primary narrative for Caesar's campaigns and civil war context. | `data/caesar_docs/caesar_commentaries_pg10657_full.txt`  `data/pompey_docs/caesar_commentaries_pg10657_civil_war_context.txt` |
| Suetonius, *The Lives of the Twelve Caesars* (PG 6400) | https://www.gutenberg.org/ebooks/6400.txt.utf-8 | Biographical context for Julius Caesar (personality, politics, elite networks). | `data/caesar_docs/suetonius_twelve_caesars_pg6400.txt` |
| Lucan, *Pharsalia* (PG 602) | https://www.gutenberg.org/ebooks/602.txt.utf-8 | Civil-war framing and rhetoric (Caesar vs Pompey conflict literature). | `data/caesar_docs/lucan_pharsalia_pg602_caesar_context.txt`  `data/pompey_docs/lucan_pharsalia_pg602_pompey_context.txt` |
| Plutarch, *Parallel Lives* omnibus (PG 674) | https://www.gutenberg.org/ebooks/674.txt.utf-8 | Targeted extraction of *Pompey* and *Caesar* sections from one source text. | `data/caesar_docs/plutarch_lives_pg674_caesar_context.txt`  `data/pompey_docs/plutarch_lives_pg674_pompey_context.txt` |
| Plutarch, *Lives, Vol. III* (PG 14140) | https://www.gutenberg.org/ebooks/14140.txt.utf-8 | Dedicated Pompeius section with tighter historical-biographical detail. | `data/pompey_docs/plutarch_lives_vol3_pg14140_full.txt` |
| Plutarch, *Lives, Vol. II* (PG 14114) | https://www.gutenberg.org/ebooks/14114.txt.utf-8 | Late-republic Roman context around figures relevant to Pompey-era debates. | `data/pompey_docs/plutarch_lives_vol2_pg14114_pompey_context.txt` |
| Cicero, *Letters to Atticus*, Vol. 1 (PG 58418) | https://www.gutenberg.org/ebooks/58418.txt.utf-8 | Political correspondence and elite decision context in the late republic. | `data/pompey_docs/cicero_letters_to_atticus_vol1_pg58418.txt` |
| Cicero, *Letters to Atticus*, Vol. 2 (PG 50692) | https://www.gutenberg.org/ebooks/50692.txt.utf-8 | Continuation of high-signal political letters around Caesar/Pompey dynamics. | `data/pompey_docs/cicero_letters_to_atticus_vol2_pg50692.txt` |
| Cicero, *Letters to Atticus*, Vol. 3 (PG 51403) | https://www.gutenberg.org/ebooks/51403.txt.utf-8 | Later-phase correspondence with direct civil-war and post-war relevance. | `data/pompey_docs/cicero_letters_to_atticus_vol3_pg51403.txt` |

## Local Authored Fallback Notes

These are short local fallback notes, used when external sources are unavailable.

| File | Purpose |
|---|---|
| `data/caesar_docs/sample_caesar_notes.txt` | Compact strategic framing for Caesar-side argument style. |
| `data/pompey_docs/sample_pompey_notes.txt` | Compact strategic framing for Pompey-side argument style. |
| `data/pompey_docs/sample_senate_law_notes.txt` | Compact constitutional/legal context for moderator and Pompey-side legal arguments. |

## Removed Legacy Files

These are intentionally removed by the fetch script to avoid noisy or duplicated material:

- `data/caesar_docs/appian_civil_wars_pg28334_selected.txt`
- `data/pompey_docs/appian_civil_wars_pg28334_selected.txt`
- `data/caesar_docs/caesar_commentaries_pg10657_selected.txt`
- `data/pompey_docs/plutarch_lives_vol3_pg14140_selected.txt`

