import asyncpg
from config import DATABASE_URL

pool: asyncpg.Pool | None = None


async def connect_db() -> asyncpg.Pool:
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    return pool


async def setup_tables() -> None:
    assert pool is not None

    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS intro_settings (
            guild_id BIGINT PRIMARY KEY,
            intro_channel_id BIGINT NOT NULL,
            panel_message_id BIGINT,
            messages_since_bump INTEGER NOT NULL DEFAULT 0,
            updated_at BIGINT NOT NULL
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS introductions (
            user_id BIGINT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            last_used BIGINT NOT NULL
        )
        """)

async def get_intro_settings(guild_id: int):
    assert pool is not None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM intro_settings WHERE guild_id = $1",
            guild_id
        )


async def upsert_intro_settings(
    guild_id: int,
    intro_channel_id: int,
    panel_message_id: int | None,
    messages_since_bump: int = 0,
    updated_at: int = 0,
) -> None:
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO intro_settings (
            guild_id, intro_channel_id, panel_message_id, messages_since_bump, updated_at
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (guild_id) DO UPDATE SET
            intro_channel_id = EXCLUDED.intro_channel_id,
            panel_message_id = EXCLUDED.panel_message_id,
            messages_since_bump = EXCLUDED.messages_since_bump,
            updated_at = EXCLUDED.updated_at
        """, guild_id, intro_channel_id, panel_message_id, messages_since_bump, updated_at)


async def update_panel_state(guild_id: int, panel_message_id: int, updated_at: int) -> None:
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute("""
        UPDATE intro_settings
        SET panel_message_id = $1,
            messages_since_bump = 0,
            updated_at = $2
        WHERE guild_id = $3
        """, panel_message_id, updated_at, guild_id)


async def increment_bump_counter(guild_id: int, updated_at: int) -> int:
    assert pool is not None
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
        UPDATE intro_settings
        SET messages_since_bump = messages_since_bump + 1,
            updated_at = $2
        WHERE guild_id = $1
        RETURNING messages_since_bump
        """, guild_id, updated_at)
        return int(row["messages_since_bump"]) if row else 0


async def reset_bump_counter(guild_id: int, updated_at: int) -> None:
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute("""
        UPDATE intro_settings
        SET messages_since_bump = 0,
            updated_at = $2
        WHERE guild_id = $1
        """, guild_id, updated_at)


async def get_user_intro(user_id: int):
    assert pool is not None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM introductions WHERE user_id = $1",
            user_id
        )


async def upsert_user_intro(
    user_id: int,
    guild_id: int,
    channel_id: int,
    message_id: int,
    last_used: int
) -> None:
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute("""
        INSERT INTO introductions (user_id, guild_id, channel_id, message_id, last_used)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id) DO UPDATE SET
            guild_id = EXCLUDED.guild_id,
            channel_id = EXCLUDED.channel_id,
            message_id = EXCLUDED.message_id,
            last_used = EXCLUDED.last_used
        """, user_id, guild_id, channel_id, message_id, last_used)