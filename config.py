import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Admin user IDs (Telegram user_id) who have access to /admin
ADMIN_IDS = [
    # Add admin Telegram user IDs here, e.g.:
    # 123456789,
    # 987654321,
]

DATABASE_URL = "giveaway_bot.db"
