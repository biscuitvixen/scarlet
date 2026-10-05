import asyncio
from unittest.mock import AsyncMock, Mock

from scarlet.bot import Scarlet
from scarlet.config import Settings


def make_bot(about="I may not be real - but I am still fluffy!"):
    settings = Settings(
        discord_token="x", bot_about=about, git_sha="8fa4a66abc", git_date="2026-10-05"
    )
    bot = Scarlet(settings)
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
    import discord

    bot, info = make_bot()
    info.description = "something else"
    info.edit = AsyncMock(side_effect=discord.HTTPException(Mock(status=500), "no"))
    asyncio.run(bot._update_about())  # must not raise
    assert "could not update the About Me" in caplog.text
