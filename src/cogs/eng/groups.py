from __future__ import annotations

from discord import app_commands


class EngGroups:
    eng = app_commands.Group(name="eng", description="Bot engineering commands")
    eng_mongo = app_commands.Group(
        name="mongo",
        description="Temporary MongoDB access",
        parent=eng,
    )
