from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import discord
import httpx

from src.utils import general as ug

if TYPE_CHECKING:
    import logging

    from src.bot import DiscordBot

_FAQ_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "faq.json"
_REDDIT_URL = "https://reddit.com/r/PESU/comments/14c1iym/.json"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",  # noqa: E501
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept": "*/*",
    "Connection": "keep-alive",
}


async def fetch_faq_data(logger: logging.Logger | None = None) -> dict:
    """Fetch FAQ data from Reddit, falling back to the local snapshot on failure."""
    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        response = await client.get(_REDDIT_URL)
        if response.status_code == 200:
            return _parse_reddit_data(response.json())

        if logger is not None:
            logger.warning(f"Failed to fetch data: {response.status_code}, falling back to local data. {response.text}")
        return load_local_faq()


def load_local_faq() -> dict:
    with open(_FAQ_PATH) as file:
        raw = json.load(file)

    data: dict = {}
    for category in raw.get("categories", []):
        name = category["category"]
        entries = data.setdefault(name, [])
        for item in category.get("questions", []):
            entries.append({"question": item["question"], "answer": item["answer"]})
    return data


def _parse_reddit_data(data: dict) -> dict:
    x = data[0]["data"]["children"][0]["data"]["selftext"]
    finedata: dict = {}
    y = x.split("# ")

    for i in y:
        j = i.split("\n\n")
        if "This post will be" in j[0]:
            continue

        s = j[1].split("* ")
        news = list(filter(None, s))

        for item in news:
            _process_news_item(item, j[0], finedata)

    return finedata


def _process_news_item(item: str, category: str, finedata: dict) -> None:
    if ") or [" in item:
        _process_multiple_links(item, category, finedata)
    else:
        _process_single_link(item, category, finedata)


def _process_multiple_links(item: str, category: str, finedata: dict) -> None:
    chakdeh = item.split(") or [")
    for link_part in chakdeh:
        link_parts = link_part.split("](")
        title, url = _clean_link_parts(link_parts)
        finedata.setdefault(category, []).append({"question": title, "answer": url})


def _process_single_link(item: str, category: str, finedata: dict) -> None:
    chakdeh = item.split("](")
    title, url = _clean_link_parts(chakdeh)
    if url.endswith("\n"):
        url = url[:-1]
    finedata.setdefault(category, []).append({"question": title, "answer": url})


def _clean_link_parts(parts: list) -> tuple[str, str]:
    title, url = parts[0], parts[1]
    if title.startswith("["):
        title = title[1:]
    if url.endswith(")"):
        url = url[:-1]
    return title, url


class GeneralHelpers:
    client: DiscordBot
    cached_data: dict | None

    async def get_data(self) -> dict:
        if not self.cached_data:
            self.cached_data = await fetch_faq_data(self.client.logger)
        return self.cached_data

    async def _handle_category_only(self, interaction: discord.Interaction, data: dict, category: str) -> None:
        questions = []
        for entry in data[category]:
            question = entry["question"]
            answer = entry["answer"]
            if answer.endswith(")") or question.endswith("\n"):
                answer = answer[:-1]
            questions.append(f"[{question}]({answer})")

        if questions:
            embed = ug.build_embed(
                title=f"FAQ - {category}",
                color=discord.Color.blurple(),
                description="\n\n".join(questions),
            )
            await interaction.followup.send(embed=embed)
        else:
            embed = ug.build_embed(
                title="FAQ",
                color=discord.Color.red(),
                description="No questions found in this category",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def _handle_specific_question(
        self,
        interaction: discord.Interaction,
        data: dict,
        category: str,
        question: str,
    ) -> None:
        for entry in data[category]:
            if entry["question"] == question:
                url = entry["answer"]
                if url.endswith(")") or url.endswith("\n"):
                    url = url[:-1]
                await interaction.followup.send(content=f"[{question}]({url})", ephemeral=False)
                return

        await interaction.followup.send(content="Question not found in the selected category", ephemeral=True)
