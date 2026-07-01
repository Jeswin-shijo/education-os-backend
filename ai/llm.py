"""Pluggable LLM interface + canned, feature-specific fallback.

This module is the single seam where a real LLM can be wired in later. Today it
ships a deterministic, feature-specific *canned* generator that mirrors the
mobile app's ``aiService.buildResponse`` output, so the AI endpoints work with
**no LLM API key** configured.

Design:

- :data:`LLM_PROVIDER` is a module-level callable
  ``(feature: str, prompt: str, *, history=None) -> str``. It defaults to the
  canned fallback :func:`canned_response`.
- To plug a real model, call :func:`set_llm_provider` (e.g. from an app-ready
  hook or settings) with a function that calls your provider of choice; if it
  raises, :func:`generate` falls back to the canned response so requests never
  hard-fail on provider errors.
- :func:`generate` is what the service/Celery task call. It never raises on
  provider failure — it degrades to canned text.

Keeping the provider abstract (a plain callable) means the ``ai`` app has **no
hard dependency** on any particular SDK; the concrete integration lives wherever
:func:`set_llm_provider` is invoked.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, Sequence

logger = logging.getLogger(__name__)

# Type of a provider: (feature, prompt, history) -> assistant text.
LLMProvider = Callable[..., str]


# --- Canned, feature-specific fallback --------------------------------------
def canned_response(feature: str, prompt: str, *, history=None) -> str:
    """Deterministic, feature-specific reply mirroring the app's aiService.

    ``history`` is accepted (and ignored) so this has the same signature as a
    real provider. Returns plain text/markdown, exactly like the mobile mock.
    """
    topic = (prompt or "").strip() or "this topic"

    if feature == "doubt":
        return "\n".join(
            [
                f'Let\'s solve "{topic}" step by step:',
                "",
                "1. Identify what is being asked and the relevant concept.",
                "2. Recall the governing rule or formula.",
                "3. Apply it carefully to the given values.",
                "4. Simplify and double-check each step.",
                "",
                "Worked idea: break the problem into smaller parts, solve each, "
                "then combine. For example, differentiating term by term: "
                "d/dx[sin(x) - cos(x)] = cos(x) + sin(x).",
                "",
                "Tip: practise 2-3 similar problems to lock in the method.",
            ]
        )

    if feature == "notes":
        return "\n".join(
            [
                f"# Notes - {topic}",
                "",
                "Key points:",
                f"- Definition: a concise explanation of {topic}.",
                "- Core concepts: the main ideas you must remember.",
                "- Why it matters: where this is applied in practice.",
                "",
                "Important terms:",
                "- Term 1 - short meaning.",
                "- Term 2 - short meaning.",
                "",
                "Quick revision:",
                "- Summarise in one line.",
                "- Recall one example.",
                "- Note one common mistake to avoid.",
            ]
        )

    if feature == "mentor":
        return "\n".join(
            [
                f'Great question about "{topic}". Here\'s how I\'d approach it '
                "as your mentor:",
                "",
                "- Focus first on subjects where your attendance or marks are "
                "weakest.",
                "- Block 2 focused study sessions daily and review notes the "
                "same evening.",
                "- Attempt past internal papers under timed conditions before "
                "IA-II.",
                "",
                "You are doing well overall (CGPA 8.4). Stay consistent and ask "
                "for help early. I can build a day-by-day plan if you like.",
            ]
        )

    if feature == "assignment":
        return "\n".join(
            [
                f'Here\'s a suggested structure for "{topic}":',
                "",
                "1. Introduction & problem statement",
                "2. Background / theory",
                "3. Approach or methodology",
                "4. Implementation / analysis",
                "5. Results & discussion",
                "6. Conclusion & references",
                "",
                "Remember to cite your sources and add diagrams where helpful.",
            ]
        )

    if feature == "resume":
        return "\n".join(
            [
                f'Feedback on "{topic}":',
                "",
                "- Lead each bullet with an action verb and quantify impact.",
                "- Highlight your hackathon runner-up and key projects near the "
                "top.",
                "- Group skills (Languages, Frameworks, Tools) for quick "
                "scanning.",
                "- Keep it to one page; remove generic objective statements.",
            ]
        )

    if feature == "career":
        return "\n".join(
            [
                f'Career guidance on "{topic}":',
                "",
                "- Strengthen DSA and core CS fundamentals for product "
                "companies.",
                "- Build 2-3 portfolio projects that match your target role.",
                "- Practise mock interviews and revise OS, DBMS, CN before "
                "drives.",
                "- Companies like Zoho and Freshworks value strong "
                "problem-solving.",
            ]
        )

    # chat + any unknown feature -> generic assistant reply.
    return "\n".join(
        [
            f'Here\'s what I found about "{topic}":',
            "",
            "I can help with your classes, attendance, assignments, exams, fees "
            "and more. Ask me anything about your campus life and I will pull "
            "the relevant details.",
        ]
    )


# --- Pluggable provider registry --------------------------------------------
# Defaults to the canned fallback so the app works with no LLM key.
LLM_PROVIDER: LLMProvider = canned_response


def set_llm_provider(provider: Optional[LLMProvider]) -> None:
    """Install a real LLM provider (or reset to canned when ``None``).

    ``provider`` must be callable as ``provider(feature, prompt, history=...)``
    and return the assistant text. Wire your concrete SDK here from a startup
    hook or settings loader; nothing else in the app changes.
    """
    global LLM_PROVIDER
    LLM_PROVIDER = provider or canned_response


def generate(
    feature: str,
    prompt: str,
    *,
    history: Optional[Sequence[dict]] = None,
) -> str:
    """Produce an assistant reply for ``feature``/``prompt``.

    Calls the installed :data:`LLM_PROVIDER`; on any provider error, logs and
    degrades to :func:`canned_response` so requests never hard-fail. ``history``
    is an optional list of prior turns (``[{"role", "text"}, ...]``) a real
    provider may use for context.
    """
    provider = LLM_PROVIDER
    try:
        return provider(feature, prompt, history=history)
    except TypeError:
        # Provider without a history kwarg -> call positionally.
        try:
            return provider(feature, prompt)
        except Exception:  # pragma: no cover - defensive
            logger.exception("LLM provider failed; using canned fallback")
            return canned_response(feature, prompt, history=history)
    except Exception:  # pragma: no cover - defensive
        logger.exception("LLM provider failed; using canned fallback")
        return canned_response(feature, prompt, history=history)


# --- Static quick-prompt chips (client contract; served by GET suggestions) --
SUGGESTIONS = {
    "mentor": [
        "How do I improve my CGPA?",
        "Plan my week for IA-II prep",
        "My OS attendance is low, what do I do?",
        "Which electives suit a backend career?",
    ],
    "doubt": [
        "Derivative of sin(x) - cos(x)",
        "Explain deadlock with an example",
        "Difference between BFS and DFS",
        "What is normalization in DBMS?",
    ],
    "notes": [
        "CPU Scheduling Algorithms",
        "Normalization in DBMS",
        "TCP/IP Reference Model",
        "AVL Tree Rotations",
    ],
    "assignment": [
        "Outline a report on Graph Traversal",
        "Structure my AVL tree assignment",
        "Suggest references for subnetting",
    ],
    "resume": [
        "Review my resume bullet points",
        "How to highlight my hackathon win?",
        "What skills should I add for SDE roles?",
    ],
    "career": [
        "Backend developer roadmap",
        "How to prepare for Zoho interview?",
        "Higher studies vs placement?",
    ],
    "chat": [
        "When is my next exam?",
        "Show today's classes",
        "How much fee is due?",
    ],
}
