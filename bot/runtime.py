from __future__ import annotations

from dataclasses import dataclass

from telegram.ext import ContextTypes

from .config import Config
from .database import MemberRepository


@dataclass(slots=True)
class Runtime:
    config: Config
    repo: MemberRepository


def get_runtime(context: ContextTypes.DEFAULT_TYPE) -> Runtime:
    runtime = context.application.bot_data.get("runtime")
    if runtime is None:
        raise RuntimeError("runtime is not initialized")
    return runtime
