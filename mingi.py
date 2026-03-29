import asyncio
import time
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

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


def now_ts():
    return int(time.time())


def format_remaining(seconds: int):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    return f"{days}d {hours}h"


def clean(v):
    return v if v and v.strip() else "N/A"


def format_link(label, url, emoji):
    if not url or url.strip().lower() == "n/a":
        return "N/A"
    if not url.startswith("http"):
        url = "https://" + url
    return f"[{emoji} {label}]({url})"


def build_embed(user, data, translations):
    desc = f"""
╭──╯ . . . . . 𝐼𝓃𝓉𝓇𝑜𝒹𝓊𝒸𝓉𝒾𝑜𝓃 . . . . . ╰──╮

⛧ {data['name']} ⛧

🎮 Gamertag(s): {data['gamertags']}
🎯 Games: {data['games']}
✨ Quirks: {data['quirks']}

📺 Twitch: {data['twitch']}
📹 YouTube: {data['youtube']}

╭──╯ . . . 𝒜𝒷ℴ𝓊𝓉 ℳℯ . . . ╰──╮
ღ {data['about']} ღ

🌍 Translations

🇨🇳 {translations[0]}

🇯🇵 {translations[1]}

🇰🇷 {translations[2]}

🇹🇭 {translations[3]}

🇷🇺 {translations[4]}
"""

    embed = discord.Embed(description=desc, color=0xD4AF37)
    embed.set_author(name=user.name, icon_url=user.display_avatar.url)
    embed.set_footer(text="🏮 Recorded by Minglu")
    return embed


async def send_panel(channel):
    embed = discord.Embed(
        title="🏮 Minglu • 名录",
        description="Record your name in the Jianghu.",
        color=0xD4AF37
    )
    return await channel.send(embed=embed, view=IntroView())

class IntroView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Record Your Name", style=discord.ButtonStyle.primary, custom_id="intro_btn")
    async def intro(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_data = await get_user_intro(interaction.user.id)

        if user_data:
            remaining = INTRO_COOLDOWN_SECONDS - (now_ts() - user_data["last_used"])
            if remaining > 0:
                return await interaction.response.send_message(
                    f"🏮 You can introduce again in {format_remaining(remaining)}",
                    ephemeral=True
                )

        await interaction.response.send_modal(IntroPage1())


class IntroPage1(discord.ui.Modal, title="Intro Page 1"):
    name = discord.ui.TextInput(label="Name")
    gamertags = discord.ui.TextInput(label="Gamertags")
    games = discord.ui.TextInput(label="Games")
    twitch = discord.ui.TextInput(label="Twitch (optional)", required=False)
    youtube = discord.ui.TextInput(label="YouTube (optional)", required=False)

    async def on_submit(self, interaction):
        data = {
            "name": str(self.name),
            "gamertags": str(self.gamertags),
            "games": str(self.games),
            "twitch": str(self.twitch),
            "youtube": str(self.youtube),
        }
        await interaction.response.send_modal(IntroPage2(data))


class IntroPage2(discord.ui.Modal, title="Intro Page 2"):
    quirks = discord.ui.TextInput(label="Quirks")
    about = discord.ui.TextInput(label="About", style=discord.TextStyle.paragraph, required=False)

    def __init__(self, data):
        super().__init__()
        self.data = data

    async def on_submit(self, interaction):
        settings = await get_intro_settings(interaction.guild.id)
        channel = interaction.guild.get_channel(settings["intro_channel_id"])

        self.data["quirks"] = clean(str(self.quirks))
        self.data["about"] = clean(str(self.about))
        self.data["twitch"] = format_link("Twitch", self.data["twitch"], "🟣")
        self.data["youtube"] = format_link("YouTube", self.data["youtube"], "🔴")

        text = f"{self.data['quirks']} {self.data['about']}"

        async with aiohttp.ClientSession() as session:
            translations = await asyncio.gather(
                translate_text(session, text, LANG_CODES["zh"]),
                translate_text(session, text, LANG_CODES["ja"]),
                translate_text(session, text, LANG_CODES["ko"]),
                translate_text(session, text, LANG_CODES["th"]),
                translate_text(session, text, LANG_CODES["ru"]),
            )

        old = await get_user_intro(interaction.user.id)
        if old:
            try:
                msg = await channel.fetch_message(old["message_id"])
                await msg.delete()
            except:
                pass

        embed = build_embed(interaction.user, self.data, translations)
        msg = await channel.send(embed=embed)

        await upsert_user_intro(
            interaction.user.id,
            interaction.guild.id,
            channel.id,
            msg.id,
            now_ts()
        )
        await interaction.response.send_message("🏮 Recorded.", ephemeral=True)


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())

    async def setup_hook(self):
        await connect_db()
        await setup_tables()
        self.add_view(IntroView())
        await self.tree.sync()


bot = Bot()


@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=BOT_STATUS_TEXT
        )
    )
    print("Bot online")


@bot.tree.command(name="intro")
@app_commands.describe(channel="Intro channel")
async def setup(interaction: discord.Interaction, channel: discord.TextChannel):
    msg = await send_panel(channel)

    await upsert_intro_settings(
        interaction.guild.id,
        channel.id,
        msg.id,
        0,
        now_ts()
    )

    await interaction.response.send_message("Setup complete", ephemeral=True)


@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if not message.guild or message.author.bot:
        return

    settings = await get_intro_settings(message.guild.id)
    if not settings:
        return

    if message.channel.id != settings["intro_channel_id"]:
        return

    count = await increment_bump_counter(message.guild.id, now_ts())

    if count >= PANEL_BUMP_COUNT:
        try:
            old = await message.channel.fetch_message(settings["panel_message_id"])
            await old.delete()
        except:
            pass

        new = await send_panel(message.channel)
        await update_panel_state(message.guild.id, new.id, now_ts())


bot.run(DISCORD_TOKEN)