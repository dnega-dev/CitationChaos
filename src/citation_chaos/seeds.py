"""Built-in starter corpus used by ``citation-chaos init``."""

from __future__ import annotations

from typing import Tuple

from .schemas import Answer, Citation, Claim, Corpus, Source, Span


STARTER_QUESTION = "What did the Metro Energy Board report about solar capacity and the pilot date?"


def starter_project() -> Tuple[Corpus, Answer, str]:
    capacity = Span(
        id="capacity",
        text="Installed solar capacity reached 240 MW in 2024.",
        start=0,
        end=49,
        page="3",
    )
    schedule = Span(
        id="schedule",
        text="The storage pilot begins on 2025-06-15.",
        start=50,
        end=91,
        page="4",
    )
    appendix = Span(
        id="appendix",
        text="The audited figures use nameplate capacity.",
        start=92,
        end=135,
        page="9",
    )
    board = Source(
        id="board-report",
        uri="https://example.invalid/metro-energy/annual-2024",
        title="Metro Energy Board 2024 Annual Report",
        spans=(capacity, schedule, appendix),
        sha256=Source.hash_spans((capacity, schedule, appendix)),
        kind="primary",
        published_at="2025-02-10",
    )
    glossary_span = Span(
        id="glossary-capacity",
        text="Nameplate capacity is the rated maximum output.",
        start=0,
        end=46,
        page="1",
    )
    glossary = Source(
        id="board-glossary",
        uri="https://example.invalid/metro-energy/glossary",
        title="Metro Energy Board Glossary",
        spans=(glossary_span,),
        sha256=Source.hash_spans((glossary_span,)),
        kind="primary",
        published_at="2024-12-01",
    )
    corpus = Corpus(
        id="metro-energy",
        version="1",
        sources=(board, glossary),
        metadata={"question": STARTER_QUESTION, "description": "Synthetic starter corpus"},
    )
    answer = Answer(
        status="answered",
        claims=(
            Claim(
                id="solar-capacity",
                text="Installed solar capacity reached 240 MW in 2024.",
                citations=(
                    Citation(
                        source_id="board-report",
                        span_id="capacity",
                        anchor="p.3",
                        quote=capacity.text,
                    ),
                ),
            ),
            Claim(
                id="pilot-date",
                text="The storage pilot begins on 2025-06-15.",
                citations=(
                    Citation(
                        source_id="board-report",
                        span_id="schedule",
                        anchor="p.4",
                        quote=schedule.text,
                    ),
                ),
            ),
        ),
        text=(
            "Installed solar capacity reached 240 MW in 2024. "
            "The storage pilot begins on 2025-06-15."
        ),
    )
    return corpus, answer, STARTER_QUESTION
