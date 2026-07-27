"""Trusted adapter-file example for Citation Chaos.

Replace ``your_pipeline`` with your own retrieval/generation entry point.  This
example delegates to the structural reference adapter so the seeded demo is
fully deterministic.
"""

from citation_chaos.adapters import ReferenceAdapter


_adapter = ReferenceAdapter()


def run_pipeline(question, corpus):
    """Return either an Answer or an Answer-compatible mapping."""

    return _adapter.run(question, corpus)
