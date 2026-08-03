from __future__ import annotations

from discord import app_commands


class AnonGroups:
    anon = app_commands.Group(name="anon", description="Anonymous messaging commands")
