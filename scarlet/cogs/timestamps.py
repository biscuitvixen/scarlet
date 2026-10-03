"""Turns time phrases in chat into Discord timestamp markup.

<t:unix:F> renders as an absolute time in each viewer's own timezone and
<t:unix:R> as a relative one, so "friday at 7pm" becomes unambiguous for
the whole server. Parsing lives in scarlet.timeparse; this cog handles
the Discord side and the per-user timezone registry.
"""

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import app_commands
from discord.ext import commands

from ..timeparse import (
    TIME_OF_DAY,
    TimeMatch,
    explicit_zone,
    extract_times,
)

log = logging.getLogger(__name__)

# how far back a nudge looks for the message it is about. Long enough to
# reach past a couple of replies to the one she ignored, short enough that
# she never digs up something from an hour ago
HISTORY_LINES = 8

# a message that is her name and nothing much else: "Scarlet?", "hey
# scarlett convert that", "scarlet pls". A mention of her with no other
# words counts too, that check is on the message, not the text
NUDGE = re.compile(
    r"""
    ^\W*(?:(?:hey|hi|oi|yo|ok|okay|uh|um|erm)\W+)?
    scarlett?
    (?:\W+(?:convert|time|times|please|pls|plz|that|this|it|one|again))*
    \W*$
    """,
    re.IGNORECASE | re.VERBOSE,
)
# a user or role mention token, stripped before the text is read
MENTION = re.compile(r"<@[!&]?\d+>")

# /time was asked a direct question, so the quiet-hour rule that keeps her
# from butting in over an imminent time does not apply
ASKED_MIN_LEAD = timedelta(0)

# the reply still has to fit in a Discord message and stay readable, so the
# cap is raised rather than lifted
ASKED_MAX_MATCHES = 10


def is_nudge(content: str, mentioned: bool) -> bool:
    """Whether a message is someone calling her name and no more.

    mentioned says her user was @mentioned; the token itself is stripped
    before the text is read, so "@Scarlet ?" and "scarlet?" read the same.
    """
    text = MENTION.sub(" ", content).strip()
    if mentioned and not re.search(r"\w", text):
        return True
    return bool(NUDGE.match(text))


def _render(matches: list[TimeMatch]) -> str:
    lines = []
    for m in matches:
        unix = int(m.when.timestamp())
        # m.zone is set when a bare time borrowed a zone stated elsewhere in
        # the message, which is a guess worth saying out loud
        said = f" in {m.zone}" if m.zone else ""
        lines.append(f'"{m.phrase}"{said} is <t:{unix}:F> (<t:{unix}:R>)')
    return "\n".join(lines)


# Discord's timestamp styles, https://discord.com/developers/docs/reference
# #message-formatting-timestamp-styles. The letter is what goes in the
# markup, the label is how the picker describes it
TIMESTAMP_STYLES = {
    "t": "short time, 16:20",
    "T": "long time, 16:20:30",
    "d": "short date, 20/04/2021",
    "D": "long date, 20 April 2021",
    "f": "short date and time, 20 April 2021 16:20",
    "F": "long date and time, Tuesday, 20 April 2021 16:20",
    "R": "relative, 2 months ago",
}

# what /timecode hands over when no style is asked for: the same pair the
# listener posts, an absolute time and a countdown to it
DEFAULT_STYLES = ("F", "R")


def _render_codes(matches: list[TimeMatch], styles: tuple[str, ...]) -> str:
    """The raw markup in a code block, then what each line renders as.

    Inside a fenced block Discord shows <t:...> literally and, on desktop,
    offers a copy button for the whole block, which is the point. The
    preview outside it renders normally so the code can be checked before
    it is pasted anywhere.
    """
    codes = []
    previews = []
    for m in matches:
        unix = int(m.when.timestamp())
        markup = " ".join(f"<t:{unix}:{s}>" for s in styles)
        codes.append(markup)
        said = f" in {m.zone}" if m.zone else ""
        previews.append(f'"{m.phrase}"{said} shows as {markup}')
    return "```\n" + "\n".join(codes) + "\n```\n" + "\n".join(previews)


class Timestamps(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.zones = sorted(available_timezones())
        self.zone_set = set(self.zones)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.content:
            return
        if is_nudge(message.content, self.bot.user in message.mentions):
            await self._nudged(message)
            return

    async def _nudged(self, nudge: discord.Message) -> None:
        """Convert the latest time-ish message she has not answered.

        Someone saying her name is the strongest signal there is that a
        conversion is wanted, so nothing that keeps her quiet on the
        listener path applies: not the past-tense filter, not the lead
        time, not the prompt cooldown.
        """
        log.info("nudged by %s in %s", nudge.author.id, nudge.channel.id)
        answered: set[int] = set()
        candidates: list[discord.Message] = []
        try:
            async for earlier in nudge.channel.history(
                limit=HISTORY_LINES, before=nudge
            ):
                if earlier.author.id == self.bot.user.id:
                    if earlier.reference and earlier.reference.message_id:
                        answered.add(earlier.reference.message_id)
                elif not earlier.author.bot and earlier.content:
                    candidates.append(earlier)
        except discord.Forbidden:
            log.warning(
                "cannot read history in %s, the nudge needs Read Message History",
                nudge.channel.id,
            )
            await nudge.reply(
                "I can't read back through this channel, so I don't know what "
                "you mean. I need the Read Message History permission here.",
                mention_author=False,
            )
            return

        # history arrives newest first, so the first hit is the latest one
        for message in candidates:
            if message.id in answered or "<t:" in message.content:
                continue
            if TIME_OF_DAY.search(message.content):
                break
        else:
            log.info("nothing time-ish in the last %d messages", HISTORY_LINES)
            await nudge.reply(
                "I don't see a time in the last few messages. Try /time with "
                "the bit you want converted.",
                mention_author=False,
            )
            return

        log.info("nudge points at %r from %s", message.content, message.author.id)
        stated = explicit_zone(message.content)
        if stated is None:
            tz_name = await self.bot.db.get_timezone(message.author.id)
            if tz_name is None:
                await self._prompt_for_timezone(
                    message, TIME_OF_DAY.search(message.content).group(0)
                )
                return
            zone = ZoneInfo(tz_name)
        else:
            zone = stated.tz

        matches = extract_times(message.content, zone, min_lead=ASKED_MIN_LEAD)
        if not matches:
            log.info("nudged, but could not place %r", message.content)
            await nudge.reply(
                "I see a time in there but I can't place it, sorry. "
                "Try /time with just that bit.",
                mention_author=False,
            )
            return
        log.info("converting %s on a nudge", [m.phrase for m in matches])
        await message.reply(
            _render(matches),
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _prompt_for_timezone(self, message: discord.Message, phrase: str) -> None:
        log.info("%s has no timezone set, asking them to /tz", message.author.id)
        # reply() pings the author by default, which is wanted here
        await message.reply(
            f'"{phrase}" looks like a time! I don\'t know your timezone yet '
            "though. Set it with /tz and I'll sort the conversions for everyone."
        )

    # named around the time module this cog already imports, the slash
    # command is still /time
    @app_commands.command(
        name="time", description="Convert a time for everyone, right now"
    )
    @app_commands.describe(when="A time, e.g. 21:00, 8pm friday, or 22:00 CET")
    async def convert_time(self, interaction: discord.Interaction, when: str) -> None:
        log.info("/time from %s: %r", interaction.user.id, when)
        matches = await self._resolve_asked(interaction, when)
        if matches is None:
            return
        await interaction.response.send_message(
            _render(matches), allowed_mentions=discord.AllowedMentions.none()
        )

    @app_commands.command(
        name="timecode",
        description="Get the timestamp markup for a time, to paste yourself",
    )
    @app_commands.describe(
        when="A time, e.g. 21:00, 8pm friday, or 22:00 CET",
        style="Which style to render; default is the date and a countdown",
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name=f"{letter}: {label}", value=letter)
            for letter, label in TIMESTAMP_STYLES.items()
        ]
    )
    async def timecode(
        self,
        interaction: discord.Interaction,
        when: str,
        style: app_commands.Choice[str] | None = None,
    ) -> None:
        log.info("/timecode from %s: %r", interaction.user.id, when)
        matches = await self._resolve_asked(interaction, when)
        if matches is None:
            return
        styles = (style.value,) if style else DEFAULT_STYLES
        # only the asker sees it, the markup is theirs to paste
        await interaction.response.send_message(
            _render_codes(matches, styles),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _resolve_asked(
        self, interaction: discord.Interaction, when: str
    ) -> list[TimeMatch] | None:
        """Times in a phrase someone asked about directly.

        Both error paths reply on the interaction themselves and return
        None, so a caller that gets None has nothing more to say.
        """
        stated = explicit_zone(when)
        if stated is None:
            tz_name = await self.bot.db.get_timezone(interaction.user.id)
            if tz_name is None:
                log.info("no timezone on file for %s", interaction.user.id)
                await interaction.response.send_message(
                    "I don't know your timezone yet, so I can't place that. "
                    "Set it with /tz, or say the zone outright like "
                    "'22:00 CET' and I'll take it from there.",
                    ephemeral=True,
                )
                return None
            zone = ZoneInfo(tz_name)
        else:
            zone = stated.tz

        matches = extract_times(
            when,
            zone,
            min_lead=ASKED_MIN_LEAD,
            max_matches=ASKED_MAX_MATCHES,
        )
        if not matches:
            log.info("could not place %r for %s", when, interaction.user.id)
            # quietly, so a typo doesn't land in the channel
            await interaction.response.send_message(
                f"I couldn't find a time in '{when}'. Something like 21:00, "
                "8pm friday or 22:00 CET works.",
                ephemeral=True,
            )
            return None
        return matches

    @app_commands.command(
        description="Set your timezone so time phrases convert correctly"
    )
    @app_commands.describe(timezone="IANA timezone name, e.g. Europe/London")
    async def tz(self, interaction: discord.Interaction, timezone: str) -> None:
        if timezone not in self.zone_set:
            log.info(
                "%s tried to set %r, not an IANA zone",
                interaction.user.id,
                timezone,
            )
            await interaction.response.send_message(
                f"Hmm, '{timezone}' isn't an IANA timezone name. "
                "Try the autocomplete, something like Europe/London.",
                ephemeral=True,
            )
            return
        await self.bot.db.set_timezone(interaction.user.id, timezone)
        log.info("%s registered as %s", interaction.user.id, timezone)
        local = datetime.now(ZoneInfo(timezone)).strftime("%H:%M")
        await interaction.response.send_message(
            f"All set, your timezone's {timezone}. "
            f"That puts your local time around {local}, if that's off just pick again.",
            ephemeral=True,
        )

    @tz.autocomplete("timezone")
    async def tz_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        needle = current.lower()
        hits = [z for z in self.zones if needle in z.lower()]
        return [app_commands.Choice(name=z, value=z) for z in hits[:25]]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Timestamps(bot))
