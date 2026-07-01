from datetime import datetime

import discord


def parse_time(time_str: str) -> int:
    """Parse a duration string ending in y/d/h/m/s into seconds."""
    time_str = time_str.lower().strip()
    try:
        if time_str.endswith("y"):
            return int(time_str[:-1]) * 24 * 60 * 60 * 365
        if time_str.endswith("d"):
            return int(time_str[:-1]) * 24 * 60 * 60
        if time_str.endswith("h"):
            return int(time_str[:-1]) * 60 * 60
        if time_str.endswith("m"):
            return int(time_str[:-1]) * 60
        if time_str.endswith("s"):
            return int(time_str[:-1])
        return int(time_str)
    except ValueError:
        raise ValueError("Invalid time format") from None


def build_unknown_error_embed(error: Exception) -> discord.Embed:
    return (
        discord.Embed(
            title="❗ Unexpected Error",
            description="Something went wrong while processing the command.",
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )
        .add_field(name="Error Type", value=type(error).__name__, inline=True)
        .add_field(
            name="Details",
            value=str(error)[:1000] or "No details available.",
            inline=False,
        )
        .add_field(
            name="Support",
            value="Please report this to the developers if it keeps happening.",
            inline=False,
        )
        .set_footer(
            text="PESU Bot",
        )
    )
