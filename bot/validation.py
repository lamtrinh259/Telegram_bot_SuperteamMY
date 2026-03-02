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

    if word_count >= min_words:
        return IntroValidationResult(is_valid=True, reason="Looks good.", word_count=word_count)

    word_set = set(words)
    has_self_signal = bool(word_set.intersection(SELF_WORDS))
    has_role_signal = bool(word_set.intersection(ROLE_WORDS))

    if word_count >= min_words_with_signals and has_self_signal and has_role_signal:
        return IntroValidationResult(is_valid=True, reason="Looks good.", word_count=word_count)

    return IntroValidationResult(
        is_valid=False,
        reason=(
            "Please add more detail about who you are and what you do "
            f"(current length: {word_count} words)."
        ),
        word_count=word_count,
    )
