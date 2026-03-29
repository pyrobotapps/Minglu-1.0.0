import asyncio
import time
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

from config import (
    DISCORD_TOKEN,
    INTRO_COOLDOWN_SECONDS,
    PANEL_BUMP_COUNT,
    BOT_STATUS_TEXT,
)
from database import (
    connect_db,
    setup_tables,
    get_intro_settings,
    upsert_intro_settings,
    update_panel_state,
    increment_bump_counter,
    get_user_intro,
    upsert_user_intro,
)
from translator import translate_text, LANG_CODES


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


def format_link(label: str, url: str, emoji: str) -> str:
    value = clean_value(url)
    if value == "N/A":
        return "N/A"

    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"

    return f"[{emoji} {label}]({value})"


def build_intro_embed(
    user: discord.User | discord.Member,
    name: str,
    gamertags: str,
    games: str,
    quirks: str,
    twitch: str,
    youtube: str,
    about: str,
    cn: str,
    jp: str,
    kr: str,
    th: str,
    ru: str,
) -> discord.Embed:
    description = "\n".join([
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
        f"📺 Twitch: {twitch}",
        f"📹 YouTube: {youtube}",
        "",
        "╭──╯ . . . 𝒜𝒷ℴ𝓊𝓉 ℳℯ . . . ╰──╮",
        f"ღ {about} ღ",
        "╰──────────────────────",
        "",
        "🌍 Translations",
        "",
        f"🇨🇳 中文:\n{cn}",
        "",
        f"🇯🇵 日本語:\n{jp}",
        "",
        f"🇰🇷 한국어:\n{kr}",
        "",
        f"🇹🇭 ไทย:\n{th}",
        "",
        f"🇷🇺 Русский:\n{ru}",
    ])

    embed = discord.Embed(
        color=0xD4AF37,
        description=description
    )
    embed.set_author(
        name=user.display_name if isinstance(user, discord.Member) else user.name,
        icon_url=user.display_avatar.url
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="🏮 Recorded by Minglu")
    return embed


async def send_intro_panel(channel: discord.TextChannel) -> discord.Message:
    embed = discord.Embed(
        title="🏮 Minglu • 名录",
        description=(
            "Step forward and record your name in the Jianghu.\n\n"
            "Click the button below to introduce yourself.\n"
            "You may submit a new introduction once every 7 days.\n"
            "Your previous introduction will be automatically replaced."
        ),
        color=0xD4AF37
    )
    return await channel.send(embed=embed, view=IntroPanelView())


class IntroPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Record Your Name",
        style=discord.ButtonStyle.primary,
        custom_id="minglu:intro:start"
    )
    async def start_intro(self, interaction: discord.Interaction, _: discord.ui.Button):
        existing = await get_user_intro(interaction.user.id)
        current = now_ts()

        if existing:
            remaining = INTRO_COOLDOWN_SECONDS - (current - int(existing["last_used"]))
            if remaining > 0:
                return await interaction.response.send_message(
                    f"🏮 The Minglu remembers your name.\n\n"
                    f"You may submit another introduction in **{format_remaining(remaining)}**.",
                    ephemeral=True
                )

        await interaction.response.send_modal(IntroModalPageOne())


class IntroModalPageOne(discord.ui.Modal, title="Minglu Introduction • Page 1"):
    name = discord.ui.TextInput(label="Name", max_length=100)
    gamertags = discord.ui.TextInput(label="Gamertag(s)", max_length=200)
    games = discord.ui.TextInput(label="Games", max_length=200)
    twitch = discord.ui.TextInput(
        label="Twitch (optional)",
        required=False,
        max_length=200,
        placeholder="N/A"
    )
    youtube = discord.ui.TextInput(
        label="YouTube (optional)",
        required=False,
        max_length=200,
        placeholder="N/A"
    )

    async def on_submit(self, interaction: discord.Interaction):
        payload = {
            "name": str(self.name),
            "gamertags": str(self.gamertags),
            "games": str(self.games),
            "twitch": str(self.twitch),
            "youtube": str(self.youtube),
        }
        await interaction.response.send_modal(IntroModalPageTwo(payload))


class IntroModalPageTwo(discord.ui.Modal, title="Minglu Introduction • Page 2"):
    quirks = discord.ui.TextInput(label="Quirks", max_length=200)
    about = discord.ui.TextInput(
        label="About Me (optional)",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=1000,
        placeholder="N/A"
    )

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload

    async def on_submit(self, interaction: discord.Interaction):
        settings = await get_intro_settings(interaction.guild.id if interaction.guild else 0)
        if not settings:
            return await interaction.response.send_message(
                "Minglu has not been set up in this server yet. Run `/intro_setup` first.",
                ephemeral=True
            )

        intro_channel = interaction.guild.get_channel(int(settings["intro_channel_id"]))
        if not isinstance(intro_channel, discord.TextChannel):
            return await interaction.response.send_message(
                "The introduction channel is not configured correctly.",
                ephemeral=True
            )

        existing = await get_user_intro(interaction.user.id)
        current = now_ts()

        if existing:
            remaining = INTRO_COOLDOWN_SECONDS - (current - int(existing["last_used"]))
            if remaining > 0:
                return await interaction.response.send_message(
                    f"🏮 The Minglu remembers your name.\n\n"
                    f"You may submit another introduction in **{format_remaining(remaining)}**.",
                    ephemeral=True
                )
            
        name = clean_value(self.payload["name"])
        gamertags = clean_value(self.payload["gamertags"])
        games = clean_value(self.payload["games"])
        quirks = clean_value(str(self.quirks))
        about = clean_value(str(self.about))
        twitch = format_link("Twitch", self.payload["twitch"], "🟣")
        youtube = format_link("YouTube", self.payload["youtube"], "🔴")

        text_to_translate = f"Quirks: {quirks}\nAbout Me: {about}"

        async with aiohttp.ClientSession() as session:
            cn, jp, kr, th, ru = await asyncio.gather(
                translate_text(session, text_to_translate, LANG_CODES["zh"]),
                translate_text(session, text_to_translate, LANG_CODES["ja"]),
                translate_text(session, text_to_translate, LANG_CODES["ko"]),
                translate_text(session, text_to_translate, LANG_CODES["th"]),
                translate_text(session, text_to_translate, LANG_CODES["ru"]),
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
            name=name,
            gamertags=gamertags,
            games=games,
            quirks=quirks,
            twitch=twitch,
            youtube=youtube,
            about=about,
            cn=cn,
            jp=jp,
            kr=kr,
            th=th,
            ru=ru,
        )

        sent = await intro_channel.send(embed=embed)

        await upsert_user_intro(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id,
            channel_id=intro_channel.id,
            message_id=sent.id,
            last_used=current,
        )

        await interaction.response.send_message(
            "🏮 Your name has been recorded in the Minglu.",
            ephemeral=True
        )


class MingiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.repost_locks: set[int] = set()

    async def setup_hook(self):
        await connect_db()
        await setup_tables()
        self.add_view(IntroPanelView())
        await self.tree.sync()


bot = MingiBot()


@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=BOT_STATUS_TEXT
        )
    )
    print(f"Logged in as {bot.user}")
@bot.tree.command(name="intro_setup", description="Set up Minglu in a channel")
@app_commands.describe(channel="Channel for introductions and the intro panel")
@app_commands.checks.has_permissions(administrator=True)
async def intro_setup(interaction: discord.Interaction, channel: discord.TextChannel):
    old_settings = await get_intro_settings(interaction.guild.id)
    if old_settings and old_settings["panel_message_id"]:
        try:
            old_channel = interaction.guild.get_channel(int(old_settings["intro_channel_id"]))
            if isinstance(old_channel, discord.TextChannel):
                old_message = await old_channel.fetch_message(int(old_settings["panel_message_id"]))
                await old_message.delete()
        except Exception:
            pass

    panel_message = await send_intro_panel(channel)

    await upsert_intro_settings(
        guild_id=interaction.guild.id,
        intro_channel_id=channel.id,
        panel_message_id=panel_message.id,
        messages_since_bump=0,
        updated_at=now_ts(),
    )

    await interaction.response.send_message(
        f"🏮 Minglu has been set up in {channel.mention}.",
        ephemeral=True
    )


@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)

    if not message.guild or message.author.id == bot.user.id:
        return

    settings = await get_intro_settings(message.guild.id)
    if not settings:
        return

    intro_channel_id = int(settings["intro_channel_id"])
    panel_message_id = int(settings["panel_message_id"]) if settings["panel_message_id"] else None

    if message.channel.id != intro_channel_id:
        return

    if panel_message_id and message.id == panel_message_id:
        return

    if message.guild.id in bot.repost_locks:
        return

    count = await increment_bump_counter(message.guild.id, now_ts())
    if count < PANEL_BUMP_COUNT:
        return

    bot.repost_locks.add(message.guild.id)
    try:
        try:
            if panel_message_id:
                old_panel = await message.channel.fetch_message(panel_message_id)
                await old_panel.delete()
        except Exception:
            pass

        new_panel = await send_intro_panel(message.channel)
        await update_panel_state(message.guild.id, new_panel.id, now_ts())

    finally:
        bot.repost_locks.discard(message.guild.id)


bot.run(DISCORD_TOKEN)