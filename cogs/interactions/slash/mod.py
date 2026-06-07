import datetime as dt
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

import utils.general as ug
from bot import DiscordBot


class SlashMod(commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client

        # Background tasks
        self.tasks = [self.check_mutes_loop]
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
            if time_str.endswith("y"):
                return int(time_str[:-1]) * 24 * 60 * 60 * 365
            return int(time_str)
        except ValueError:
            raise ValueError("Invalid time format") from None

    async def cog_unload(self) -> None:
        for task in self.tasks:
            task.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.client.wait_until_ready()
        for task in self.tasks:
            if not task.is_running():
                task.start()

    @tasks.loop(seconds=30)
    async def check_mutes_loop(self) -> None:
        now = datetime.now(dt.UTC)
        expired_mutes = await self.client.mute_collection.find({"unmute_time": {"$lte": now}, "active": True}).to_list(
            length=100
        )

        guild = self.client.config.guild
        for mute in expired_mutes:
            try:
                member = await guild.fetch_member(mute["user_id"])
            except discord.NotFound:
                await self.client.mute_collection.update_one(
                    {"_id": mute["_id"]},
                    {
                        "$set": {
                            "active": False,
                            "unmute_time": now,
                            "unmute_type": "auto_member_left",
                        }
                    },
                )
                continue

            muted_role = self.client.config.muted_role
            if muted_role and muted_role in member.roles:
                try:
                    await member.remove_roles(muted_role, reason="Automatic unmute by loop")
                except Exception as e:
                    embed = ug.build_unknown_error_embed(e)
                    bot_logs = self.client.config.bot_logs_channel
                    await bot_logs.send(embed=embed)

            await self.client.mute_collection.update_one(
                {"_id": mute["_id"]},
                {
                    "$set": {
                        "active": False,
                        "unmute_time": now,
                        "unmute_type": "loop_auto",
                    }
                },
            )

            channel = guild.get_channel(mute["channel_id"])
            if not isinstance(channel, discord.TextChannel | discord.Thread):
                continue
            if channel:
                unmute_embed = discord.Embed(title="Unmute", color=discord.Color.green(), timestamp=now)
                unmute_embed.add_field(
                    name="Unmuted user",
                    value=f"{member.mention} welcome back",
                    inline=False,
                )
                unmute_embed.set_footer(text="PESU Bot")
                try:
                    await channel.send(content=member.mention, embed=unmute_embed)
                except discord.HTTPException:
                    pass

            mod_logs = self.client.config.mod_logs_channel
            unmute_logs_embed = discord.Embed(title="Unmute", color=discord.Color.green(), timestamp=now)

            unmute_logs_embed.add_field(
                name="Unmuted user",
                value=f"{member.mention}\nModerator: Auto",
                inline=False,
            )
            unmute_logs_embed.set_footer(text="PESU Bot")

            try:
                await mod_logs.send(embed=unmute_logs_embed)
            except discord.HTTPException:
                pass

    @check_mutes_loop.before_loop
    async def before_check_mutes_loop(self) -> None:
        await self.client.wait_until_ready()

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(
                content="This command can only be used in a server.",
                ephemeral=True,
            )
            return

        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="Noob you can't do that", ephemeral=True)
            return

        if member.bot:
            await interaction.followup.send(
                content="You dare kick one of my brothers you little twat",
                ephemeral=True,
            )
            return

        if self.client.config.has_mod_permissions(member):
            await interaction.followup.send(content="Gomma you can't kick admin/mod")
            return

        try:
            await member.send(content=f"You have been kicked from **{interaction.guild.name}**\nReason: {reason}")
        except (discord.Forbidden, discord.HTTPException):
            # Failed to send DM, it's alright
            pass

        await member.kick(reason=f"Kicked by {interaction.user} | {reason}")
        embed = discord.Embed(
            title="Member Kicked",
            color=discord.Color.red(),
            description=(f"{member.mention} was kicked by {interaction.user.mention}\n**Reason:** {reason}"),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="PESU Bot")
        await interaction.followup.send(embed=embed)
        mod_logs_channel = self.client.config.mod_logs_channel
        await mod_logs_channel.send(embed=embed)

    @kick.error
    async def kick_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            original = error.original

            if isinstance(original, discord.NotFound):
                await interaction.followup.send(
                    content="This user doesn't even exist here, who are you trying to kick?",
                    ephemeral=True,
                )

            elif isinstance(original, discord.Forbidden):
                await interaction.followup.send(content="I am unable to kick this user at this time", ephemeral=True)

            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @commands.command(name="echo", description="Echoes a message to the target channel", aliases=["e"])
    async def echo_prefix(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | discord.Thread,
        *,
        message: str,
    ) -> None:
        if not isinstance(ctx.author, discord.Member) or not ctx.guild:
            await ctx.reply(content="This command can only be used in a server.")
            return
        if not self.client.config.has_mod_permissions(ctx.author) and not self.client.config.has_bot_dev_permissions(
            ctx.author
        ):
            await ctx.reply(content="You think I am a fool")
            return

        try:
            attachment_to_send = await ctx.message.attachments[0].to_file() if ctx.message.attachments else None
            if attachment_to_send:
                await channel.send(content=message, file=attachment_to_send)
            else:
                await channel.send(content=message)
        except discord.Forbidden:
            await ctx.reply(content="Error: I don't have permission to send messages there.")
            return
        except Exception as e:
            await ctx.reply(content=f"An unexpected error occurred: {e}")
            return

        mods_logs_channel = self.client.config.mod_logs_channel
        echo_embed = discord.Embed(
            title="Echo Sent (Prefix)",
            color=discord.Color.blue(),
            timestamp=datetime.now(dt.UTC),
        )
        echo_embed.add_field(name="Message", value=message, inline=False)
        echo_embed.add_field(name="Channel", value=channel.mention, inline=False)
        echo_embed.add_field(
            name="Attachment",
            value="Yes" if ctx.message.attachments else "No",
            inline=False,
        )
        echo_embed.add_field(name="Author", value=ctx.author.mention, inline=False)
        echo_embed.set_footer(text="PESU Bot")
        await mods_logs_channel.send(embed=echo_embed)

    @app_commands.command(name="echo", description="Echoes a message to the target channel")
    @app_commands.describe(
        channel="The channel to send the message to",
        message="The message to send",
        attachment="An optional attachment to send with the message",
    )
    async def echo(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.Thread,
        message: str,
        attachment: discord.Attachment | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server.", ephemeral=True)
            return

        if not self.client.config.has_mod_permissions(
            interaction.user
        ) and not self.client.config.has_bot_dev_permissions(interaction.user):
            await interaction.followup.send(content="You are not authorised to run this command", ephemeral=True)
            return

        if not attachment:
            await channel.send(content=message)
        else:
            await channel.send(content=message, file=await attachment.to_file())
        await interaction.followup.send(content=f"Message sent to {channel.mention}", ephemeral=True)

        mod_logs_channel = self.client.config.mod_logs_channel
        echo_embed = discord.Embed(
            title="Echo Sent",
            color=discord.Color.blue(),
            timestamp=datetime.now(dt.UTC),
        )
        echo_embed.add_field(name="Message", value=message, inline=False)
        echo_embed.add_field(name="Channel", value=channel.mention, inline=False)
        echo_embed.add_field(
            name="Attachment",
            value="Yes" if attachment else "No",
            inline=False,
        )
        echo_embed.add_field(name="Author", value=interaction.user.mention, inline=False)
        echo_embed.set_footer(text="PESU Bot")
        await mod_logs_channel.send(embed=echo_embed)

    @echo.error
    async def echo_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            if isinstance(error.original, discord.Forbidden):
                await interaction.followup.send(
                    content="I do not have permission to send messages in that channel",
                    ephemeral=True,
                )
            elif isinstance(error.original, discord.NotFound):
                await interaction.followup.send(content="The specified channel does not exist", ephemeral=True)
            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error.original))
        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="mute", description="Mute a member for a specified duration")
    @app_commands.describe(
        member="The member to mute (or yourself for self-mute)",
        time="Duration for mute (e.g., 1h, 30m, 2d, and ofc y(💀))",
        reason="Reason for the mute (optional)",
    )
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        time: str,
        reason: str = "No reason provided",
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        if not isinstance(interaction.user, discord.Member) or not interaction.guild or not interaction.channel:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return
        muted_role = self.client.config.muted_role

        if interaction.user.id == member.id:
            is_self_mute = True
        else:
            if not self.client.config.has_mod_permissions(interaction.user):
                await interaction.followup.send(content="You are not authorised to do that", ephemeral=True)
                return
            is_self_mute = False

        try:
            seconds = self.parse_time(time)
        except ValueError:
            await interaction.followup.send(
                content="Mention the proper amount of time\nAccepted Time Format: Should end with `d/h/m/s/y`",
                ephemeral=True,
            )
            return

        if is_self_mute and seconds < 3600:
            await interaction.followup.send(content="Self-mute is only for 1 hour or more", ephemeral=True)
            return

        if muted_role in member.roles:
            await interaction.followup.send(
                content="Brother, leave the already muted poor soul alone",
                ephemeral=True,
            )
            return

        if not is_self_mute and self.client.config.has_mod_permissions(member):
            await interaction.followup.send(content="Leyy, he's admin/mod. Can't mute them", ephemeral=True)
            return

        if member.bot:
            await interaction.followup.send(content="You dare mute one of my kind nin amn", ephemeral=True)
            return

        await member.add_roles(muted_role)
        mute_time = datetime.now(dt.UTC)
        unmute_time = mute_time + timedelta(seconds=seconds)

        mute_record = {
            "user_id": member.id,
            "channel_id": interaction.channel.id,
            "moderator_id": interaction.user.id,
            "mute_time": mute_time,
            "unmute_time": unmute_time,
            "reason": reason,
            "active": True,
            "is_self_mute": is_self_mute,
        }
        await self.client.mute_collection.insert_one(mute_record)

        mute_embed = discord.Embed(
            title="Mute",
            color=discord.Color.red(),
            timestamp=datetime.now(dt.UTC),
        )
        unmute_timestamp = int(unmute_time.timestamp())
        mute_embed.add_field(
            name="Muted User",
            value=f"{member.mention} was muted\nUnmute: <t:{unmute_timestamp}:R>\nReason: {reason}",
            inline=False,
        )
        mute_embed.set_footer(text="PESU Bot")
        await interaction.followup.send(content=member.mention, embed=mute_embed)

        mod_logs = self.client.config.mod_logs_channel
        mute_logs_embed = discord.Embed(
            title="Mute",
            color=discord.Color.red(),
            timestamp=datetime.now(dt.UTC),
        )
        moderator_mention = interaction.user.mention if not is_self_mute else "Self"
        mute_logs_embed.add_field(
            name="Muted User",
            value=f"{member.mention}\nTime: {time}\nReason: {reason}\nModerator: {moderator_mention}",
            inline=False,
        )
        mute_logs_embed.set_footer(text="PESU Bot")
        await mod_logs.send(embed=mute_logs_embed)

    @mute.error
    async def mute_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            original = error.original

            if isinstance(original, discord.NotFound):
                await interaction.followup.send(
                    content="This user doesn't even exist here, who are you trying to mute?",
                    ephemeral=True,
                )

            elif isinstance(original, discord.Forbidden):
                await interaction.followup.send(content="I am unable to mute this user at this time", ephemeral=True)

            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="unmute", description="Unmute a member")
    @app_commands.describe(member="The member to unmute")
    async def unmute(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.response.defer(ephemeral=False)
        if not isinstance(interaction.user, discord.Member) or not interaction.guild or not interaction.channel:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return

        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="You are not authorised to do this", ephemeral=True)
            return
        muted_role = self.client.config.muted_role

        if muted_role not in member.roles:
            await interaction.followup.send(content="Why you trynna unmute someone who ain't muted?", ephemeral=True)
            return

        await member.remove_roles(muted_role)

        await self.client.mute_collection.update_many(
            {"user_id": member.id, "active": True},
            {
                "$set": {
                    "active": False,
                    "unmute_time": datetime.now(dt.UTC),
                    "unmute_type": "manual",
                    "unmuted_by": interaction.user.id,
                }
            },
        )

        unmute_embed = discord.Embed(
            title="Unmute",
            color=discord.Color.green(),
            timestamp=datetime.now(dt.UTC),
        )
        unmute_embed.set_footer(text="PESU Bot")
        unmute_embed.add_field(
            name="Unmuted user",
            value=f"{member.mention} welcome back",
            inline=False,
        )

        await interaction.followup.send(content=member.mention, embed=unmute_embed)

        mod_logs = self.client.config.mod_logs_channel
        unmute_logs_embed = discord.Embed(
            title="Unmute",
            color=discord.Color.green(),
            timestamp=datetime.now(dt.UTC),
        )
        unmute_logs_embed.set_footer(text="PESU Bot")
        unmute_logs_embed.add_field(
            name="Unmuted user",
            value=f"{member.mention}\nModerator: {interaction.user.mention}",
            inline=False,
        )
        await mod_logs.send(embed=unmute_logs_embed)

    @unmute.error
    async def unmute_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            original = error.original

            if isinstance(original, discord.NotFound):
                await interaction.followup.send(
                    content="This user doesn't even exist here, who are you trying to unmute?",
                    ephemeral=True,
                )

            elif isinstance(original, discord.Forbidden):
                await interaction.followup.send(
                    content="I am unable to unmute this user at this time",
                    ephemeral=True,
                )

            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="purge", description="Delete messages by amount, date, or message link")
    @app_commands.describe(
        amount="Number of messages to delete (1-100)",
        message_link="Delete all messages after this message",
        date="Delete all messages after this date (DD-MM-YYYY)",
    )
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: int | None = None,
        message_link: str | None = None,
        date: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel | discord.Thread):
            await interaction.followup.send(
                content="This command can only be used in a text channel or thread", ephemeral=True
            )
            return

        if sum(x is not None for x in [amount, message_link, date]) != 1:
            await interaction.followup.send(
                content="Please provide exactly one of: `amount`, `message_link`, or `date`.", ephemeral=True
            )
            return

        deleted_messages = []
        log_description = ""

        if amount:
            if amount < 1 or amount > 100:
                await interaction.followup.send(content="Please specify a number between 1 and 100", ephemeral=True)
                return
            deleted_messages = await interaction.channel.purge(limit=amount)
            log_description = f"deleted {len(deleted_messages)} messages"

        elif message_link:
            try:
                msg_id = int(message_link.split("/")[-1])
                message = await interaction.channel.fetch_message(msg_id)
                deleted_messages = await interaction.channel.purge(after=message)
                log_description = f"deleted messages after {message_link}"
            except (ValueError, IndexError, discord.NotFound):
                await interaction.followup.send(
                    content="Invalid message link or message not found in this channel.", ephemeral=True
                )
                return

        elif date:
            try:
                date_obj = datetime.strptime(date, "%d-%m-%Y").replace(tzinfo=dt.UTC)
                deleted_messages = await interaction.channel.purge(after=date_obj)
                log_description = f"deleted messages since {date}"
            except ValueError:
                await interaction.followup.send(content="Invalid date format. Please use DD-MM-YYYY.", ephemeral=True)
                return

        await interaction.followup.send(content=f"Deleted {len(deleted_messages)} messages.", ephemeral=True)
        embed = discord.Embed(
            title="Messages Purged",
            color=discord.Color.green(),
            description=f"{interaction.user.mention} {log_description} in {interaction.channel.mention}",
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="PESU Bot")

        mod_logs_channel = self.client.config.mod_logs_channel
        await mod_logs_channel.send(embed=embed)

    @purge.error
    async def purge_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            original = error.original

            if isinstance(original, discord.Forbidden):
                await interaction.followup.send(
                    content="I am unable to delete messages in this channel at this time",
                    ephemeral=True,
                )
            elif isinstance(original, discord.NotFound):
                await interaction.followup.send(
                    content="This channel doesn't exist or has been deleted",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="lock", description="lock a channel")
    @app_commands.describe(
        channel="The channel to lock (defaults to current channel)",
        reason="Reason for locking the channel (optional)",
    )
    async def lock_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        reason: str = "No reason provided",
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return

        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="I am not dyno to let you do this", ephemeral=True)
            return

        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.followup.send(
                    content="This command can only be used in a text channel",
                    ephemeral=True,
                )
                return
            channel = interaction.channel

        everyone_role = interaction.guild.default_role
        overwrites = channel.overwrites_for(everyone_role)
        if overwrites.send_messages is False:
            await interaction.followup.send(content="This channel is already locked", ephemeral=True)
            return

        overwrites.send_messages = False
        await channel.set_permissions(everyone_role, overwrite=overwrites)
        await interaction.followup.send(content=f"Locked {channel.mention}", ephemeral=False)

        lock_embed = discord.Embed(
            title="Channel Locked :lock:",
            color=discord.Color.red(),
            description=reason,
            timestamp=datetime.now(dt.UTC),
        )
        lock_embed.set_footer(text="PESU Bot")
        await channel.send(embed=lock_embed)

        lock_logs_embed = discord.Embed(
            title="Lock",
            color=discord.Color.red(),
            timestamp=datetime.now(dt.UTC),
        )
        lock_logs_embed.set_footer(text="PESU Bot")
        lock_logs_embed.add_field(name="Channel", value=channel.mention, inline=True)
        lock_logs_embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        lock_logs_embed.add_field(name="Reason", value=reason, inline=False)
        mod_logs_channel = self.client.config.mod_logs_channel
        await mod_logs_channel.send(embed=lock_logs_embed)

    @lock_channel.error
    async def lock_channel_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            original = error.original

            if isinstance(original, discord.NotFound):
                await interaction.followup.send(
                    content="This channel doesn't exist or has been deleted",
                    ephemeral=True,
                )

            elif isinstance(original, discord.Forbidden):
                await interaction.followup.send(
                    content="I am unable to lock this channel at this time",
                    ephemeral=True,
                )

            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="unlock", description="Unlock a channel")
    @app_commands.describe(channel="The channel to unlock (defaults to current channel)")
    async def unlock_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return

        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="I am not dyno to let you do this", ephemeral=True)
            return

        if channel is None:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.followup.send(
                    content="This command can only be used in a text channel",
                    ephemeral=True,
                )
                return
            channel = interaction.channel

        everyone_role = interaction.guild.default_role

        overwrites = channel.overwrites_for(everyone_role)
        if overwrites.send_messages is None or overwrites.send_messages is True:
            await interaction.followup.send(content="This channel ain't locked bruh whatcha doin", ephemeral=True)
            return

        overwrites.send_messages = None
        await channel.set_permissions(everyone_role, overwrite=overwrites)
        await interaction.followup.send(content=f"Unlocked {channel.mention}", ephemeral=False)

        unlock_embed = discord.Embed(
            title="Channel Unlocked :unlock:",
            color=discord.Color.green(),
            timestamp=datetime.now(dt.UTC),
        )
        unlock_embed.set_footer(text="PESU Bot")
        await channel.send(embed=unlock_embed)

        unlock_logs_embed = discord.Embed(
            title="Unlock",
            color=discord.Color.green(),
            timestamp=datetime.now(dt.UTC),
        )
        unlock_logs_embed.set_footer(text="PESU Bot")
        unlock_logs_embed.add_field(name="Channel", value=channel.mention, inline=True)
        unlock_logs_embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        mod_logs_channel = self.client.config.mod_logs_channel
        await mod_logs_channel.send(embed=unlock_logs_embed)

    @unlock_channel.error
    async def unlock_channel_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            original = error.original

            if isinstance(original, discord.NotFound):
                await interaction.followup.send(
                    content="This channel doesn't exist or has been deleted",
                    ephemeral=True,
                )

            elif isinstance(original, discord.Forbidden):
                await interaction.followup.send(
                    content="I am unable to unlock this channel at this time",
                    ephemeral=True,
                )

            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="timeout", description="Timeout a member for a specified duration")
    @app_commands.describe(
        member="The member to timeout",
        time="Duration for timeout (e.g., 1h, 30m, 2d)",
        reason="Reason for the timeout (optional)",
    )
    async def timeout_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        time: str,
        reason: str = "No reason provided",
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return

        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="You are not authorised to do this", ephemeral=True)
            return

        try:
            seconds = self.parse_time(time)
        except ValueError:
            await interaction.followup.send(
                content=(
                    "Mention the proper amount of time to be timed-out\nAccepted Time Format: Should end with `d/h/m/s`"
                ),
                ephemeral=True,
            )
            return

        if seconds <= 0 or seconds > 2419200:
            await interaction.followup.send(content="Time-out limit is 28 days only", ephemeral=True)
            return

        if member.is_timed_out():
            await interaction.followup.send(
                content="Brother, leave the already timed-out poor soul alone", ephemeral=True
            )
            return

        if self.client.config.has_mod_permissions(member):
            await interaction.followup.send(content="Leyy, he's admin/mod. Can't time them out", ephemeral=True)
            return

        if member.bot:
            await interaction.followup.send(content="You dare time-out one of my kind nin amn", ephemeral=True)
            return

        timeout_until = discord.utils.utcnow() + timedelta(seconds=seconds)
        await member.timeout(timeout_until, reason=reason)

        timeout_embed = discord.Embed(title="Time-out", color=0x8B0000, timestamp=discord.utils.utcnow())
        timeout_embed.set_footer(text="PESU Bot")
        timeout_timestamp = int(timeout_until.timestamp())
        timeout_embed.add_field(
            name="Timed-out Member",
            value=f"{member.mention} was timed-out\nDe-time-out: <t:{timeout_timestamp}:R>\nReason: {reason}",
            inline=False,
        )

        await interaction.followup.send(content=member.mention, embed=timeout_embed)

        mod_logs = self.client.config.mod_logs_channel
        timeout_logs_embed = discord.Embed(title="Time-out", color=0x8B0000, timestamp=discord.utils.utcnow())
        timeout_logs_embed.add_field(
            name="Timed-out User",
            value=f"{member.mention}\nTime: {time}\nReason: {reason}\nModerator: {interaction.user.mention}",
            inline=False,
        )
        timeout_logs_embed.set_footer(text="PESU Bot")
        await mod_logs.send(embed=timeout_logs_embed)

    @timeout_member.error
    async def timeout_member_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            original = error.original

            if isinstance(original, discord.NotFound):
                await interaction.followup.send(
                    content="This user doesn't even exist here, who are you trying to timeout?",
                    ephemeral=True,
                )

            elif isinstance(original, discord.Forbidden):
                await interaction.followup.send(
                    content="I am unable to timeout this user at this time",
                    ephemeral=True,
                )

            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @app_commands.command(name="detimeout", description="Remove timeout from a member")
    @app_commands.describe(member="The member to remove timeout from")
    async def detimeout_member(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.response.defer(ephemeral=False)
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return
        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="You are not authorised to do this", ephemeral=True)
            return

        if not member.is_timed_out():
            await interaction.followup.send(content="This person ain't on time-out only", ephemeral=True)
            return

        await member.timeout(None, reason=f"Timeout removed by {interaction.user}")

        detimeout_embed = discord.Embed(title="De-Time-out", color=0x00FF00, timestamp=discord.utils.utcnow())
        detimeout_embed.set_footer(text="PESU Bot")
        detimeout_embed.add_field(
            name="De-timed-out Member",
            value=f"{member.mention}, welcome back",
            inline=False,
        )

        await interaction.followup.send(content=member.mention, embed=detimeout_embed)

        mod_logs = self.client.config.mod_logs_channel
        detimeout_logs_embed = discord.Embed(title="De-time-out", color=0x00FF00, timestamp=discord.utils.utcnow())
        detimeout_logs_embed.set_footer(text="PESU Bot")
        detimeout_logs_embed.add_field(
            name="De-timed-out User",
            value=f"{member.mention}\nModerator: {interaction.user.mention}",
            inline=False,
        )
        await mod_logs.send(embed=detimeout_logs_embed)

    @detimeout_member.error
    @timeout_member.error
    async def detimeout_member_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            original = error.original

            if isinstance(original, discord.NotFound):
                await interaction.followup.send(
                    content="This user doesn't even exist here, who are you trying to de-timeout?",
                    ephemeral=True,
                )

            elif isinstance(original, discord.Forbidden):
                await interaction.followup.send(
                    content="I am unable to de-timeout this user at this time",
                    ephemeral=True,
                )

            else:
                await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

        else:
            await interaction.followup.send(embed=ug.build_unknown_error_embed(error))


async def setup(client: DiscordBot) -> None:
    await client.add_cog(
        SlashMod(client),
        guild=client.config.guild,
    )
