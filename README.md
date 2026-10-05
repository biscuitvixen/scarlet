# scarlet

A friendly, growing utility bot for Discord. Right now she handles cross-timezone timestamps and voice-channel music, with more tools on the way. Runs anywhere Docker does, no GPU needed.

Features:

- **Timestamp coordination**: turns a time someone wrote ("friday at 7pm") into Discord timestamp markup (`<t:unix:F>` and `<t:unix:R>`), so everyone sees it in their own zone. She only does it when asked, never on her own: @mention her in the message, put a `!` in front of the time (`!8pm`), right-click any message and pick Apps > Convert times, or just say "Scarlet?" and she converts the latest time-ish message. See [Asking for a timestamp](#asking-for-a-timestamp). Parsing is deterministic. Users register a timezone with `/tz` (autocompleted), or say the zone in the message itself ("22:00 CET"), which works whether or not the author has registered one. `/time <phrase>` converts a phrase of your own, and `/timecode <phrase>` hands back the raw markup privately, in a code block, for pasting into your own message; an optional style picks one of Discord's seven formats.
- **Self-assignable roles**: buttons on a message that hand out roles when clicked, so members pick their own pronouns, game pings or colours without anyone with Manage Roles being awake. Panels are built with `/roles` and come in three flavours: pick as many as you like, pick exactly one, or click-to-opt-in with no take-backs. See [Reaction roles](#reaction-roles).
- **Music**: plays audio in voice channels via Lavalink. `/play` takes a link or a search term; `/skip`, `/stop`, `/pause`, `/volume`, `/shuffle`, `/loop`, `/queue` and `/nowplaying` round it out. She manages a queue and leaves on her own once the channel empties or nothing has played for a while.

Plus `/ping` to check she's alive and `/help` to list everything. More tools are on the way, so treat the list above as what she does today rather than the ceiling.

## Architecture

Two CPU-only containers, defined in `docker-compose.yml`, cover everything:

| Service  | What it does |
|----------|--------------|
| bot      | The discord.py bot itself. CPU only. |
| lavalink | Audio server the bot controls via wavelink for music playback. CPU only. |

## Setup

1. Create an application at https://discord.com/developers/applications, add a bot, enable the **message content** intent, and grab the token.
2. Invite it to your server with the `bot` and `applications.commands` scopes.
3. Configure and start:

```sh
cp .env.example .env   # fill in DISCORD_TOKEN, and GUILD_ID for instant command sync
docker compose up -d --build
```

That is the whole bot up and running.

## Asking for a timestamp

She never converts a time unprompted. An earlier version replied to
every clock time in chat, and the people living with it asked for that
to stop: most times in conversation are not plans, and a bot that
answers "we were up until 3am" with a countdown is noise. So every
conversion starts with someone asking, in whichever of these ways is
closest to hand:

| Ask | What happens |
|-----|--------------|
| `@Scarlet raid at 8pm?` | Converts the times in that message. |
| `raid at !8pm?` | A `!` directly before a time marks it. Only marked times convert, so "up until 3am, !8pm tonight" gives just the 8pm. |
| Apps > Convert times | Right-click (long-press on mobile) any message, however old. The conversion is a public reply on it; anything that goes wrong is said privately to whoever asked. |
| `Scarlet?` | After a message she did not convert: she looks back over the last few messages, takes the newest one with a time in it that she has not already answered, and converts that. |
| `/time 8pm friday` | Converts a phrase of your own, not a message. |

Times are read in the author's timezone, the one they set with `/tz`,
unless the message states its own ("22:00 CET"). If the author has no
zone on file she asks them to set one, except from the context menu,
where she tells the person who asked instead so nobody is pinged on
someone else's behalf.

The nudge and the context menu need the Read Message History
permission in the channel. Without it she says so rather than
staying silent.

## Reaction roles

Despite the name everyone uses for them, these are buttons rather than
reactions. Reactions were the only interactive surface bots had before
2021; buttons give real labels, a private reply to whoever clicked, and
no need for the message-reaction intent.

Scarlet never records who holds which role. Discord already knows, and
is the only authority on it, so nothing here can drift out of step with
the role list and nobody loses a role if the database is thrown away.

Clicks are confirmed privately, and a run of them rewrites one message
rather than stacking up a column of them, so the confirmation reads as a
live list of what you hold on that panel. Note that the role change
itself is not private: roles show on profiles as normal, and Discord
writes every change to the server audit log.

### Setting up the server

These are the once-off Discord-side jobs, and between them they account
for essentially every way a role panel fails.

1. **Put Scarlet's role above the roles she hands out.** Server
   Settings > Roles, drag her up. A bot can only manage roles strictly
   below its own highest role. This is the big one.
2. **Give her Manage Roles**, server-wide. It is not a per-channel
   permission.
3. **Check your 2FA setting.** If Server Settings > Safety Setup requires
   2FA for moderator actions, the account that owns the bot application
   needs 2FA switched on or every role change fails.
4. **Make a `#roles` channel.** Deny `@everyone` Send Messages so it
   stays nothing but panels, and allow Scarlet View Channel, Send
   Messages and Embed Links. She does not need Manage Messages.
5. **Create the roles.** If a role only exists to unlock a channel, give
   it no permissions at all and set the visibility on the channel
   instead: deny `@everyone` View Channel there, allow the role. The
   role then carries no power of its own.

Roles Discord will never let anyone assign by hand are refused up front
rather than at click time: `@everyone`, and any role managed by an
integration such as another bot or Nitro boosting.

### Building a panel

```
/roles create name:pronouns channel:#roles mode:multi title:"Pronouns"
/roles add    panel:pronouns role:@they/them label:"they/them" emoji:🦊
/roles add    panel:pronouns role:@she/her   label:"she/her"
```

Every edit rewrites the message straight away, so the panel takes shape
as you build it. Panels are addressed by the short name you gave them,
which autocompletes.

| Mode | Behaviour | Good for |
|------|-----------|----------|
| `multi` | Each button toggles its own role | Pronouns, game pings, notification opt-ins |
| `single` | Taking one role drops the others on that panel | Colours, region, age bracket |
| `sticky` | Click to gain the role, never to lose it | Rules agreement, verification |

Panels take a colour, either a name like `blurple` from the suggestions
or a hex code like `#ff8800`, on `/roles create` or afterwards with
`/roles colour`. The private confirmation you get on clicking a button
wears the same colour, so a reply is recognisably from the panel it came
from. Left unset, panels are blurple.

The rest of the group: `/roles remove` takes a role off a panel,
`/roles order` moves a button, `/roles list` shows what exists,
`/roles repost` puts a panel back if its message got deleted, and
`/roles delete` removes the panel entirely. None of them take roles away
from anyone who already has one. The whole group is hidden from members
without Manage Roles, because Discord gates it.

One message holds at most 25 buttons, five to a row. Past that, make a
second panel.

### Moving over from Dyno

Nothing is lost in the switch, because neither bot ever owned the role
membership. Build the new panels in a staff-only channel and click
through them, post them in `#roles` alongside Dyno's, and once people
have moved across, delete Dyno's messages and take away its Manage
Roles permission.

Dyno's existing panels cannot be adopted in place. Only the bot that
posted a message can put buttons on it, so the panels get rebuilt.

## Music

Playback runs through the `lavalink` container using the [youtube-source](https://github.com/lavalink-devs/youtube-source) plugin (Lavalink 4 dropped its built-in YouTube support). Two things need doing once on a fresh machine:

- **Plugin volume ownership.** Lavalink runs as uid 322, but Docker creates the `lavalink-plugins` volume as root, so the first plugin download fails with a permission error until you fix it:

  ```sh
  docker run --rm -v scarlet_lavalink-plugins:/p alpine chown -R 322:322 /p
  ```

- **Volumes from before the rename.** The compose project is pinned to
  `scarlet`, so her volumes are `scarlet_bot-data` and
  `scarlet_lavalink-plugins`. A deployment made when the repo was
  `scarlett_ai` has them under that prefix, and a plain `docker compose
  up` on the new checkout starts her on fresh, empty ones. Copy the old
  data across once, with the stack stopped:

  ```sh
  docker volume create scarlet_bot-data
  docker run --rm -v scarlett_ai_bot-data:/from -v scarlet_bot-data:/to alpine cp -a /from/. /to/
  ```

  The same two lines with `lavalink-plugins` in place of `bot-data`
  save re-downloading the plugins.

- **YouTube OAuth**, which is the reliable cure for "sign in to confirm you're not a bot" errors. Start Lavalink with `YOUTUBE_OAUTH_REFRESH_TOKEN` blank in `.env` and watch its logs (`docker compose logs -f lavalink`): it prints a device-link URL and code. Authorise with a **burner** Google account (never your main one), then copy the refresh token it logs into `YOUTUBE_OAUTH_REFRESH_TOKEN` in `.env` and restart. The token is injected into `lavalink/application.yml` via the compose file, so it never lives in a tracked file.

### Sources

Beyond YouTube, the sources enabled in `lavalink/application.yml` are **SoundCloud**, **Bandcamp**, **Twitch**, **Vimeo**, and **HTTP** (direct audio URLs and stream/radio links). Paste a link from any of them into `/play`; plain-text searches go to YouTube. Lavalink also ships **Niconico** and **local files**, both left off. To turn one on, flip it to `true` under `lavalink.server.sources` and restart the `lavalink` container.

More services (Spotify, Apple Music, Deezer, Tidal, Yandex, ...) can be added with the [LavaSrc](https://github.com/topi314/LavaSrc) plugin, wired in the same way as the youtube-source plugin. Note that Spotify, Apple Music and Tidal are metadata-only "mirror" sources: LavaSrc reads the track details from the link but streams the actual audio from YouTube.

## Slash command sync

Discord keeps slash commands in two separate registries: **global** (shows in every
guild the bot is in, but changes can take up to an hour to appear) and **per-guild**
(one guild, updates instantly). The bot chooses based on `GUILD_ID` in `.env`:

- `GUILD_ID` blank: syncs globally.
- `GUILD_ID=<id>`: syncs to that one guild, handy for instant iteration while developing. Development only: with it set she empties her global commands on login, so every other server she is in loses them. Leave it blank in production.

A sync only ever replaces the scope it is aimed at, so without further
care a guild synced under `GUILD_ID` during development would keep
those copies after `GUILD_ID` is blanked, and show every command twice
beside the global set. She prevents that on login: whichever scope the
current `.env` does not use is sent an empty list, the global scope
when `GUILD_ID` is set, and the guild scope of every server she is in
when it is blank. The registered commands after any restart therefore
follow the current setting alone, and a guild showing duplicates is
cleaned by the next restart.

## Running her locally

Docker is the deployment story, but rebuilding an image to try a code
change is a slow way to work. For development, run the bot straight out
of a venv:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

set -a && . ./.env && set +a           # config comes from the environment
export DB_PATH=./data/scarlet.db      # the default path lives inside the image
export MUSIC_ENABLED=false
.venv/bin/python -m scarlet
```

The `set -a` line is the part that catches people out. Under Docker,
compose reads `.env` and injects it; run directly, nothing does, and the
bot only ever reads the environment.

Use a second bot application for this, with its own token and `GUILD_ID`
pointing at a test server, so a half-finished change is never loose in a
real one.

`MUSIC_ENABLED=false` is the line that makes the logs readable. Lavalink
is not running outside compose, and wavelink retries an unreachable node
forever, so leaving it on buries everything you are actually trying to
read under reconnect warnings. Off, the music cog is never loaded and
the node is never created. Roles, timestamps and `/help` need nothing.

Tests need nothing running at all:

```sh
.venv/bin/python -m pytest
```

### What build am I running

She says so on her profile: the About Me is the tagline from
`BOT_ABOUT` with "Running `<commit>`" underneath, rewritten once at
login when it has changed. Edit the tagline in `.env`, not on Discord,
or the next login puts it back. `/version` answers with the commit and
its date, privately, for people with Manage Server, and that is the
line she writes to the startup log.

There is no release number on show. The one in `pyproject.toml` is a
compatibility claim that a bot changing every week never earns a bump
for, so the build is named by its commit and the commit's date, which
need no decision from anyone. Both are baked into the image at build
time from `GIT_SHA` and `GIT_DATE`, which CI fills in from the commit
being built. The published images also carry the commit in their OCI
labels, so `docker inspect` answers the same question without Discord:

```sh
docker inspect --format \
  '{{index .Config.Labels "org.opencontainers.image.revision"}}' \
  ghcr.io/<owner>/scarlet:latest
```

Running from a checkout nothing sets them, and she falls back to the
package version so the line is never blank. Pass them yourself if you
want the commit named:

```sh
export GIT_SHA=$(git rev-parse HEAD) GIT_DATE=$(git log -1 --format=%cs)
```

## CI

Pushes to `main` (and `v*` tags) build a multi-arch image and publish it to GHCR as `ghcr.io/<owner>/<repo>`. Pull requests build without publishing.
