import asyncio
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import discord

from scarlet.bot import Scarlet
from scarlet.config import Settings


def make_bot(about="I may not be real - but I am still fluffy!", guild_id=None):
    settings = Settings(
        discord_token="x",
        bot_about=about,
        git_sha="8fa4a66abc",
        git_date="2026-10-05",
        guild_id=guild_id,
    )
    bot = Scarlet(settings)
    bot.http = Mock()
    bot.http.bulk_upsert_global_commands = AsyncMock()
    bot.http.bulk_upsert_guild_commands = AsyncMock()
    info = Mock()
    info.edit = AsyncMock()
    bot.application_info = AsyncMock(return_value=info)
    return bot, info


def test_the_profile_is_rewritten_when_the_build_changed():
    bot, info = make_bot()
    info.description = "I may not be real - but I am still fluffy!\n\nRunning 1234567"
    asyncio.run(bot._update_about())
    info.edit.assert_awaited_once_with(
        description="I may not be real - but I am still fluffy!\n\nRunning 8fa4a66"
    )


def test_the_profile_is_left_alone_when_it_already_says_so():
    bot, info = make_bot()
    info.description = "I may not be real - but I am still fluffy!\n\nRunning 8fa4a66"
    asyncio.run(bot._update_about())
    info.edit.assert_not_awaited()


def test_a_failed_profile_edit_does_not_take_her_down(caplog):
    bot, info = make_bot()
    info.description = "something else"
    info.edit = AsyncMock(side_effect=discord.HTTPException(Mock(status=500), "no"))
    asyncio.run(bot._update_about())  # must not raise
    assert "could not update the About Me" in caplog.text


# the command scope the settings do not use is emptied on login, so a guild
# synced under GUILD_ID during development does not show everything twice


def in_guilds(bot, *ids):
    guilds = [Mock(id=i) for i in ids]
    return patch.object(
        type(bot), "guilds", new_callable=PropertyMock, return_value=guilds
    )


def test_with_a_guild_id_the_global_scope_is_emptied():
    bot, _ = make_bot(guild_id=42)
    with in_guilds(bot, 42), patch.object(type(bot), "application_id", 7):
        asyncio.run(bot._sweep_stale_commands())
    bot.http.bulk_upsert_global_commands.assert_awaited_once_with(7, [])
    bot.http.bulk_upsert_guild_commands.assert_not_awaited()


def test_without_a_guild_id_every_guild_scope_is_emptied():
    bot, _ = make_bot(guild_id=None)
    with in_guilds(bot, 42, 43), patch.object(type(bot), "application_id", 7):
        asyncio.run(bot._sweep_stale_commands())
    bot.http.bulk_upsert_global_commands.assert_not_awaited()
    assert bot.http.bulk_upsert_guild_commands.await_args_list == [
        ((7, 42, []),),
        ((7, 43, []),),
    ], "each guild she is in gets an empty list"


def test_a_guild_that_refuses_does_not_stop_the_sweep(caplog):
    bot, _ = make_bot(guild_id=None)
    bot.http.bulk_upsert_guild_commands = AsyncMock(
        side_effect=[discord.Forbidden(Mock(status=403), "no"), None]
    )
    with in_guilds(bot, 42, 43), patch.object(type(bot), "application_id", 7):
        asyncio.run(bot._sweep_stale_commands())
    assert bot.http.bulk_upsert_guild_commands.await_count == 2, "43 still swept"
    assert "cannot touch commands in guild 42" in caplog.text
