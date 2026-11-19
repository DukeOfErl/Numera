"""The validator: from a property question to reviewed numbers.

A fixed pipeline, not an agent (ADR-1520): discovery finds open-access research articles, one
extraction call per paper produces verbatim-quoted claims, a mechanical checker verifies every
quote, and a person decides. Core modules import no Streamlit and nothing from `numera_ask`;
only `deployment.py` and the root `review_app.py` may.
"""
