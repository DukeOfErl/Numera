"""Where the pipeline writes, and why it is under `data/`.

Fetched article XML and search responses go under `EUROPEPMC_DIR`; a run's claims, rejected
candidates, states and spend go under `RUNS_DIR/<run-id>/`. Both sit under `data/`, which
`.gitignore` covers at the root, and `tests/test_bionumbers_paths.py` asks git directly that they
stay ignored. A run file carries paper text: openly licensed, but a committed 100 kB of someone
else's article is a mistake this project has already spent a guard on (ADR-0170, ADR-0250), so the
writers also pass through `bionumbers_ingest.guard` rather than trusting this file.
"""

from __future__ import annotations

from pathlib import Path

EUROPEPMC_DIR = Path("data/europepmc")
"""Disk cache of Europe PMC searches and full-text XML, keyed by identifier and version."""

RUNS_DIR = Path("data/runs")
"""One directory per run id: the JSONL files a run writes before anything reaches Postgres."""
