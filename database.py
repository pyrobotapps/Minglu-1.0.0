import asyncpg
from typing import Optional

_pool: Optional[asyncpg.Pool] = None


async def connect_db(database_url: str) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
    return _pool


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool has not been initialized.")
    return _pool


async def setup_tables() -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intro_settings (
                guild_id TEXT PRIMARY KEY,
                intro_channel_id TEXT NOT NULL,
                panel_message_id TEXT,
                updated_at BIGINT NOT NULL
            );
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS introductions (
                user_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                last_used BIGINT NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            );
            """
        )


async def get_intro_settings(guild_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT guild_id, intro_channel_id, panel_message_id, updated_at
            FROM intro_settings
            WHERE guild_id = $1
            """,
            str(guild_id),
        )


async def upsert_intro_settings(
    guild_id: int,
    intro_channel_id: int,
    panel_message_id: Optional[int],
    updated_at: int,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO intro_settings (guild_id, intro_channel_id, panel_message_id, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id) DO UPDATE SET
                intro_channel_id = EXCLUDED.intro_channel_id,
                panel_message_id = EXCLUDED.panel_message_id,
                updated_at = EXCLUDED.updated_at
            """,
            str(guild_id),
            str(intro_channel_id),
            str(panel_message_id) if panel_message_id else None,
            updated_at,
        )


async def update_panel_state(guild_id: int, panel_message_id: int, updated_at: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE intro_settings
            SET panel_message_id = $1,
                updated_at = $2
            WHERE guild_id = $3
            """,
            str(panel_message_id),
            updated_at,
            str(guild_id),
        )


async def get_user_intro(user_id: int, guild_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT user_id, guild_id, channel_id, message_id, last_used
            FROM introductions
            WHERE user_id = $1 AND guild_id = $2
            """,
            str(user_id),
            str(guild_id),
        )


async def upsert_user_intro(
    user_id: int,
    guild_id: int,
    channel_id: int,
    message_id: int,
    last_used: int,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO introductions (user_id, guild_id, channel_id, message_id, last_used)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                message_id = EXCLUDED.message_id,
                last_used = EXCLUDED.last_used
            """,
            str(user_id),
            str(guild_id),
            str(channel_id),
            str(message_id),
            last_used,
        )