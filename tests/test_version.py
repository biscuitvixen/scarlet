import pytest

from scarlet.version import about_text, describe, short_sha


@pytest.mark.parametrize(
    "sha, expected",
    [
        ("1f65e17abcdef", "1f65e17"),
        ("1f65e17", "1f65e17"),
        ("  1f65e17  ", "1f65e17"),
        ("", None),
        (None, None),
    ],
)
def test_a_commit_is_trimmed_to_something_readable(sha, expected):
    assert short_sha(sha) == expected, f"{sha!r} trimmed wrongly"


def test_the_commit_and_its_date_name_the_build():
    assert describe("0.3.0", "8fa4a66abc", "2026-10-05") == "8fa4a66 (2026-10-05)"


def test_the_commit_stands_alone_without_a_date():
    assert describe("0.3.0", "8fa4a66abc") == "8fa4a66", "no date, no brackets"
    assert describe("0.3.0", "8fa4a66abc", "  ") == "8fa4a66", "blank is absent"


def test_the_version_is_the_fallback_for_a_checkout():
    # running from a checkout, where nothing bakes the commit in
    assert describe("0.3.0", "") == "0.3.0", "an absent commit falls back"
    assert describe("0.3.0", None, "2026-10-05") == "0.3.0", "a date alone is noise"


def test_the_profile_text_keeps_the_tagline_above_the_build():
    text = about_text(
        "I may not be real - but I am still fluffy!  ", "8fa4a66 (2026-10-05)"
    )
    assert text == (
        "I may not be real - but I am still fluffy!\n\nRunning 8fa4a66 (2026-10-05)"
    )


def test_the_version_command_is_gated_to_managers():
    # which build is running is an operator's question, and the gate is the
    # kind of thing that breaks without anything failing
    import asyncio

    import discord
    from discord.ext import commands

    from scarlet.cogs.general import General

    async def main():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        await bot.add_cog(General(bot))
        return next(c for c in bot.tree.get_commands() if c.name == "version")

    command = asyncio.run(main())
    assert command.guild_only, "asking which build is running is a server question"
    assert command.default_permissions == discord.Permissions(manage_guild=True), (
        "/version should default to Manage Server only"
    )
