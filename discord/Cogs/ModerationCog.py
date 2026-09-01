import datetime
import logging
import os
from datetime import timedelta

import discord
from discord import Forbidden, app_commands
from discord.ext import commands

from .util import GUILD_CONFIG_PATH, MOD_CONFIG_PATH, WARNINGS_PATH, load_json, save_json

logger = logging.getLogger(__name__)

OWNER_ID = os.getenv("BotOwnerId")
try:
    OWNER_ID = int(OWNER_ID) if OWNER_ID else None
except ValueError:
    logger.warning("BotOwnerId env var is not a valid integer: %r", OWNER_ID)
    OWNER_ID = None


def _is_owner_or_admin(interaction: discord.Interaction) -> bool:
    """Check if the user is the configured owner, guild owner, or has administrator perms."""
    # Configured owner ID from .env
    if OWNER_ID is not None and interaction.user.id == OWNER_ID:
        return True
    # Guild owner fallback
    if interaction.guild and interaction.guild.owner_id == interaction.user.id:
        return True
    # Administrator permission fallback
    return bool(interaction.permissions and interaction.permissions.administrator)


async def is_allowed_user(interaction: discord.Interaction):
    if not _is_owner_or_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return False
    return True


class Moderation(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.mod_config: dict = load_json(MOD_CONFIG_PATH)
        self.warnings: dict = load_json(WARNINGS_PATH)
        self.guild_config: dict = load_json(GUILD_CONFIG_PATH)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel_id = self.guild_config.get("welcome_channel_id")
        if not channel_id:
            return
        channel = self.client.get_channel(channel_id)
        if not channel:
            return
        template = self.guild_config.get("welcome_message") or "👋 Welcome to the server, {member}!"
        try:
            await channel.send(template.format(member=member.mention))
        except (Forbidden, discord.HTTPException):
            logger.warning("Could not send welcome message to channel %s", channel_id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel_id = self.guild_config.get("welcome_channel_id")
        if not channel_id:
            return
        channel = self.client.get_channel(channel_id)
        if not channel:
            return
        try:
            await channel.send(f"👋 **{discord.utils.escape_mentions(member.display_name)}** has left the server.")
        except (Forbidden, discord.HTTPException):
            logger.warning("Could not send leave message to channel %s", channel_id)

    async def _log_action(self, interaction: discord.Interaction, action: str, target: str, reason: str):
        """Posts a record of a moderation action to the configured log
        channel, if one has been set via /set_log_channel. Never raises -
        a missing/deleted log channel shouldn't break the action itself."""
        channel_id = self.mod_config.get("log_channel_id")
        if not channel_id:
            return
        channel = self.client.get_channel(channel_id)
        if not channel:
            return
        embed = discord.Embed(title=f"🛡️ {action}", color=0xE67E22, timestamp=discord.utils.utcnow())
        embed.add_field(name="Target", value=target, inline=True)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=discord.utils.escape_mentions(reason), inline=False)
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (Forbidden, discord.HTTPException):
            logger.warning("Could not post mod-log entry to channel %s", channel_id)

    # ── Utility ──────────────────────────────────────────────────────────

    @app_commands.command(name="ping", description="Ping the bot")
    @app_commands.guild_only()
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong! {round(self.client.latency * 1000)}ms")

    @app_commands.command(name="cogs", description="List loaded cogs")
    @app_commands.guild_only()
    async def cogs(self, interaction: discord.Interaction):
        loaded = list(self.client.extensions.keys())
        lines = "\n".join(f"• {name}" for name in loaded) if loaded else "None loaded"
        embed = discord.Embed(title="Loaded Cogs", color=0x00FF00)
        embed.description = f"```\n{lines}\n```"
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="modhelp", description="List moderation commands")
    @app_commands.guild_only()
    async def modhelp(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Moderation Commands", color=0x00FF00)
        embed.add_field(
            name="Messages", value="`/purge <count>` — Bulk delete messages\n`/speak <message> [channel]` — Send as bot", inline=False
        )
        embed.add_field(
            name="Member Actions",
            value=(
                "`/kick <member> [reason]` — Kick user\n"
                "`/ban <member> [reason]` — Ban user\n"
                "`/unban <user_id> [reason]` — Unban user\n"
                "`/timeout <member> <minutes> [reason]` — Timeout user\n"
                "`/untimeout <member>` — Remove timeout\n"
                "`/warn <member> [reason]` — Issue a warning\n"
                "`/warnings <member>` — View warning history"
            ),
            inline=False,
        )
        embed.add_field(
            name="Bot",
            value=(
                "`/reload_cogs` — Hot-reload all cogs\n"
                "`/cogs` — List loaded cogs\n"
                "`/set_log_channel <channel>` — Set the mod-action log channel"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="help", description="List all available commands")
    @app_commands.guild_only()
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📖 S.A.R.A.H. Command Help", color=0x00FF00)
        for cog_name, cog in self.client.cogs.items():
            cmds = cog.get_app_commands()
            if not cmds:
                continue
            lines = [f"`/{c.name}` — {c.description}" for c in cmds]
            chunk = ""
            part = 1
            for line in lines:
                if len(chunk) + len(line) + 1 > 1000:
                    field_name = cog_name if part == 1 else f"{cog_name} (cont.)"
                    embed.add_field(name=field_name, value=chunk, inline=False)
                    chunk = ""
                    part += 1
                chunk += line + "\n"
            if chunk:
                field_name = cog_name if part == 1 else f"{cog_name} (cont.)"
                embed.add_field(name=field_name, value=chunk, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="set_log_channel", description="Set the channel moderation actions are logged to")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.check(is_allowed_user)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.mod_config["log_channel_id"] = channel.id
        save_json(MOD_CONFIG_PATH, self.mod_config)
        await interaction.response.send_message(f"📋 Moderation log channel set to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="set_welcome_channel", description="Set the channel for welcome/leave messages")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.check(is_allowed_user)
    async def set_welcome_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel, message: str | None = None
    ):
        self.guild_config["welcome_channel_id"] = channel.id
        if message:
            self.guild_config["welcome_message"] = message
        save_json(GUILD_CONFIG_PATH, self.guild_config)
        note = " Use `{member}` in your message to mention the new member." if message else ""
        await interaction.response.send_message(
            f"👋 Welcome/leave channel set to {channel.mention}.{note}", ephemeral=True
        )

    # ── Warnings ─────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Issue a warning to a member")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.check(is_allowed_user)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        user_id = str(member.id)
        entry = {
            "reason": reason,
            "moderator_id": interaction.user.id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.warnings.setdefault(user_id, []).append(entry)
        save_json(WARNINGS_PATH, self.warnings)

        safe_reason = discord.utils.escape_mentions(reason)
        count = len(self.warnings[user_id])
        await interaction.response.send_message(
            f"⚠️ {member.mention} has been warned (total: {count}).\n📋 Reason: `{safe_reason}`", ephemeral=True
        )
        await self._log_action(interaction, "Warn", f"{member.mention} ({member.id})", reason)

    @app_commands.command(name="warnings", description="View a member's warning history")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.check(is_allowed_user)
    async def view_warnings(self, interaction: discord.Interaction, member: discord.Member):
        entries = self.warnings.get(str(member.id), [])
        embed = discord.Embed(title=f"⚠️ Warnings for {member.display_name}", color=0xE67E22)
        if not entries:
            embed.description = "No warnings on record."
        else:
            for idx, entry in enumerate(entries, 1):
                mod = interaction.guild.get_member(entry.get("moderator_id"))
                mod_name = mod.mention if mod else "Unknown"
                safe_reason = discord.utils.escape_mentions(entry.get("reason", "No reason provided"))
                embed.add_field(
                    name=f"#{idx} — {entry.get('timestamp', 'unknown time')[:10]}",
                    value=f"By {mod_name}: {safe_reason}",
                    inline=False,
                )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Message Cleanup ────────────────────────────────────────────────

    @app_commands.command(name="purge", description="Clear chat messages")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.check(is_allowed_user)
    async def purge(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 100]):
        try:
            await interaction.response.defer(ephemeral=True)
            deleted = await interaction.channel.purge(limit=count)
            await interaction.followup.send(f"🗑 Deleted {len(deleted)} messages.", ephemeral=True)
            await self._log_action(interaction, "Purge", interaction.channel.mention, f"{len(deleted)} messages")
        except Forbidden:
            await interaction.followup.send("❌ Missing permissions.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Purge failed: {e}", ephemeral=True)

    @app_commands.command(name="speak", description="Make the bot send a message")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.check(is_allowed_user)
    async def speak(self, interaction: discord.Interaction, message: app_commands.Range[str, 1, 2000], channel: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        target_channel = channel or interaction.channel

        try:
            await target_channel.send(message, allowed_mentions=discord.AllowedMentions.none())
            logger.info(
                "/speak used by %s (id=%s) in %s targeting %s: %s",
                interaction.user,
                interaction.user.id,
                interaction.channel,
                target_channel,
                message[:200],
            )
            await interaction.followup.send(f"✅ Message sent to {target_channel.mention}.", ephemeral=True)
        except Forbidden:
            await interaction.followup.send("❌ Bot lacks permissions in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    # ── Member Actions ─────────────────────────────────────────────────

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.check(is_allowed_user)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.kick(reason=reason)
            safe_reason = discord.utils.escape_mentions(reason)
            await interaction.response.send_message(f"{member.mention} has been kicked.\n📋 Reason: `{safe_reason}`", ephemeral=True)
            await self._log_action(interaction, "Kick", f"{member.mention} ({member.id})", reason)
        except Forbidden:
            await interaction.response.send_message("❌ I can't kick this member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.check(is_allowed_user)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.ban(reason=reason)
            safe_reason = discord.utils.escape_mentions(reason)
            await interaction.response.send_message(f"{member.mention} has been banned.\n📋 Reason: `{safe_reason}`", ephemeral=True)
            await self._log_action(interaction, "Ban", f"{member.mention} ({member.id})", reason)
        except Forbidden:
            await interaction.response.send_message("❌ I can't ban this member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a member from the server")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.check(is_allowed_user)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            user = await self.client.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
            safe_reason = discord.utils.escape_mentions(reason)
            await interaction.response.send_message(f"{user.mention} has been unbanned.\n📋 Reason: `{safe_reason}`", ephemeral=True)
            await self._log_action(interaction, "Unban", f"{user.mention} ({user.id})", reason)
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID.", ephemeral=True)
        except Forbidden:
            await interaction.response.send_message("❌ I can't unban this user.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="timeout", description="Temporarily timeout a member")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.check(is_allowed_user)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],  # max ~4 weeks
        reason: str = "No reason provided",
    ):
        try:
            duration = discord.utils.utcnow() + timedelta(minutes=minutes)
            await member.timeout(duration, reason=reason)
            safe_reason = discord.utils.escape_mentions(reason)
            await interaction.response.send_message(
                f"🔇 {member.mention} has been timed out for **{minutes} minute(s)**.\n📋 Reason: `{safe_reason}`", ephemeral=True
            )
            await self._log_action(interaction, "Timeout", f"{member.mention} ({member.id}) — {minutes}m", reason)
        except Forbidden:
            await interaction.response.send_message("❌ I can't timeout this member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove a member's timeout")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.check(is_allowed_user)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.timeout(None, reason=reason)
            safe_reason = discord.utils.escape_mentions(reason)
            await interaction.response.send_message(
                f"🔊 {member.mention}'s timeout has been removed.\n📋 Reason: `{safe_reason}`", ephemeral=True
            )
            await self._log_action(interaction, "Untimeout", f"{member.mention} ({member.id})", reason)
        except Forbidden:
            await interaction.response.send_message("❌ I can't remove this timeout.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # ── Cog Management ──────────────────────────────────────────────────

    @app_commands.command(name="reload_cogs", description="Hot-reload all cogs")
    @app_commands.guild_only()
    @app_commands.check(is_allowed_user)
    async def reload_cogs(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        results = []

        for ext in self.client.extensions:
            if ext == "__main__":
                continue
            try:
                await self.client.reload_extension(ext)
                results.append(f"🔄 {ext} — reloaded")
            except Exception as e:
                cause = e.__cause__ if e.__cause__ is not None else e
                text = str(cause)
                err = next((line.strip() for line in text.split("\n") if line.strip()), text)
                results.append(f"❌ {ext} — {err}")

        embed = discord.Embed(title="Cog Reload Results", color=0x00FF00)
        embed.description = "\n".join(results) if results else "No cogs loaded"
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(client: commands.Bot):
    await client.add_cog(Moderation(client))
    logger.info("Moderation Online")
