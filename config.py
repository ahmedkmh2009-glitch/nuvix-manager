import os

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SELLAUTH_API_KEY = os.getenv("SELLAUTH_API_KEY")
SELLAUTH_SHOP_ID = os.getenv("SELLAUTH_SHOP_ID")

def _parse_ids(value: str):
    ids = []
    if not value:
        return ids
    for part in value.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids

# Owner (single)
OWNER_ID = int(os.getenv("OWNER_ID", "1310330017963839622"))

# Role lists (two per type, but can be 1 or more)
USER_ROLE_IDS = _parse_ids(os.getenv("USER_ROLE_IDS", "1432474583927361638,1432828668001914983"))
STAFF_ROLE_IDS = _parse_ids(os.getenv("STAFF_ROLE_IDS", "1445039975199674388,1432829631852970095"))
ADMIN_ROLE_IDS = _parse_ids(os.getenv("ADMIN_ROLE_IDS", "1442219517555245156,1432829627000160378"))

# Single channel IDs (can be overridden in ENV)
SELL_CHANNEL_ID = int(os.getenv("SELL_CHANNEL_ID", "1443350157650559118"))
FEEDBACK_CHANNEL_ID = int(os.getenv("FEEDBACK_CHANNEL_ID", "1432474754740125706"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "1432474771660079329"))
ANNOUNCE_CHANNEL_ID = int(os.getenv("ANNOUNCE_CHANNEL_ID", "1432474701082398720"))

DB_PATH = os.getenv("DB_PATH", "nuvixmarket.db")
