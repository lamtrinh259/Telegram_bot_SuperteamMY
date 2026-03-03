from __future__ import annotations

import re
from dataclasses import dataclass


SELF_WORDS = {
    "i",
    "im",
    "i'm",
    "my",
    "me",
    "myself",
}

ROLE_WORDS = {
    "work",
    "working",
    "build",
    "building",
    "developer",
    "engineer",
    "designer",
    "marketer",
    "student",
    "founder",
    "freelancer",
    "contribute",
    "creator",
    "operator",
    "product",
    "backend",
    "frontend",
}

# Answer lines from the example intro that users should NOT copy verbatim.
# Question/header lines are excluded — only the sample *answers* matter.
_EXAMPLE_ANSWER_LINES = [
    "I am Aisyah, a frontend developer building web apps for early-stage startups.",
    "Kuala Lumpur, Malaysia.",
    "I can solve a Rubik's Cube in under one minute.",
    "I want to help local builders ship better UX and contribute to community hack projects.",
]

_EXAMPLE_TRIGRAMS: set[tuple[str, ...]] | None = None


def _get_example_trigrams() -> set[tuple[str, ...]]:
    """Lazily build trigrams from example answer lines."""
    global _EXAMPLE_TRIGRAMS  # noqa: PLW0603
    if _EXAMPLE_TRIGRAMS is not None:
        return _EXAMPLE_TRIGRAMS

    combined = " ".join(_EXAMPLE_ANSWER_LINES).lower()
    words = re.findall(r"[a-z0-9']+", combined)
    trigrams: set[tuple[str, ...]] = set()
    for i in range(len(words) - 2):
        trigrams.add((words[i], words[i + 1], words[i + 2]))
    _EXAMPLE_TRIGRAMS = trigrams
    return _EXAMPLE_TRIGRAMS


def _is_copy_of_example(words: list[str], threshold: float = 0.45) -> bool:
    """Return True if the text's trigrams overlap too much with the example answers.

    A threshold of 0.45 means >45% of the user's trigrams also appear in the
    example answers — a strong signal of copy-paste.  Users who only keep the
    question headers (~25-30% overlap) will pass comfortably.
    """
    if len(words) < 3:
        return False

    example_trigrams = _get_example_trigrams()
    if not example_trigrams:
        return False

    user_trigrams = [
        (words[i], words[i + 1], words[i + 2]) for i in range(len(words) - 2)
    ]
    matching = sum(1 for t in user_trigrams if t in example_trigrams)
    ratio = matching / len(user_trigrams)
    return ratio > threshold


@dataclass(slots=True)
class IntroValidationResult:
    is_valid: bool
    reason: str
    word_count: int


def validate_intro_text(
    text: str,
    min_words: int,
    min_words_with_signals: int,
) -> IntroValidationResult:
    if not text.strip():
        return IntroValidationResult(
            is_valid=False,
            reason="Please write at least a short introduction about yourself.",
            word_count=0,
        )

    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    word_count = len(words)

    # ---- anti copy-paste check ----
    if _is_copy_of_example(words):
        return IntroValidationResult(
            is_valid=False,
            reason=(
                "Your intro looks too similar to the example. "
                "Please write your own introduction in your own words!"
            ),
            word_count=word_count,
        )

    # ---- signal detection ----
    word_set = set(words)
    has_self_signal = bool(word_set.intersection(SELF_WORDS))
    has_role_signal = bool(word_set.intersection(ROLE_WORDS))

    # A genuine self-introduction must reference yourself (I, my, me, etc.).
    # This rejects copy-pasted bot output, diagnostics, and random text that
    # may be long enough in word count but aren't actually about the user.
    if not has_self_signal:
        return IntroValidationResult(
            is_valid=False,
            reason=(
                "Your message doesn't look like a self-introduction. "
                "Please tell us about yourself — use \"I\", \"my\", etc."
            ),
            word_count=word_count,
        )

    # ---- length / signal checks ----
    if word_count >= min_words:
        return IntroValidationResult(is_valid=True, reason="Looks good.", word_count=word_count)

    if word_count >= min_words_with_signals and has_role_signal:
        return IntroValidationResult(is_valid=True, reason="Looks good.", word_count=word_count)

    return IntroValidationResult(
        is_valid=False,
        reason=(
            "Please add more detail about who you are and what you do "
            f"(current length: {word_count} words)."
        ),
        word_count=word_count,
    )
