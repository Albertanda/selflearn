"""Subject-scoped learning features (M1–M8).

This package owns the fork's subject layer: the per-subject data tree
(``store``), the wrong-question book, exam points, the knowledge-point index,
the learner profile, and lecture exam-point detection.
"""

from __future__ import annotations

#: Generation budget for the subject-feature LLM calls (M3 grading, M4
#: detection, M6 review guides, M7 reports).
#:
#: These calls target instruction models, but the everyday model may be a
#: *reasoning* model (e.g. DeepSeek ``deepseek-flash``), whose chain-of-thought
#: tokens are billed against the same ``max_tokens`` budget as the answer. The
#: generic 4096 default is small enough that a long generation finishes with
#: ``finish_reason="length"`` and an EMPTY ``content`` — which used to render a
#: blank PDF while reporting success. Reasoning length varies run to run, so a
#: 4096 budget fails *intermittently*; 16000 leaves room for reasoning plus the
#: full answer in every case observed.
LLM_MAX_TOKENS = 16000

__all__ = ("LLM_MAX_TOKENS",)
