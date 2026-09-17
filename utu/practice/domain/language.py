"""Language contracts for generated experience prose."""

from __future__ import annotations

import re

from .contracts import ExperienceOutputLanguage


def experience_output_language_instruction(language: ExperienceOutputLanguage | str) -> str:
    """Return the prompt contract for persisted experience prose."""

    if language == "english":
        return (
            "Write all generated summaries, experience content, reasons, and structured "
            "text fields in English. Preserve mathematical notation and identifiers exactly "
            "when needed, but translate explanatory prose and transliterate names into English."
        )
    if language == "same_as_input":
        return "Use the same language as the input trajectory and supplied experiences."
    raise ValueError(f"unsupported experience output language: {language!r}")


def validate_experience_output_language(
    text: str,
    language: ExperienceOutputLanguage | str,
    *,
    label: str = "experience content",
) -> None:
    """Reject CJK prose or symbol-only content in an English run."""

    experience_output_language_instruction(language)
    if language != "english":
        return

    cjk_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text))
    prose = re.sub(r"\\[A-Za-z]+", " ", text)
    prose = re.sub(r"[\$\{\}\[\]_\^\d]", " ", prose)
    latin = [char for char in prose if char.isascii() and char.isalpha()]
    if cjk_count or not latin:
        raise ValueError(
            f"{label} violates experience_output_language='english' "
            f"(cjk_characters={cjk_count}, latin_letters={len(latin)})"
        )
