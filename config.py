import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

AZURE_KEY = os.getenv("AZURE_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")
AZURE_REGION = os.getenv("AZURE_REGION")

INTRO_COOLDOWN_SECONDS = 7 * 24 * 60 * 60
PANEL_BUMP_COUNT = 4
BOT_STATUS_TEXT = "WWM introductions"