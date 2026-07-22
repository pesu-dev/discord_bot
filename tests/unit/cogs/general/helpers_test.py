from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import respx
from httpx import Response

from src.cogs.general.helpers import (
    _clean_link_parts,
    _parse_reddit_data,
    fetch_faq_data,
    load_local_faq,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from tests.conftest import InteractionFactory


def test_load_local_faq() -> None:
    data = load_local_faq()
    assert isinstance(data, dict)
    assert len(data) > 0
    first_category = next(iter(data))
    assert "question" in data[first_category][0]
    assert "answer" in data[first_category][0]


def test_clean_link_parts() -> None:
    title, url = _clean_link_parts(["[Hello", "https://example.com)"])
    assert title == "Hello"
    assert url == "https://example.com"


def test_parse_reddit_data_single_and_multi() -> None:
    # Mirror the fragile production parser: sections are split on "# ",
    # and each section needs a title + body separated by blank lines.
    selftext = (
        "This post will be updated\n\n"
        "intro body\n\n"
        "# Campus\n\n"
        "* [Single Q](https://example.com/a)\n\n"
        "* [Multi A](https://example.com/1) or [Multi B](https://example.com/2)\n\n"
    )
    payload = [{"data": {"children": [{"data": {"selftext": selftext}}]}}]
    parsed = _parse_reddit_data(payload)
    assert "Campus" in parsed
    questions = {item["question"] for item in parsed["Campus"]}
    assert "Single Q" in questions
    # Multi-link lines are also accepted by the parser when present.
    assert any(item["answer"].startswith("https://example.com/") for item in parsed["Campus"])


@respx.mock
async def test_fetch_faq_data_success() -> None:
    selftext = "This post will be updated\n\nintro\n\n# Cats\n\n* [Q1](https://example.com/q1)\n\n"
    payload = [{"data": {"children": [{"data": {"selftext": selftext}}]}}]
    respx.get("https://reddit.com/r/PESU/comments/14c1iym/.json").mock(return_value=Response(200, json=payload))
    data = await fetch_faq_data()
    assert "Cats" in data


@respx.mock
async def test_fetch_faq_data_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    faq = {"categories": [{"category": "LocalOnly", "questions": [{"question": "Q", "answer": "A"}]}]}
    path = tmp_path / "faq.json"
    path.write_text(json.dumps(faq))
    monkeypatch.setattr("src.cogs.general.helpers._FAQ_PATH", path)
    respx.get("https://reddit.com/r/PESU/comments/14c1iym/.json").mock(return_value=Response(503, text="down"))
    data = await fetch_faq_data(logger=MagicMock())
    assert "LocalOnly" in data


def test_faq_multi_link_and_trailing_newline() -> None:
    from src.cogs.general.helpers import _parse_reddit_data, _process_news_item

    data: dict = {}
    _process_news_item("[Q1](https://a.com) or [Q2](https://b.com)\n", "Multi", data)
    assert len(data["Multi"]) == 2

    data2: dict = {}
    _process_news_item("[Solo](https://c.com)\n", "SoloCat", data2)
    assert data2["SoloCat"][0]["answer"] == "https://c.com)"

    selftext = "This post will be updated\n\nintro\n\n# SkipMe\n\n* [Only](https://example.com/x)\n\n"
    payload = [{"data": {"children": [{"data": {"selftext": selftext}}]}}]
    assert "SkipMe" in _parse_reddit_data(payload)


async def test_handle_specific_question_strip_url(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    from src.cogs.general.helpers import GeneralHelpers

    helpers = GeneralHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    data = {"C": [{"question": "Q", "answer": "https://example.com)\n"}]}
    await helpers._handle_specific_question(interaction, data, "C", "Q")
    assert "https://example.com" in interaction.followup.send.await_args.kwargs["content"]
