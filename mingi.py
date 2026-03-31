import asyncio
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import DISCORD_TOKEN, DATABASE_URL, INTRO_COOLDOWN_SECONDS, BOT_STATUS_TEXT
from database import (
    connect_db,
    setup_tables,
    get_intro_settings,
    upsert_intro_settings,
    update_panel_state,
    get_user_intro,
    upsert_user_intro,
)


def now_ts() -> int:
    return int(time.time())


def format_remaining(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600

    if days > 0 and hours > 0:
        return f"{days} days and {hours} hours"
    if days > 0:
        return f"{days} days"
    return f"{hours} hours"


def clean_value(value: Optional[str]) -> str:
    if not value:
        return "N/A"
    value = str(value).strip()
    return value if value else "N/A"


def normalize_link(value: Optional[str]) -> Optional[str]:
    cleaned = clean_value(value)
    if cleaned == "N/A":
        return None
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned


def build_intro_embed(
    user: discord.User | discord.Member,
    name: str,
    gamertags: str,
    games: str,
    quirks: str,
    twitch: Optional[str],
    youtube: Optional[str],
    about: str,
) -> discord.Embed:
    lines = [
        "╭──╯ . . . . . 𝐼𝓃𝓉𝓇𝑜𝒹𝓊𝒸𝓉𝒾𝑜𝓃 . . . . . ╰──╮",
        "",
        f"/ᐠ - ˕ -マ ⛧ {name} ⛧",
        "",
        "╭∪─∪───────────────",
        f"┊ 🎮 Gamertag(s): {gamertags}",
        f"┊ 🎯 Games: {games}",
        f"┊ ✨ Quirks: {quirks}",
        "╰──────────────────",
        "",
        "⊹ ࣪ ﹏𓊝﹏𓂁﹏⊹ ࣪ ˖",
        "",
    ]

    social_lines = []
    twitch_url = normalize_link(twitch)
    youtube_url = normalize_link(youtube)

    if twitch_url:
        social_lines.append(f"📺 Twitch: [🟣 twitch]({twitch_url})")
    if youtube_url:
        social_lines.append(f"📹 YouTube: [🔴 YouTube]({youtube_url})")

    if social_lines:
        lines.extend(social_lines)
        lines.append("")

    lines.extend(
        [
            "╭──╯ . . . 𝒜𝒷ℴ𝓊𝓉 ℳℯ . . . ╰──╮",
            f"ღ {about} ღ",
            "╰──────────────────────",
        ]
    )

    embed = discord.Embed(
        color=discord.Color.from_str("#D4AF37"),
        description="\n".join(lines),
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="🏮 A new legend enters the Jianghu")
    return embed


class IntroModalPageOne(discord.ui.Modal, title="Jianghu Introduction"):
    def __init__(self):
        super().__init__(timeout=300)

        self.name_input = discord.ui.TextInput(
            label="Name",
            max_length=100,
            required=True,
        )
        self.gamertags_input = discord.ui.TextInput(
            label="Gamertag(s)",
            max_length=200,
            required=True,
        )
        self.games_input = discord.ui.TextInput(
            label="Games",
            max_length=200,
            required=True,
        )
        self.twitch_input = discord.ui.TextInput(
            label="Twitch (optional)",
            max_length=200,
            required=False,
            placeholder="N/A",
        )
        self.youtube_input = discord.ui.TextInput(
            label="YouTube (optional)",
            max_length=200,
            required=False,
            placeholder="N/A",
        )

        self.add_item(self.name_input)
        self.add_item(self.gamertags_input)
        self.add_item(self.games_input)
        self.add_item(self.twitch_input)
        self.add_item(self.youtube_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        modal = IntroModalPageTwo(
            name=self.name_input.value,
            gamertags=self.gamertags_input.value,
            games=self.games_input.value,
            twitch=self.twitch_input.value,
            youtube=self.youtube_input.value,
        )
        await interaction.response.send_modal(modal)


class IntroModalPageTwo(discord.ui.Modal, title="Jianghu Introduction"):
    def __init__(self, name: str, gamertags: str, games: str, twitch: str, youtube: str):
        super().__init__(timeout=300)
        self.saved_name = name
        self.saved_gamertags = gamertags
        self.saved_games = games
        self.saved_twitch = twitch
        self.saved_youtube = youtube

        self.quirks_input = discord.ui.TextInput(
            label="Quirks",
            max_length=200,
            required=True,
        )
        self.about_input = discord.ui.TextInput(
            label="About Me (optional)",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False,
            placeholder="N/A",
        )

        self.add_item(self.quirks_input)
        self.add_item(self.about_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        current = now_ts()

        settings = await get_intro_settings(interaction.guild.id)
        if not settings:
            return await interaction.response.send_message(
                "The introduction system has not been set up yet.",
                ephemeral=True,
            )

        intro_channel = interaction.guild.get_channel(int(settings["intro_channel_id"]))
        if not isinstance(intro_channel, discord.TextChannel):
            return await interaction.response.send_message(
                "The introduction channel is invalid.",
                ephemeral=True,
            )

        existing = await get_user_intro(interaction.user.id, interaction.guild.id)
        if existing:
            remaining = INTRO_COOLDOWN_SECONDS - (current - int(existing["last_used"]))
            if remaining > 0:
                return await interaction.response.send_message(
                    f"🏮 The Jianghu remembers your name.\n\n"
                    f"You may submit another introduction in {format_remaining(remaining)}.",
                    ephemeral=True,
                )

        if existing:
            try:
                old_channel = interaction.guild.get_channel(int(existing["channel_id"]))
                if isinstance(old_channel, discord.TextChannel):
                    old_message = await old_channel.fetch_message(int(existing["message_id"]))
                    await old_message.delete()
            except Exception:
                pass

        embed = build_intro_embed(
            user=interaction.user,
            name=clean_value(self.saved_name),
            gamertags=clean_value(self.saved_gamertags),
            games=clean_value(self.saved_games),
            quirks=clean_value(self.quirks_input.value),
            twitch=self.saved_twitch,
            youtube=self.saved_youtube,
            about=clean_value(self.about_input.value),
        )

        sent = await intro_channel.send(embed=embed)

        # move panel after every successful introduction
        if interaction.guild.id not in interaction.client.repost_locks:
            interaction.client.repost_locks.add(interaction.guild.id)
            try:
                panel_message_id = int(settings["panel_message_id"]) if settings["panel_message_id"] else None

                try:
                    if panel_message_id:
                        old_panel = await intro_channel.fetch_message(panel_message_id)
                        await old_panel.delete()
                except Exception:
                    pass

                new_panel = await send_intro_panel(intro_channel)
                await update_panel_state(interaction.guild.id, new_panel.id, now_ts())
            finally:
                interaction.client.repost_locks.discard(interaction.guild.id)

        await upsert_user_intro(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id,
            channel_id=intro_channel.id,
            message_id=sent.id,
            last_used=current,
        )

        await interaction.response.send_message(
            "🏮 Your introduction has been recorded in the Jianghu.",
            ephemeral=True,
        )


class IntroPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Introduce Yourself",
        style=discord.ButtonStyle.primary,
        custom_id="intro_button",
    )
    async def introduce_yourself(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        existing = await get_user_intro(interaction.user.id, interaction.guild.id)
        if existing:
            remaining = INTRO_COOLDOWN_SECONDS - (now_ts() - int(existing["last_used"]))
            if remaining > 0:
                return await interaction.response.send_message(
                    f"🏮 The Jianghu remembers your name.\n\n"
                    f"You may submit another introduction in {format_remaining(remaining)}.",
                    ephemeral=True,
                )

        await interaction.response.send_modal(IntroModalPageOne())


async def send_intro_panel(channel: discord.TextChannel) -> discord.Message:
    embed = discord.Embed(
        title="🏮 New User Introductions",
        description=(
            "Step forward and share your story with the Jianghu.\n\n"
            "Click the button below to introduce yourself.\n"
            "You may submit a new introduction once every 7 days.\n"
            "Your previous introduction will be automatically replaced."
        ),
        color=discord.Color.from_str("#D4AF37"),
    )

    return await channel.send(embed=embed, view=IntroPanelView())


intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.repost_locks = set()


class IntroGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="intro", description="Introduction system commands")

    @app_commands.command(name="setup", description="Set the introduction channel and post the panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        settings = await get_intro_settings(interaction.guild.id)

        if settings and settings["panel_message_id"]:
            try:
                old_channel = interaction.guild.get_channel(int(settings["intro_channel_id"]))
                if isinstance(old_channel, discord.TextChannel):
                    old_panel = await old_channel.fetch_message(int(settings["panel_message_id"]))
                    await old_panel.delete()
            except Exception:
                pass

        panel_message = await send_intro_panel(channel)

        await upsert_intro_settings(
            guild_id=interaction.guild.id,
            intro_channel_id=channel.id,
            panel_message_id=panel_message.id,
            updated_at=now_ts(),
        )

        await interaction.response.send_message(
            f"Introduction setup complete in {channel.mention}.",
            ephemeral=True,
        )


bot.tree.add_command(IntroGroup())


@bot.event
async def on_ready():
    await connect_db(DATABASE_URL)
    await setup_tables()
    bot.add_view(IntroPanelView())

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as exc:
        print(f"Failed to sync commands: {exc}")

    await bot.change_presence(activity=discord.Game(name=BOT_STATUS_TEXT))
    print(f"Logged in as {bot.user} ({bot.user.id})")


@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)


async def keep_database_awake():
    while True:
        try:
            from database import get_pool
            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1;")
        except Exception as exc:
            print(f"Database keep-alive failed: {exc}")
        await asyncio.sleep(240)


@bot.event
async def setup_hook():
    bot.loop.create_task(keep_database_awake())


bot.run(DISCORD_TOKEN)