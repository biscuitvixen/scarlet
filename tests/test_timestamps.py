import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from scarlet.cogs.timestamps import (
    ASKED_MIN_LEAD,
    DEFAULT_STYLES,
    TIMESTAMP_STYLES,
    Timestamps,
    _render,
    _render_codes,
    is_nudge,
)
from scarlet.timeparse import TimeMatch

LONDON = ZoneInfo("Europe/London")
WHEN = datetime(2026, 7, 1, 19, 0, tzinfo=LONDON)
UNIX = int(WHEN.timestamp())


BOT_ID = 999


def make_cog(tz_name=None):
    bot = Mock()
    bot.user = Mock()
    bot.user.id = BOT_ID
    bot.db = Mock()
    bot.db.get_timezone = AsyncMock(return_value=tz_name)
    return Timestamps(bot)


def make_message(content, author_id=1, is_bot=False, message_id=0, mentions=()):
    message = Mock()
    message.id = message_id
    message.content = content
    message.author.id = author_id
    message.author.bot = is_bot
    message.mentions = list(mentions)
    message.reference = None
    message.reply = AsyncMock()
    return message


def make_channel(history):
    """A channel whose history() yields the given messages, newest first."""

    async def _history(**kwargs):
        for message in history:
            yield message

    channel = Mock()
    channel.id = 42
    channel.history = _history
    return channel


def bot_reply_to(message_id):
    reply = make_message("converted", author_id=BOT_ID, is_bot=True)
    reply.reference = Mock()
    reply.reference.message_id = message_id
    return reply


def run(coro):
    return asyncio.run(coro)


def reply_text(message):
    return message.reply.call_args.args[0]


def test_prompt_quotes_the_matched_phrase():
    # the message that started all this: a bare "noon" with no tz on file
    cog = make_cog(tz_name=None)
    msg = make_message("I had shawarma for breakfast at noon, walked back")
    run(cog.on_message(msg))
    msg.reply.assert_called_once()
    text = reply_text(msg)
    assert '"noon"' in text
    assert "/tz" in text


def test_prompt_preserves_original_casing():
    cog = make_cog(tz_name=None)
    msg = make_message("lunch at NOON tomorrow")
    run(cog.on_message(msg))
    assert '"NOON"' in reply_text(msg)


def test_prompt_quotes_a_clock_time():
    cog = make_cog(tz_name=None)
    msg = make_message("dinner at 7:30 pm sound good?")
    run(cog.on_message(msg))
    assert '"7:30 pm"' in reply_text(msg)


def test_prompt_is_rate_limited_per_user():
    cog = make_cog(tz_name=None)
    first = make_message("noon", author_id=5)
    second = make_message("midnight", author_id=5)
    run(cog.on_message(first))
    run(cog.on_message(second))
    first.reply.assert_called_once()
    # inside PROMPT_COOLDOWN, the second mention stays quiet
    second.reply.assert_not_called()


def test_bot_messages_are_ignored():
    cog = make_cog(tz_name=None)
    msg = make_message("meet at 7pm", is_bot=True)
    run(cog.on_message(msg))
    msg.reply.assert_not_called()
    cog.bot.db.get_timezone.assert_not_called()


def test_message_without_a_time_is_ignored():
    cog = make_cog(tz_name=None)
    msg = make_message("see you friday")
    run(cog.on_message(msg))
    msg.reply.assert_not_called()
    cog.bot.db.get_timezone.assert_not_called()


def test_preformatted_timestamp_is_ignored():
    cog = make_cog(tz_name=None)
    msg = make_message("meet at <t:1751652000:F> please")
    run(cog.on_message(msg))
    msg.reply.assert_not_called()


def test_known_timezone_replies_with_conversion():
    cog = make_cog(tz_name="Europe/London")
    msg = make_message("dinner at 7pm tomorrow")
    run(cog.on_message(msg))
    msg.reply.assert_called_once()
    text = reply_text(msg)
    assert "<t:" in text
    # the reply quotes the matched phrase, which dateparser returns with its
    # surrounding words ("at 7pm tomorrow"), not just the clock time
    assert '"' in text and "7pm" in text


def test_gate_hit_with_nothing_to_convert_stays_quiet():
    # "in 5 minutes" trips the regex gate but is under the minimum lead, so
    # extract_times finds nothing and a tz-known user gets no noisy reply
    cog = make_cog(tz_name="Europe/London")
    msg = make_message("leaving in 5 minutes")
    run(cog.on_message(msg))
    msg.reply.assert_not_called()


def test_stated_zone_skips_the_database_entirely():
    # "22:00 CET" needs nobody's registered zone, so it must not nag
    cog = make_cog(tz_name=None)
    msg = make_message("22:00 CET tomorrow works for me")
    run(cog.on_message(msg))
    msg.reply.assert_called_once()
    assert "<t:" in reply_text(msg)
    cog.bot.db.get_timezone.assert_not_called()


def test_prompt_still_fires_when_no_zone_is_stated():
    cog = make_cog(tz_name=None)
    msg = make_message("22:00 tomorrow works for me")
    run(cog.on_message(msg))
    assert "/tz" in reply_text(msg)


def test_render_plain_match():
    line = _render([TimeMatch("21:00", WHEN)])
    assert line == f'"21:00" is <t:{UNIX}:F> (<t:{UNIX}:R>)'


def test_render_names_a_borrowed_zone():
    line = _render([TimeMatch("21:00", WHEN, "CET")])
    assert line == f'"21:00" in CET is <t:{UNIX}:F> (<t:{UNIX}:R>)'


def test_render_one_line_per_match():
    lines = _render([TimeMatch("20:00", WHEN), TimeMatch("21:00", WHEN)])
    assert len(lines.splitlines()) == 2


def test_asked_min_lead_is_off():
    # /time was asked directly, nothing it finds is too soon to convert
    assert ASKED_MIN_LEAD.total_seconds() == 0


def test_codes_default_to_the_listener_pair():
    text = _render_codes([TimeMatch("7pm", WHEN)], DEFAULT_STYLES)
    assert text.startswith(f"```\n<t:{UNIX}:F> <t:{UNIX}:R>\n```\n"), (
        f"code block should carry F and R for the match, got: {text!r}"
    )
    assert f'"7pm" shows as <t:{UNIX}:F> <t:{UNIX}:R>' in text, (
        f"preview line missing or wrong, got: {text!r}"
    )


def test_codes_honour_a_single_chosen_style():
    text = _render_codes([TimeMatch("7pm", WHEN)], ("t",))
    assert f"```\n<t:{UNIX}:t>\n```" in text, f"only style t should appear: {text!r}"
    assert ":F>" not in text and ":R>" not in text, (
        f"default styles leaked into a single-style request: {text!r}"
    )


def test_codes_one_block_line_per_match():
    later = TimeMatch("9pm", WHEN.replace(hour=21))
    text = _render_codes([TimeMatch("7pm", WHEN), later], ("F",))
    block = text.split("```")[1].strip().splitlines()
    assert len(block) == 2, f"expected one code line per match, got {block!r}"


def test_codes_say_when_a_zone_was_borrowed():
    text = _render_codes([TimeMatch("7pm", WHEN, zone="CET")], ("F",))
    assert '"7pm" in CET shows as' in text, (
        f"borrowed zone should be named in the preview: {text!r}"
    )


def test_every_discord_style_is_offered():
    assert set(TIMESTAMP_STYLES) == set("tTdDfFR"), (
        "style picker drifted from Discord's seven timestamp styles"
    )


@pytest.mark.parametrize(
    "content, mentioned",
    [
        ("Scarlet?", False),
        ("scarlett", False),
        ("hey scarlet convert that", False),
        ("scarlet pls", False),
        ("oi scarlett!!", False),
        ("Scarlet, again?", False),
        ("<@999>", True),
        ("<@999> ?", True),
    ],
)
def test_a_bare_call_of_her_name_is_a_nudge(content, mentioned):
    assert is_nudge(content, mentioned), f"{content!r} should read as a nudge"


@pytest.mark.parametrize(
    "content, mentioned",
    [
        ("scarlet 8pm?", False),
        ("scarlet is great", False),
        ("<@999> what time", True),
        ("the scarlet witch", False),
        ("8pm?", False),
    ],
)
def test_her_name_inside_a_sentence_is_not_a_nudge(content, mentioned):
    assert not is_nudge(content, mentioned), f"{content!r} should not be a nudge"


def nudge_in(history, tz_name="Europe/London"):
    cog = make_cog(tz_name=tz_name)
    nudge = make_message("Scarlet?", author_id=2, message_id=100)
    nudge.channel = make_channel(history)
    run(cog.on_message(nudge))
    return nudge


def test_a_nudge_converts_the_latest_message_with_a_time_in_it():
    past = make_message("we were up until 3am", message_id=10)
    chatter = make_message("lmao same", author_id=3, message_id=11)
    nudge = nudge_in([chatter, past])
    past.reply.assert_called_once()
    assert "<t:" in reply_text(past), "the conversion should sit on the message"
    nudge.reply.assert_not_called()
    chatter.reply.assert_not_called()


def test_a_nudge_skips_a_message_she_already_answered():
    older = make_message("raid at 8pm", message_id=10)
    answered = make_message("dinner at 7pm", message_id=11)
    nudge_in([bot_reply_to(11), answered, older])
    answered.reply.assert_not_called()
    older.reply.assert_called_once()
    assert "<t:" in reply_text(older), "the unanswered one should convert"


def test_a_nudge_with_nothing_to_point_at_says_so():
    chatter = make_message("lmao same", message_id=11)
    nudge = nudge_in([chatter])
    nudge.reply.assert_called_once()
    assert "/time" in reply_text(nudge), "should point at /time as the fallback"
    chatter.reply.assert_not_called()


def test_a_nudge_prompts_the_author_for_a_zone_even_inside_the_cooldown():
    cog = make_cog(tz_name=None)
    first = make_message("i was up until 7am", message_id=10)
    run(cog.on_message(first))
    first.reply.assert_not_called()  # past tense, the listener stays quiet
    cog.last_prompted[first.author.id] = 1e12  # as if nagged a moment ago
    nudge = make_message("scarlet?", author_id=2, message_id=100)
    nudge.channel = make_channel([first])
    run(cog.on_message(nudge))
    first.reply.assert_called_once()
    assert "/tz" in reply_text(first), "a nudge should re-ask for the zone"
