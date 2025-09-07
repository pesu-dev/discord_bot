import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

import utils.general as ug
from bot import DiscordBot


class SlashAnon(commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        self.anon_cache = {}
        self.ctx_menu = app_commands.ContextMenu(
            name="Ban this anon",
            callback=self.anon_ban_from_context_menu,
        )
        self.client.tree.add_command(self.ctx_menu)
        self.tasks = [self.check_anon_bans_loop, self.clear_anon_cache_loop]
        for task in self.tasks:
            if not task.is_running():
                task.start()

    async def cog_unload(self) -> None:
        for task in self.tasks:
            task.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.client.wait_until_ready()
        for task in self.tasks:
            if not task.is_running():
                task.start()

    @staticmethod
    def parse_time(time_str: str) -> int:
        time_str = time_str.lower().strip()
        try:
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

    async def _check_server_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if interaction is in a server with proper member permissions."""
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return False
        return True

    async def _check_mod_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if user has moderator permissions."""
        if not isinstance(interaction.user, discord.Member):
            return False
        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="You ain't authorised to run this command", ephemeral=True)
            return False
        return True

    async def _check_text_channel_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if interaction is in a text channel with proper permissions."""
        if (
            not isinstance(interaction.user, discord.Member)
            or not isinstance(interaction.channel, discord.TextChannel)
            or not interaction.guild
        ):
            await interaction.followup.send(content="This command can only be used in a text channel", ephemeral=True)
            return False
        return True

    async def _check_user_anon_ban(self, user_id: str) -> dict | None:
        """Check if user is banned from anon messaging."""
        return await self.client.anonban_collection.find_one({"userId": user_id, "active": True})

    async def _validate_and_parse_time(self, interaction: discord.Interaction, time_str: str) -> int | None:
        """Validate and parse time string, return seconds or None if invalid."""
        try:
            seconds = self.parse_time(time_str)
            if seconds <= 10:
                await interaction.followup.send(
                    content="You can't ban someone for less than 10 seconds", ephemeral=True
                )
                return None
            return seconds
        except ValueError:
            await interaction.followup.send(
                content=(
                    "Mention the proper amount of time to be muted\nAccepted Time Format: Should end with `d/h/m/s`"
                ),
                ephemeral=True,
            )
            return None

    def _find_user_from_message(self, message_id: str, guild: discord.Guild) -> discord.Member | None:
        """Find the user who sent an anonymous message based on message ID."""
        for user_id, messages in self.anon_cache.items():
            for message in messages:
                if str(message_id) == message["message_id"]:
                    return guild.get_member(int(user_id))
        return None

    def _create_notification_embed(
        self, title: str, description: str, color: discord.Color, fields: list[dict] | None = None
    ) -> discord.Embed:
        """Create a standardized notification embed."""
        embed = discord.Embed(title=title, description=description, color=color)
        if fields:
            for field in fields:
                embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))
        embed.timestamp = datetime.datetime.now(datetime.UTC)
        embed.set_footer(text="PESU Bot")
        return embed

    async def _send_dm_safely(self, user: discord.User | discord.Member, embed: discord.Embed) -> bool:
        """Send DM to user with error handling. Returns True if successful."""
        try:
            await user.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def _handle_ban_message_link(
        self, interaction: discord.Interaction, link: str
    ) -> tuple[discord.Member, discord.Message] | None:
        """Handle message link validation and user lookup. Returns (user, message) or None if failed."""
        if not isinstance(interaction.channel, discord.TextChannel) or not interaction.guild:
            return None

        try:
            ban_msg = await interaction.channel.fetch_message(int(link.split("/")[-1]))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(content="Could not find the message to ban from", ephemeral=True)
            return None

        user_to_ban = self._find_user_from_message(str(ban_msg.id), interaction.guild)
        if not user_to_ban:
            await interaction.followup.send(
                content="This wasn't an anon message only da what you doing?", ephemeral=True
            )
            return None

        return user_to_ban, ban_msg

    async def _create_and_store_ban(self, user_id: str, reason: str, time_str: str | None = None) -> tuple[dict, str]:
        """Create ban data and store in database. Returns (ban_data, expiry_timestamp)."""
        banned_at = datetime.datetime.now(datetime.UTC)

        if time_str is not None:
            seconds = self.parse_time(time_str)
            expires_at = banned_at + datetime.timedelta(seconds=seconds)
        else:
            expires_at = None

        ban_data = {
            "userId": user_id,
            "reason": reason,
            "bannedAt": banned_at,
            "expiresAt": expires_at,
            "active": True,
        }

        await self.client.anonban_collection.insert_one(ban_data)
        expiry_timestamp = "Permanent" if expires_at is None else f"<t:{int(expires_at.timestamp())}:R>"

        return ban_data, expiry_timestamp

    @tasks.loop(seconds=30)
    async def check_anon_bans_loop(self) -> None:
        current_time = datetime.datetime.now(datetime.UTC)
        async for ban in self.client.anonban_collection.find(
            {"expiresAt": {"$ne": None, "$lt": current_time}, "active": True}
        ):
            await self.client.anonban_collection.update_one({"_id": ban["_id"]}, {"$set": {"active": False}})
            user = await self.client.fetch_user(ban["userId"])
            if user:
                embed = self._create_notification_embed(
                    title="Notification",
                    description="Your anon messaging ban has expired",
                    color=discord.Color.green(),
                )
                await self._send_dm_safely(user, embed)

    @check_anon_bans_loop.before_loop
    async def before_check_anon_bans_loop(self) -> None:
        await self.client.wait_until_ready()

    @tasks.loop(seconds=10)
    async def clear_anon_cache_loop(self) -> None:
        if self.anon_cache:
            # gets current time
            current_time = datetime.datetime.now(datetime.UTC)
            # amount of time in seconds the bot waits to clear the cache.
            min_time = 86400
            # cache clearing logic
            for key, value in self.anon_cache.items():
                self.anon_cache[key] = [
                    msg for msg in value if (current_time - msg["timestamp"]).total_seconds() < min_time
                ]

    @clear_anon_cache_loop.before_loop
    async def before_clear_anon_cache_loop(self) -> None:
        await self.client.wait_until_ready()

    @app_commands.command(
        name="anon",
        description="Send messages anonymously to the general lobby channel",
    )
    @app_commands.describe(message="The message you want to send", link="Message link you want to reply to")
    async def anon(self, interaction: discord.Interaction, message: str, link: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(
                content="This command can only be used by members of the server", ephemeral=True
            )
            return

        member_link_check = await self.client.link_collection.find_one({"userId": str(interaction.user.id)})
        if not member_link_check:
            await interaction.followup.send(
                content="You're not linked, so you can't use anon messaging. If this is a mistake, please contact Han",
                ephemeral=True,
            )
            return
        member_anon_ban_check = await self.client.anonban_collection.find_one(
            {"userId": str(interaction.user.id), "active": True}
        )
        if member_anon_ban_check:
            await interaction.followup.send(
                content=":x: You have been banned from using anon messaging", ephemeral=True
            )
            return

        lobby_channel = self.client.config.lobby_channel
        perms = lobby_channel.permissions_for(interaction.user)
        if not perms.send_messages:
            await interaction.followup.send(
                content="Looks like the channel is locked or you're muted. I won't send",
                ephemeral=True,
            )
            return

        # they passed the checks, so we can send the message

        if link is not None:
            try:
                reply_msg = await lobby_channel.fetch_message(int(link.split("/")[-1]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                reply_msg = None
        else:
            reply_msg = None

        embed = discord.Embed(title="Anon Message", description=message, color=discord.Color.random())
        embed.timestamp = datetime.datetime.now(datetime.UTC)
        embed.set_footer(text="PESU Bot")

        if reply_msg:
            anon_message = await reply_msg.reply(embed=embed, mention_author=True)
        else:
            anon_message = await lobby_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(
            content=f":white_check_mark: Your anon message has been sent to {lobby_channel.mention}"
        )

        if str(interaction.user.id) not in self.anon_cache:
            self.anon_cache[str(interaction.user.id)] = []

        # adds a list of dictionaries
        # each dict contains message id and timestamp
        self.anon_cache[str(interaction.user.id)].append(
            {"message_id": str(anon_message.id), "timestamp": datetime.datetime.now(datetime.UTC)}
        )

    @anon.error
    async def anon_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="bananon", description="Ban a user from using anon based on message link")
    @app_commands.describe(
        link="The message link you want to use to ban",
        time="Duration of the ban",
        reason="Reason for ban (optional)",
    )
    async def ban_anon(
        self,
        interaction: discord.Interaction,
        link: str,
        time: str | None = None,
        reason: str | None = "No reason provided",
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        if not await self._check_text_channel_permissions(interaction):
            return
        if not await self._check_mod_permissions(interaction):
            return

        # Handle message link and find user
        result = await self._handle_ban_message_link(interaction, link)
        if not result:
            return
        user_to_ban, ban_msg = result

        # Check if user is already banned
        if await self._check_user_anon_ban(str(user_to_ban.id)):
            await interaction.followup.send(content="Dude's already banned from anon messaging", ephemeral=True)
            return

        # Validate time if provided
        if time is not None and await self._validate_and_parse_time(interaction, time) is None:
            return

        # Create and store ban
        ban_reason = reason if reason is not None else "No reason provided"
        ban_data, expiry_timestamp = await self._create_and_store_ban(str(user_to_ban.id), ban_reason, time)

        # Send confirmation
        if expiry_timestamp == "Permanent":
            await interaction.followup.send(
                content=f"Member has been banned from anon messaging, their ban will never expire\nReason: {ban_reason}"
            )
        else:
            await interaction.followup.send(
                content=(
                    f"Member has been banned from anon messaging, their ban will expire {expiry_timestamp}\n"
                    f"Reason: {ban_reason}"
                )
            )

        # Send DM notification
        ban_embed = self._create_notification_embed(
            title="Notification",
            description="You have been banned from using anon messaging",
            color=discord.Color.red(),
            fields=[
                {"name": "Reason", "value": ban_reason},
                {"name": "Message Link", "value": f"[Click here to view the message]({link})"},
                {"name": "Expires", "value": expiry_timestamp},
            ],
        )

        if not await self._send_dm_safely(user_to_ban, ban_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)

    @ban_anon.error
    async def ban_anon_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    async def anon_ban_from_context_menu(self, interaction: discord.Interaction, message: discord.Message) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        if not await self._check_server_permissions(interaction):
            return
        if not await self._check_mod_permissions(interaction):
            return
        if not isinstance(interaction.channel, discord.TextChannel) or not interaction.guild:
            return

        # Find user from message
        ban_user = self._find_user_from_message(str(message.id), interaction.guild)
        if not ban_user:
            await interaction.followup.send(
                content="This wasn't an anon message only da what you doing?", ephemeral=True
            )
            return

        # Check if user is already banned
        if await self._check_user_anon_ban(str(ban_user.id)):
            await interaction.followup.send(content="Dude's already banned from anon messaging", ephemeral=True)
            return

        # Create and store permanent ban
        reason = "No reason provided, executed via context menu"
        ban_data, _ = await self._create_and_store_ban(str(ban_user.id), reason, None)

        # Create notification embed
        embed = self._create_notification_embed(
            title="Notification",
            description="You have been banned from using anon messaging",
            color=discord.Color.red(),
            fields=[
                {"name": "Reason", "value": reason},
                {
                    "name": "Message Link",
                    "value": f"[Jump to message](https://discord.com/channels/{interaction.guild.id}/{interaction.channel.id}/{message.id})",
                },
                {"name": "Expires", "value": "Permanent"},
            ],
        )

        # Send DM and confirmation
        dm_sent = await self._send_dm_safely(ban_user, embed)
        base_message = f"Member has been banned from anon messaging, their ban will never expire\nReason: {reason}"

        if dm_sent:
            await interaction.followup.send(content=base_message, ephemeral=True)
        else:
            await interaction.followup.send(
                content=f"{base_message} but I couldn't DM them",
                ephemeral=True,
            )

    @app_commands.command(name="userbananon", description="Manually ban a user from anon messaging")
    @app_commands.describe(member="The member to ban", time="Duration of the ban", reason="Reason for ban")
    async def user_ban_anon(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        time: str | None = None,
        reason: str | None = "No reason provided",
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        if not await self._check_server_permissions(interaction):
            return
        if not await self._check_mod_permissions(interaction):
            return

        # Check if user is already banned
        if await self._check_user_anon_ban(str(member.id)):
            await interaction.followup.send(content="Dude's already banned from anon messaging", ephemeral=True)
            return

        # Validate time if provided
        if time is not None:
            if await self._validate_and_parse_time(interaction, time) is None:
                return

        # Create and store ban
        ban_reason = reason if reason is not None else "No reason provided"
        ban_data, expiry_timestamp = await self._create_and_store_ban(str(member.id), ban_reason, time)

        # Send confirmation
        if expiry_timestamp == "Permanent":
            confirmation_msg = (
                f"Member has been banned from anon messaging, their ban will never expire\nReason: {ban_reason}"
            )
        else:
            confirmation_msg = (
                f"Member has been banned from anon messaging. Ban expiry: {expiry_timestamp}\nReason: {ban_reason}"
            )

        await interaction.followup.send(content=confirmation_msg)

        # Send DM notification
        ban_embed = self._create_notification_embed(
            title="Notification",
            description="You have been banned from using anon messaging",
            color=discord.Color.red(),
            fields=[
                {"name": "Reason", "value": ban_reason},
                {"name": "Expires", "value": expiry_timestamp},
            ],
        )

        if not await self._send_dm_safely(member, ban_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)

    @user_ban_anon.error
    async def user_ban_anon_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="userunbananon", description="Unban a user from anon messaging")
    @app_commands.describe(member="The member to unban")
    async def user_unban_anon(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        if not await self._check_server_permissions(interaction):
            return
        if not await self._check_mod_permissions(interaction):
            return

        # Attempt to unban user
        result = await self.client.anonban_collection.find_one_and_update(
            {"userId": str(member.id), "active": True}, {"$set": {"active": False}}
        )

        if result is None:
            await interaction.followup.send(
                content="This fellow wasn't even anon-banned in the first place", ephemeral=True
            )
            return

        await interaction.followup.send(content="Member unbanned successfully")

        # Send DM notification
        unban_embed = self._create_notification_embed(
            title="Notification",
            description="Your anon messaging ban has been revoked",
            color=discord.Color.green(),
        )

        if not await self._send_dm_safely(member, unban_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)

    @user_unban_anon.error
    async def user_unban_anon_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="anonbaninfo", description="Get info about a user's anon ban")
    @app_commands.describe(member="The member to get info about")
    async def anon_ban_info(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check permissions
        if not await self._check_server_permissions(interaction):
            return
        if not await self._check_mod_permissions(interaction):
            return

        # Get ban info
        user_anon_ban_check = await self._check_user_anon_ban(str(member.id))
        if not user_anon_ban_check:
            await interaction.followup.send(content="This fellow is not banned from anon messaging", ephemeral=True)
            return

        banned_at = user_anon_ban_check["bannedAt"]
        expires_at = user_anon_ban_check["expiresAt"]
        expiry_timestamp = f"<t:{int(expires_at.timestamp())}:R>" if expires_at else "Permanent"

        # Create info embed
        embed = self._create_notification_embed(
            title="Anon Ban Info",
            description="",
            color=discord.Color.red(),
            fields=[
                {"name": "User", "value": member.mention},
                {"name": "Reason", "value": user_anon_ban_check.get("reason", "No reason provided")},
                {"name": "Banned", "value": f"<t:{int(banned_at.timestamp())}:R>"},
                {"name": "Expires", "value": expiry_timestamp},
            ],
        )

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(client: DiscordBot) -> None:
    cog = SlashAnon(client)
    await client.add_cog(cog, guild=client.config.guild)
    client.tree.add_command(
        cog.ctx_menu,
        guild=client.config.guild,
    )
