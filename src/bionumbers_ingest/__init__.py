"""Turns the published BioNumbers export into a JSONL corpus, with provenance.

The export is a single HTML ``<table>`` published with an ``.xls`` extension.
This package reads it, resolves the notations and injected markup it actually
contains, and writes one JSON object per data row — so a reader produces a
corpus from the public source rather than being handed one.

Read as a pipeline whose two ends are the only modules that know a file format:
the HTML reader in and the JSONL writer out. Nothing between them knows either.
"""
