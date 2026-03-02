from __future__ import annotations

import unittest

from bot.validation import validate_intro_text


class IntroValidationTests(unittest.TestCase):
    def test_rejects_too_short_intro(self) -> None:
        result = validate_intro_text(
            text="Hi all",
            min_words=20,
            min_words_with_signals=12,
        )
        self.assertFalse(result.is_valid)

    def test_accepts_long_intro(self) -> None:
        text = (
            "Hi everyone, I am Aisyah and I work as a frontend developer in Kuala Lumpur. "
            "I build internal tools for startups and love community events on weekends."
        )
        result = validate_intro_text(
            text=text,
            min_words=20,
            min_words_with_signals=12,
        )
        self.assertTrue(result.is_valid)

    def test_accepts_mid_length_intro_with_signals(self) -> None:
        text = "I am Sarah, I work as a designer and build brand systems for community projects in Malaysia."
        result = validate_intro_text(
            text=text,
            min_words=20,
            min_words_with_signals=12,
        )
        self.assertTrue(result.is_valid)


if __name__ == "__main__":
    unittest.main()
