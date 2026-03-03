from __future__ import annotations

import unittest

from bot.validation import validate_intro_text


EXAMPLE_INTRO_TEXT = (
    "Who are you & what do you do?\n"
    "I am Aisyah, a frontend developer building web apps for early-stage startups.\n\n"
    "Where are you based?\n"
    "Kuala Lumpur, Malaysia.\n\n"
    "One fun fact about you\n"
    "I can solve a Rubik's Cube in under one minute.\n\n"
    "How are you looking to contribute to Superteam MY?\n"
    "I want to help local builders ship better UX and contribute to community hack projects."
)


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

    # ---- anti copy-paste tests ----

    def test_rejects_verbatim_example(self) -> None:
        """Exact copy-paste of the example intro must be rejected."""
        result = validate_intro_text(
            text=EXAMPLE_INTRO_TEXT,
            min_words=20,
            min_words_with_signals=12,
        )
        self.assertFalse(result.is_valid)
        self.assertIn("too similar to the example", result.reason)

    def test_rejects_example_with_minor_edits(self) -> None:
        """Copy-paste with only the name swapped should still be rejected."""
        text = (
            "Who are you & what do you do?\n"
            "I am John, a frontend developer building web apps for early-stage startups.\n\n"
            "Where are you based?\n"
            "Kuala Lumpur, Malaysia.\n\n"
            "One fun fact about you\n"
            "I can solve a Rubik's Cube in under one minute.\n\n"
            "How are you looking to contribute to Superteam MY?\n"
            "I want to help local builders ship better UX and contribute to community hack projects."
        )
        result = validate_intro_text(
            text=text,
            min_words=20,
            min_words_with_signals=12,
        )
        self.assertFalse(result.is_valid)
        self.assertIn("too similar to the example", result.reason)

    def test_accepts_original_content_using_same_format(self) -> None:
        """Original answers with the same question headers should be accepted."""
        text = (
            "Who are you & what do you do?\n"
            "My name is Ahmad and I run a small data analytics consultancy in Southeast Asia.\n\n"
            "Where are you based?\n"
            "Penang, Malaysia.\n\n"
            "One fun fact about you\n"
            "I once hiked the entire length of the Appalachian Trail in five months.\n\n"
            "How are you looking to contribute to Superteam MY?\n"
            "I would love to help with on-chain analytics dashboards and mentoring new developers."
        )
        result = validate_intro_text(
            text=text,
            min_words=20,
            min_words_with_signals=12,
        )
        self.assertTrue(result.is_valid)

    # ---- anti bot-message / non-intro text tests ----

    def test_rejects_copied_bot_diagnostics(self) -> None:
        """Copying bot output (diagnostics) must not pass validation."""
        text = (
            "Diagnostics:\n"
            "- Bot id: 8614044134\n"
            "- Bot username: @test_telegram_gating_bot\n"
            "- Privacy mode: OFF (good)\n"
            "- Bot member status in main group: administrator\n"
            "- can_delete_messages: True\n"
            "- can_restrict_members: True\n"
            "- MAIN_GROUP_ID: -1003868839262\n"
            "- INTRO_CHAT_ID: -1003868839262\n"
            "- INTRO_THREAD_ID: 4"
        )
        result = validate_intro_text(text, min_words=20, min_words_with_signals=12)
        self.assertFalse(result.is_valid)
        self.assertIn("self-introduction", result.reason)

    def test_rejects_copied_bot_announcement(self) -> None:
        """Copying bot output like acceptance announcements should be rejected."""
        text = (
            "Intro accepted in the topic. Main-group access unlocked. "
            "The bot has verified the introduction and granted full permissions "
            "to post in all channels of this Telegram supergroup."
        )
        result = validate_intro_text(text, min_words=20, min_words_with_signals=12)
        self.assertFalse(result.is_valid)
        self.assertIn("self-introduction", result.reason)

    def test_rejects_random_long_text_without_self_reference(self) -> None:
        """Long text that never references 'I' / 'my' / 'me' should be rejected."""
        text = (
            "The weather today is quite pleasant and the temperature "
            "has dropped significantly since yesterday afternoon making "
            "the whole neighborhood feel very comfortable and relaxed."
        )
        result = validate_intro_text(text, min_words=20, min_words_with_signals=12)
        self.assertFalse(result.is_valid)
        self.assertIn("self-introduction", result.reason)


if __name__ == "__main__":
    unittest.main()
