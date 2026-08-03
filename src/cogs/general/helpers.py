from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import discord
import httpx

from src.data.mongo.link import Link
from src.data.mongo.student import Branch, Campus, Student
from src.utils import general as ug
from src.utils.config import Config

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


class LinkMessage(StrEnum):
    """Ephemeral reply strings for `/link` (dynamic auth errors may still return a raw str)."""

    AUTH_FAILED = "An error occurred while authenticating the PESU user"
    MISSING_PROFILE_FIELDS = "Missing fields from PESU Auth. Mods are notified and will get back to you soon."
    ONBOARDING_INCOMPLETE = "Onboarding incomplete. Follow the instructions below"
    UNRECOGNIZED_BRANCH = "Unrecognized branch. Mods are notified and will get back to you soon."
    MISSING_ROLES = "Missing role IDs for branch, campus, or year. Mods are notified and will get back to you soon."
    PRN_TAKEN = "PRN already linked with a different user. If you think this is a mistake, contact us."
    SUCCESS = "User linked successfully"


class LinkProfileError(Exception):
    """Raised when PESU auth cannot produce a usable link profile.

    ``message`` is always safe to show the user. ``detail`` is for error logs only
    (may contain upstream auth text); defaults to ``message``.
    """

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail if detail is not None else message
        super().__init__(message)


ONBOARDING_CHECKLIST = (
    "## PESU Discord Authentication Checklist ✅\n"
    "\n"
    "### New Student On-boarding [If you are joining *this* year] ℹ️\n"
    "\n"
    "1. Login to [PESU Academy](https://www.pesuacademy.com/Academy/). "
    "If your assigned credentials do not work, reset your password.\n"
    "2. You will be redirected to complete your student profile the *first* time you log in "
    "(find post-counseling instructions in your email). Fill out your details, log out and log back in. "
    "Visit the `Profile` page and ensure *all* your details load; you *should not* see any `NA`s "
    "or missing fields.\n"
    "    - If you are *not* auto-redirected, you will see a blank welcome screen and *no* `Profile` tab "
    "on the left sidebar. You can force a redirection by using the PESU Academy app and navigating "
    "to student grievances.\n"
    "\n"
    "### Test your Credentials ⚙️\n"
    "\n"
    "Before authenticating, let's check if your profile *can* be authenticated.\n"
    "\n"
    "1. Visit [PESUAuth](https://pesu-auth.onrender.com/). Click on `/authenticate`, and then on "
    "`Try it out`. Select `Authentication with Full Profile`.\n"
    "2. Enter the following in the request body under `Edit Value`, and click on `Execute`.\n"
    "```json\n"
    "{\n"
    '    "username": "PRN",\n'
    '    "password": "password",\n'
    '    "profile": true\n'
    "}\n"
    "```\n"
    "3. Check the response returned in the server response under `Response body`. "
    'If you can see `"status": true` and the `"profile"` field shows *all* your details, '
    "then you are ready to authenticate with this server.\n"
    "    - Specifically, check for these details: `branch`, `campus`, `PRN`, since we need these "
    "these fields. If you see any `NA`s, it means you have *not* completed on-boarding step (2). "
    "Come back to this step after finishing the previous section.\n"
    "\n"
    "If you are still unable to authenticate, DM <@543143780925177857> with screenshots/details "
    "on which step failed and the error you faced."
)


@dataclass(frozen=True, slots=True)
class PesuAuthProfile:
    """Profile object from pesu-auth `/authenticate` (https://github.com/pesu-dev/auth)."""

    name: str | None = None
    prn: str | None = None
    srn: str | None = None
    program: str | None = None
    branch: str | None = None
    semester: str | None = None
    section: str | None = None
    email: str | None = None
    phone: str | None = None
    campus_code: int | None = None
    campus: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        campus_code = data.get("campusCode", data.get("campus_code"))
        return cls(
            name=data.get("name"),
            prn=data.get("prn"),
            srn=data.get("srn"),
            program=data.get("program"),
            branch=data.get("branch"),
            semester=data.get("semester"),
            section=data.get("section"),
            email=data.get("email"),
            phone=data.get("phone"),
            campus_code=int(campus_code) if campus_code is not None else None,
            campus=data.get("campus"),
        )

    def missing_link_field(self) -> str | None:
        """Return the first required link field that is missing, else None."""
        required = {
            "prn": self.prn,
            "branch": self.branch,
            "campus": self.campus,
            "campusCode": self.campus_code,
        }
        for name, value in required.items():
            if value is None or value == "":
                return name
        return None

    def has_na_link_field(self) -> bool:
        """Return whether branch or campus is the incomplete-profile sentinel ``NA``."""
        return self.branch == "NA" or self.campus == "NA"


@dataclass(frozen=True, slots=True)
class PesuAuthResponse:
    """Response object from pesu-auth `/authenticate` (https://github.com/pesu-dev/auth)."""

    status: bool
    message: str
    profile: PesuAuthProfile | None = None
    timestamp: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        raw_profile = data.get("profile")
        profile = PesuAuthProfile.from_dict(raw_profile) if isinstance(raw_profile, dict) else None
        timestamp = data.get("timestamp")
        return cls(
            status=bool(data.get("status", False)),
            message=str(data.get("message") or data.get("error") or ""),
            profile=profile,
            timestamp=str(timestamp) if timestamp is not None else None,
        )


def _get_dm_message(
    branch: str,
    campus: str,
    year: str,
    *,
    lobby: discord.TextChannel,
) -> str:
    """Welcome DM text after a successful link (ported from auth-link-portal)."""
    return (
        "Welcome to our humble little server, where the linking process is more rigorous "
        "than getting a security clearance for Area 51. \n\n"
        f"**Roles added: `{branch}`, `{campus}` and `{year}`. If any of these details are inaccurate "
        f"or have changed, drop a message in {lobby.mention} and ping the admin or any moderators.**\n\n"
        f"Now, let's get to the good stuff - {lobby.mention} . This is where all the cool kids hang out. "
        "Or at least, that's what we tell ourselves as we cry ourselves to sleep every night. "
        "But hey, at least we have each other, right? If you're feeling brave, you can also run "
        "`/togglerole` and see if you're worthy of some extra roles and exclusive private channels.\n\n"
        "And if you ever find yourself hopelessly lost and confused, don't worry. Our online admin or "
        "moderators are here to help... or at least, they'll try to help. No promises on the quality of "
        "their assistance though - they're not exactly successful JEE aspirants.\n\n"
        "So buckle up, grab a drink, and let's have some fun. Or, you know, just sit back and watch the "
        "chaos unfold. Either way, we're happy to have you here!"
    )


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

    async def link_account(self, member: discord.Member, username: str, password: str) -> tuple[str, str | None]:
        """Run the full link flow. Never logs or stores ``password``.

        Returns:
            ``(message, followup)`` — send ``followup`` as a second ephemeral reply when not ``None``.
        """
        self._maybe_warn_non_prn(member, username)

        try:
            profile = await self._fetch_link_profile(member, username, password)
        except LinkProfileError as e:
            return e.message, None
        if profile.has_na_link_field():
            return LinkMessage.ONBOARDING_INCOMPLETE, ONBOARDING_CHECKLIST

        prn = profile.prn
        branch_full = profile.branch
        campus_short = profile.campus
        campus_code = profile.campus_code
        # `_fetch_link_profile` already validated these; re-check so `-O` cannot strip safety.
        if prn is None or branch_full is None or campus_short is None or campus_code is None:
            return LinkMessage.MISSING_PROFILE_FIELDS, None
        year = prn[4:8]

        branch_short = self._resolve_branch_short(branch_full)
        if not branch_short:
            self._send_link_error_log(
                content=member.mention,
                title="Branch to short code mapping not found",
                fields=[
                    {"name": "Username", "value": member.name, "inline": True},
                    {"name": "User ID", "value": str(member.id), "inline": True},
                    {"name": "PRN", "value": prn, "inline": True},
                    {"name": "Branch", "value": branch_full, "inline": True},
                    {"name": "Campus", "value": campus_short, "inline": True},
                    {"name": "Year", "value": year, "inline": True},
                ],
            )
            return LinkMessage.UNRECOGNIZED_BRANCH, None

        try:
            academic_roles = [
                self.client.config.resolve_academic_role(branch_short),
                self.client.config.resolve_academic_role(campus_short),
                self.client.config.resolve_academic_role(year),
            ]
        except ValueError as exc:
            self._send_link_error_log(
                content=member.mention,
                title="Roles missing",
                fields=[
                    {"name": "Username", "value": member.name, "inline": True},
                    {"name": "User ID", "value": str(member.id), "inline": True},
                    {"name": "PRN", "value": prn, "inline": True},
                    {"name": "Branch", "value": branch_short, "inline": True},
                    {"name": "Campus", "value": campus_short, "inline": True},
                    {"name": "Year", "value": year, "inline": True},
                    {"name": "Error", "value": str(exc)},
                ],
            )
            return LinkMessage.MISSING_ROLES, None

        if await self.client.stores.links.exists(prn=prn):
            return LinkMessage.PRN_TAKEN, None

        student = Student(
            prn=prn,
            branch=Branch(full=branch_full, short=branch_short),
            year=year,
            campus=Campus(code=campus_code, short=campus_short),
        )
        verification_logs = self.client.config.verification_logs_channel
        welcome = _get_dm_message(
            branch_short,
            campus_short,
            year,
            lobby=self.client.config.lobby_channel,
        )

        results = await asyncio.gather(
            # Upsert student record by PRN
            self.client.stores.students.upsert_by_prn(student),
            # Insert Discord↔PESU link record
            self.client.stores.links.insert_one(
                Link(
                    user_id=str(member.id),
                    prn=student.prn,
                    linked_at=datetime.now(UTC),
                )
            ),
            # Assign Linked + academic roles
            member.add_roles(
                self.client.config.linked_role,
                *academic_roles,
                reason="PESU account link",
            ),
            # Remove Just Joined role
            member.remove_roles(self.client.config.just_joined_role, reason="PESU account link"),
            # Send welcome DM
            ug.send_dm_safely(member, content=welcome),
            # Post verification log
            verification_logs.send(
                content=member.mention,
                embed=ug.build_embed(
                    title="User Linked",
                    color=discord.Color.green(),
                    fields=[
                        {"name": "Username", "value": member.name, "inline": True},
                        {"name": "User ID", "value": str(member.id), "inline": True},
                        {"name": "PRN", "value": prn, "inline": True},
                        {"name": "Branch", "value": branch_short, "inline": True},
                        {"name": "Campus", "value": campus_short, "inline": True},
                        {"name": "Year", "value": year, "inline": True},
                    ],
                ),
            ),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                self.client.logger.exception("Link side-effect failed", exc_info=result)
                self._send_link_error_log(
                    content=member.mention,
                    title="Link Side-Effect Failure",
                    fields=[
                        {"name": "Usename", "value": member.name, "inline": True},
                        {"name": "User ID", "value": str(member.id), "inline": True},
                        {"name": "PRN", "value": prn, "inline": True},
                        {"name": "Error", "value": f"{type(result).__name__}: {result}"[:1000]},
                    ],
                )

        return LinkMessage.SUCCESS, welcome

    async def _fetch_link_profile(self, member: discord.Member, username: str, password: str) -> PesuAuthProfile:
        """Authenticate and return a profile with required link fields.

        Raises:
            LinkProfileError: Auth failed or required profile fields are missing.
        """
        try:
            auth = await self._authenticate_pesu(username, password)
        except LinkProfileError as e:
            self._send_link_error_log(
                content=member.mention,
                title="PESU Auth Error",
                fields=[{"name": "Error", "value": e.detail[:1000]}],
            )
            raise

        profile = auth.profile
        if profile is None:
            self._send_link_error_log(
                content=member.mention,
                title="Missing PESU Profile Field",
                fields=[{"name": "Missing Field", "value": "profile"}],
            )
            raise LinkProfileError(LinkMessage.MISSING_PROFILE_FIELDS)

        missing = profile.missing_link_field()
        if missing is not None:
            self._send_link_error_log(
                content=member.mention,
                title="Missing PESU Profile Field",
                fields=[
                    {"name": "Missing Field", "value": missing},
                    {"name": "User Profile", "value": str(profile)[:1000]},
                ],
            )
            raise LinkProfileError(LinkMessage.MISSING_PROFILE_FIELDS)

        return profile

    def _send_link_error_log(
        self,
        *,
        content: str | None = None,
        title: str,
        fields: list[dict[str, Any]],
        color: discord.Color | None = None,
    ) -> None:
        """Schedule an error-log embed; never blocks the caller."""

        async def _deliver() -> None:
            try:
                channel = self.client.config.error_logs_channel
                embed = ug.build_embed(
                    title=title,
                    color=color or discord.Color.red(),
                    fields=fields,
                )
                await channel.send(content=content, embed=embed)
            except Exception:
                self.client.logger.exception("Failed to send error log embed: %s", title)

        asyncio.create_task(_deliver(), name="link-error-log")

    def _maybe_warn_non_prn(self, member: discord.Member, username: str) -> None:
        """Background-warn if username is not a PRN/SRN shape; never blocks linking."""
        if re.fullmatch(r"^PES[12]\d{9}$", username, re.IGNORECASE) or re.fullmatch(
            r"^PES[12](UG|PG)\d{2}[A-Z]{2}\d{3}$", username, re.IGNORECASE
        ):
            return
        self._send_link_error_log(
            content=member.mention,
            title="Non-PRN/SRN Link Attempt Detected",
            color=discord.Color.orange(),
            fields=[
                {"name": "Attempted Username", "value": username},
                {"name": "Discord User", "value": f"{member.name} ({member.id})"},
            ],
        )

    def _resolve_branch_short(self, branch_full: str) -> str | None:
        """Map PESU branch name to guild role short name (portal-compatible fallback).

        1. ``BRANCH_SHORT_CODES`` full-name map.
        2. Else, if ``branch_full`` already matches an academic Discord role name, use it as-is
           (covers auth returning short codes or branches only present as guild roles).
        """
        mapped = Config.BRANCH_SHORT_CODES.get(branch_full)
        if mapped:
            return mapped
        try:
            self.client.config.resolve_academic_role(branch_full)
        except ValueError:
            return None
        return branch_full

    async def _authenticate_pesu(self, username: str, password: str) -> PesuAuthResponse:
        """POST to pesu-auth and return a successful auth response.

        Raises:
            LinkProfileError: Transport, parse, or login failure. User-facing message is always
            ``LinkMessage.AUTH_FAILED``; upstream text is attached as ``detail`` for logs.
        """
        payload = {
            "username": username,
            "password": password,
            "profile": True,
            "fields": ["prn", "branch", "campus", "campusCode"],
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(Config.PESU_AUTH_URL, json=payload)
        except httpx.HTTPError as exc:
            raise LinkProfileError(LinkMessage.AUTH_FAILED, detail=str(exc)) from exc

        if not response.content:
            raise LinkProfileError(LinkMessage.AUTH_FAILED)

        try:
            data = response.json()
        except ValueError as exc:
            raise LinkProfileError(LinkMessage.AUTH_FAILED) from exc

        if not isinstance(data, dict):
            raise LinkProfileError(LinkMessage.AUTH_FAILED)

        auth = PesuAuthResponse.from_dict(data)
        if not auth.status:
            raise LinkProfileError(
                LinkMessage.AUTH_FAILED,
                detail=auth.message or LinkMessage.AUTH_FAILED,
            )
        return auth
