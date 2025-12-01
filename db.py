import sqlite3
import config

def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Vouches
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vouches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            content TEXT,
            stars INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Blacklist
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS blacklist (
            guild_id INTEGER,
            user_id INTEGER,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Ticket bans
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_bans (
            guild_id INTEGER,
            user_id INTEGER,
            reason TEXT,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )

    # Guild config (channels by guild if needed in futuro)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            sell_channel_id INTEGER,
            feedback_channel_id INTEGER,
            log_channel_id INTEGER,
            announce_channel_id INTEGER
        )
        """
    )

    conn.commit()
    conn.close()
