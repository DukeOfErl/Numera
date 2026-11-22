"""Grounded conversational access to a corpus of biological quantities.

The agent answers natural-language questions using only entries it retrieved,
citing every quantity. It is driven through an event/command port (ports and
adapters), so a terminal, a web interface, and the evaluation harness are three
adapters over one agent rather than three modes inside it.
"""
