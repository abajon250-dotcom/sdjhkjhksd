import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID")
ADMIN_LOG_CHAT_ID = int(os.getenv("ADMIN_LOG_CHAT_ID", 0))
CRYPTOBOT_API_TOKEN = os.getenv("CRYPTOBOT_API_TOKEN", "")