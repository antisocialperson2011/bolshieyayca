import aiosqlite
import logging
from datetime import datetime
from config import DATABASE_URL

logger = logging.getLogger(__name__)


async def init_db():
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_at TEXT NOT NULL,
                is_banned INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL UNIQUE,
                channel_name TEXT,
                channel_username TEXT,
                added_at TEXT NOT NULL,
                is_banned INTEGER DEFAULT 0,
                FOREIGN KEY (owner_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                title TEXT,
                description TEXT,
                media_type TEXT,
                media_file_id TEXT,
                button_name TEXT,
                required_channels TEXT,
                end_type TEXT,
                end_value TEXT,
                ref_link TEXT UNIQUE,
                is_active INTEGER DEFAULT 1,
                winner_id INTEGER DEFAULT NULL,
                created_at TEXT NOT NULL,
                ended_at TEXT,
                FOREIGN KEY (owner_id) REFERENCES users(user_id),
                FOREIGN KEY (winner_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giveaway_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                UNIQUE(giveaway_id, user_id),
                FOREIGN KEY (giveaway_id) REFERENCES giveaways(id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                extra_data TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Migration: add winner_id column if it doesn't exist yet (for old DBs)
        try:
            await db.execute("ALTER TABLE giveaways ADD COLUMN winner_id INTEGER DEFAULT NULL")
            logger.info("Migration: added winner_id column to giveaways")
        except Exception:
            pass  # Column already exists

        await db.commit()
    logger.info("Database initialized")


async def get_or_create_user(user_id: int, username: str, first_name: str, last_name: str) -> dict:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        if user:
            return dict(user)
        now = datetime.utcnow().isoformat()
        await db.execute(
            "INSERT INTO users (user_id, username, first_name, last_name, registered_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, last_name, now)
        )
        await db.commit()
        await log_event("new_user", user_id, f"{first_name} @{username}")
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return dict(await cursor.fetchone())


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_URL) as db:
        async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row else False


# --- Channels ---

async def add_channel(owner_id: int, channel_id: str, channel_name: str, channel_username: str) -> bool:
    async with aiosqlite.connect(DATABASE_URL) as db:
        now = datetime.utcnow().isoformat()
        try:
            await db.execute(
                "INSERT INTO channels (owner_id, channel_id, channel_name, channel_username, added_at) VALUES (?, ?, ?, ?, ?)",
                (owner_id, channel_id, channel_name, channel_username, now)
            )
            await db.commit()
            await log_event("channel_added", owner_id, f"channel_id={channel_id} name={channel_name}")
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_user_channels(owner_id: int) -> list:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM channels WHERE owner_id = ? AND is_banned = 0 ORDER BY added_at DESC",
            (owner_id,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_channel_by_id(channel_id: str) -> dict | None:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def delete_channel(owner_id: int, channel_id: str):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "DELETE FROM channels WHERE owner_id = ? AND channel_id = ?",
            (owner_id, channel_id)
        )
        await db.commit()
        await log_event("channel_deleted", owner_id, f"channel_id={channel_id}")


# --- Giveaways ---

async def create_giveaway(data: dict) -> int:
    async with aiosqlite.connect(DATABASE_URL) as db:
        now = datetime.utcnow().isoformat()
        cursor = await db.execute(
            """INSERT INTO giveaways
            (owner_id, channel_id, title, description, media_type, media_file_id,
             button_name, required_channels, end_type, end_value, ref_link, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["owner_id"], data["channel_id"], data.get("title"),
                data.get("description"), data.get("media_type"), data.get("media_file_id"),
                data.get("button_name"), data.get("required_channels"),
                data.get("end_type"), data.get("end_value"),
                data["ref_link"], now
            )
        )
        giveaway_id = cursor.lastrowid
        await db.commit()
        await log_event("giveaway_created", data["owner_id"], f"giveaway_id={giveaway_id} channel={data['channel_id']}")
        return giveaway_id


async def get_all_user_giveaways(owner_id: int) -> list:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM giveaways WHERE owner_id = ? ORDER BY created_at DESC",
            (owner_id,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_active_giveaways(owner_id: int) -> list:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM giveaways WHERE owner_id = ? AND is_active = 1 ORDER BY created_at DESC",
            (owner_id,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_giveaway_by_ref(ref_link: str) -> dict | None:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM giveaways WHERE ref_link = ? AND is_active = 1",
            (ref_link,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_giveaway_by_id(giveaway_id: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def end_giveaway(giveaway_id: int, owner_id: int, winner_id: int = None):
    async with aiosqlite.connect(DATABASE_URL) as db:
        now = datetime.utcnow().isoformat()
        await db.execute(
            "UPDATE giveaways SET is_active = 0, ended_at = ?, winner_id = ? WHERE id = ?",
            (now, winner_id, giveaway_id)
        )
        await db.commit()
        await log_event(
            "giveaway_ended", owner_id,
            f"giveaway_id={giveaway_id} winner_id={winner_id}"
        )


async def get_random_winner(giveaway_id: int) -> dict | None:
    """Pick a random participant and return their user record."""
    import random
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT u.* FROM participants p
               JOIN users u ON p.user_id = u.user_id
               WHERE p.giveaway_id = ? AND u.is_banned = 0""",
            (giveaway_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    if not rows:
        return None
    return dict(random.choice(rows))


async def get_all_participants(giveaway_id: int) -> list:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT u.user_id, u.username, u.first_name, u.last_name, p.joined_at
               FROM participants p
               JOIN users u ON p.user_id = u.user_id
               WHERE p.giveaway_id = ?
               ORDER BY p.joined_at""",
            (giveaway_id,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def add_participant(giveaway_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_URL) as db:
        now = datetime.utcnow().isoformat()
        try:
            await db.execute(
                "INSERT INTO participants (giveaway_id, user_id, joined_at) VALUES (?, ?, ?)",
                (giveaway_id, user_id, now)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def is_participant(giveaway_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_URL) as db:
        async with db.execute(
            "SELECT 1 FROM participants WHERE giveaway_id = ? AND user_id = ?",
            (giveaway_id, user_id)
        ) as cursor:
            return await cursor.fetchone() is not None


async def get_participants_count(giveaway_id: int) -> int:
    async with aiosqlite.connect(DATABASE_URL) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM participants WHERE giveaway_id = ?",
            (giveaway_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


# --- Logs ---

async def log_event(event_type: str, user_id: int = None, extra_data: str = None):
    async with aiosqlite.connect(DATABASE_URL) as db:
        now = datetime.utcnow().isoformat()
        await db.execute(
            "INSERT INTO logs (event_type, user_id, extra_data, created_at) VALUES (?, ?, ?, ?)",
            (event_type, user_id, extra_data, now)
        )
        await db.commit()


# --- Admin functions ---

async def get_all_channels(limit: int = 50) -> list:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT c.*, u.username, u.first_name FROM channels c LEFT JOIN users u ON c.owner_id = u.user_id ORDER BY c.added_at DESC LIMIT ?",
            (limit,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_all_giveaways(limit: int = 50) -> list:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT g.*, u.username, u.first_name FROM giveaways g LEFT JOIN users u ON g.owner_id = u.user_id ORDER BY g.created_at DESC LIMIT ?",
            (limit,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_all_logs(limit: int = 100) -> list:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT l.*, u.username FROM logs l LEFT JOIN users u ON l.user_id = u.user_id ORDER BY l.created_at DESC LIMIT ?",
            (limit,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def ban_channel(channel_id: str):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("UPDATE channels SET is_banned = 1 WHERE channel_id = ?", (channel_id,))
        await db.commit()
        await log_event("channel_banned", None, f"channel_id={channel_id}")


async def unban_channel(channel_id: str):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("UPDATE channels SET is_banned = 0 WHERE channel_id = ?", (channel_id,))
        await db.commit()
        await log_event("channel_unbanned", None, f"channel_id={channel_id}")


async def ban_user(user_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        await db.commit()
        await log_event("user_banned", None, f"user_id={user_id}")


async def unban_user(user_id: int):
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        await db.commit()
        await log_event("user_unbanned", None, f"user_id={user_id}")


async def get_stats() -> dict:
    async with aiosqlite.connect(DATABASE_URL) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1") as c:
            banned_users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM channels") as c:
            total_channels = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM channels WHERE is_banned = 1") as c:
            banned_channels = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM giveaways") as c:
            total_giveaways = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM giveaways WHERE is_active = 1") as c:
            active_giveaways = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM participants") as c:
            total_participants = (await c.fetchone())[0]
    return {
        "total_users": total_users,
        "banned_users": banned_users,
        "total_channels": total_channels,
        "banned_channels": banned_channels,
        "total_giveaways": total_giveaways,
        "active_giveaways": active_giveaways,
        "total_participants": total_participants,
    }
