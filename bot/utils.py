from __future__ import annotations

import html

from telegram import ChatPermissions, Message

from .validation import validate_intro_text


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

INTRO_FORMAT_PROMPT = (
    "Please introduce yourself in Intro using this structure:\n\n"
    "1) Who are you & what do you do?\n"
    "2) Where are you based?\n"
    "3) One fun fact about you\n"
    "4) How are you looking to contribute to Superteam MY?\n\n"
    "You can use /example to see a sample intro."
)

MUTED_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)

UNMUTED_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)


def extract_message_text(message: Message) -> str:
    if message.text:
        return message.text.strip()
    if message.caption:
        return message.caption.strip()
    return ""


def mention_html(user_id: int, display_name: str) -> str:
    escaped = html.escape(display_name)
    return f'<a href="tg://user?id={user_id}">{escaped}</a>'


def display_name(username: str | None, first_name: str | None, user_id: int) -> str:
    if first_name:
        return first_name
    if username:
        return username
    return str(user_id)


def build_intro_deeplink(intro_chat_id: int, intro_thread_id: int | None) -> str | None:
    if intro_thread_id is None:
        return None
    abs_chat_id = str(abs(intro_chat_id))
    internal_chat_id = abs_chat_id[3:] if abs_chat_id.startswith("100") else abs_chat_id
    return f"https://t.me/c/{internal_chat_id}/{intro_thread_id}"


def format_intro_location(intro_chat_id: int, intro_thread_id: int | None) -> str:
    if intro_thread_id is not None:
        return f"#intro topic (chat ID: {intro_chat_id}, topic ID: {intro_thread_id})"
    return f"#intro chat (chat ID: {intro_chat_id})"


def build_welcome_text(intro_chat_id: int, intro_thread_id: int | None) -> str:
    intro_link = build_intro_deeplink(intro_chat_id, intro_thread_id)
    if intro_link:
        return (
            "👋 Welcome to Superteam MY. You are temporarily limited in the main group until your intro is done.\n\n"
            "Post your introduction in the Intro topic to unlock access.\n\n"
            f"🔗 Open Intro directly: {intro_link}\n\n"
            "Please introduce yourself in Intro using this structure:\n\n"
            "1) Who are you & what do you do?\n"
            "2) Where are you based?\n"
            "3) One fun fact about you\n"
            "4) How are you looking to contribute to Superteam MY?\n\n"
            "You can use /example to see a sample intro."
        )

    intro_location = format_intro_location(intro_chat_id, intro_thread_id)
    return (
        "👋 Welcome to Superteam MY. You are temporarily limited in the main group until your intro is done.\n\n"
        f"Post your intro in {intro_location} to unlock access.\n\n"
        f"{INTRO_FORMAT_PROMPT}"
    )


def build_reminder_text(intro_chat_id: int, intro_thread_id: int | None) -> str:
    intro_link = build_intro_deeplink(intro_chat_id, intro_thread_id)
    if intro_link:
        return (
            "🔒 Reminder: your main-group access is still locked.\n"
            "Please post your introduction in the Intro topic.\n\n"
            f"🔗 Open Intro directly: {intro_link}\n\n"
            "Please introduce yourself in Intro using this structure:\n\n"
            "1) Who are you & what do you do?\n"
            "2) Where are you based?\n"
            "3) One fun fact about you\n"
            "4) How are you looking to contribute to Superteam MY?\n\n"
            "You can use /example to see a sample intro."
        )

    intro_location = format_intro_location(intro_chat_id, intro_thread_id)
    return (
        "🔒 Reminder: your main-group access is still locked.\n"
        f"Please post your intro in {intro_location}.\n\n"
        f"{INTRO_FORMAT_PROMPT}"
    )
