from __future__ import annotations

from discord import app_commands


class ModGroups:
    mod = app_commands.Group(name="mod", description="Moderation commands")
    mod_link = app_commands.Group(
        name="link",
        description="Linking moderation",
        parent=mod,
    )
    mod_anon = app_commands.Group(
        name="anon",
        description="Anonymous messaging moderation",
        parent=mod,
    )
