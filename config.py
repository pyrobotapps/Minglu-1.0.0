import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
BOT_STATUS_TEXT = os.getenv("BOT_STATUS_TEXT", "🏮 Recording legends in the Jianghu")
INTRO_COOLDOWN_SECONDS = 7 * 24 * 60 * 60  # 7 days