import os
from pathlib import Path

# Load .env file
env_path = Path(__file__).parent / ".env"

if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path)
    except ImportError:
        # Fallback manual parser if python-dotenv is not installed
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key not in os.environ:
                        os.environ[key] = val

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Check interval in seconds (default 60 seconds / 1 minute)
try:
    CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
except ValueError:
    CHECK_INTERVAL = 60

# 'edit' (re-uses and updates the same pinned message) or 'new' (sends new message every minute)
UPDATE_MODE = os.getenv("UPDATE_MODE", "edit").lower().strip()

POLIS_URL = os.getenv(
    "POLIS_URL",
    "https://dex.coinmarketcap.com/token/solana/poLisWXnNRwC6oBu1vHiuKQzFjGL4XDSu4g9qjz9qVk/"
).strip()

ATLAS_URL = os.getenv(
    "ATLAS_URL",
    "https://dex.coinmarketcap.com/token/solana/ATLASXmbPQxBUYbxPsV97usA3fPQYEqzQBUHgiFCUsXx/"
).strip()

CMC_URL = POLIS_URL
