import asyncio
import logging

import discord
import wavelink
from discord.ext import commands

from .config import Settings
from .db import Database
from .version import about_text, describe, package_version

log = logging.getLogger(__name__)

# always loaded. music needs a backing service, so it is added only when
# switched on
COGS = [
    "scarlet.cogs.general",
    "scarlet.cogs.timestamps",
    "scarlet.cogs.roles",
    "scarlet.cogs.health",
]


class Scarlet(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        # she has no prefix commands, only slash commands and listeners, so
        # the prefix is mention-only: anything else would turn "!8pm", the
        # inline convert marker, into a command lookup that fails
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.db: Database | None = None
        self.lavalink_task: asyncio.Task | None = None
        # on_ready fires again on every gateway resume, the sweep is once
        self.scopes_swept = False
        self.version = describe(package_version(), settings.git_sha, settings.git_date)
        # the profile names the commit only; the date is for whoever asks
        self.build = describe(package_version(), settings.git_sha)

    async def setup_hook(self) -> None:
        self.db = await Database.open(self.settings.db_path)
        cogs = list(COGS)
        if self.settings.music_enabled:
            cogs.append("scarlet.cogs.music")
        for cog in cogs:
            await self.load_extension(cog)
            log.info("loaded %s", cog)

        # Connect to lavalink for music, in the background: wavelink retries
        # an unreachable node forever, and awaiting that here would hold up
        # setup_hook, leaving the bot logged in but never ready and with no
        # commands synced. Off to one side, an unreachable node just disables
        # playback. wavelink.Pool is global, the music cog reaches it without
        # any extra wiring.
        if self.settings.music_enabled:
            self.lavalink_task = asyncio.create_task(self._connect_lavalink())

        # Guild-scoped sync shows new slash commands immediately.
        # Global sync can take up to an hour, so use GUILD_ID during dev.
        try:
            if self.settings.guild_id:
                guild = discord.Object(id=self.settings.guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            else:
                await self.tree.sync()
        except discord.Forbidden:
            # Usually means the bot was invited without the
            # applications.commands scope, keep running so chat features
            # still work and print the fix
            log.error(
                "cannot register slash commands in guild %s, reinvite with: "
                "https://discord.com/oauth2/authorize?client_id=%s"
                "&scope=bot+applications.commands&permissions=277330890816",
                self.settings.guild_id,
                self.application_id,
            )

    async def _connect_lavalink(self) -> None:
        try:
            node = wavelink.Node(
                uri=self.settings.lavalink_url,
                password=self.settings.lavalink_password,
            )
            await wavelink.Pool.connect(client=self, nodes=[node])
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("could not connect to lavalink, music will be unavailable")

    async def on_ready(self) -> None:
        log.info(
            "logged in as %s (%s), running %s", self.user, self.user.id, self.version
        )
        await self._update_about()
        if not self.scopes_swept:
            self.scopes_swept = True
            await self._sweep_stale_commands()

    async def _sweep_stale_commands(self) -> None:
        """Empty the command scope the current settings do not use.

        Discord keeps global and per-guild command registries apart, and a
        sync only ever replaces the one it is aimed at. A guild that was
        synced under GUILD_ID keeps those copies after GUILD_ID is blanked
        and the global set is synced, and shows every command twice. The
        sweep sends an empty list to the other scope, so the registered
        state after any login follows the current settings alone.

        The raw endpoints are used rather than clearing the local tree,
        which is what she dispatches from. Needs the guild list, so it
        runs from on_ready rather than setup_hook.
        """
        app_id = self.application_id
        if self.settings.guild_id:
            await self.http.bulk_upsert_global_commands(app_id, [])
            log.info("GUILD_ID is set, cleared the global command scope")
            return
        for guild in self.guilds:
            try:
                await self.http.bulk_upsert_guild_commands(app_id, guild.id, [])
            except discord.Forbidden:
                # invited without applications.commands there; nothing of
                # hers can be registered in that guild either way
                log.warning("cannot touch commands in guild %s", guild.id)
        log.info("cleared guild command scopes in %d guilds", len(self.guilds))

    async def _update_about(self) -> None:
        """Put the running build under the tagline on her profile.

        One edit per login, and only when the text has changed, so a
        restart loop does not hammer the application endpoint.
        """
        wanted = about_text(self.settings.bot_about, self.build)
        try:
            info = await self.application_info()
            if info.description == wanted:
                return
            await info.edit(description=wanted)
        except discord.HTTPException as exc:
            # the profile is cosmetic, a failed edit must not take her down
            log.warning("could not update the About Me (%s), carrying on", exc)
            return
        log.info("profile now says: running %s", self.build)

    async def close(self) -> None:
        if self.lavalink_task is not None:
            self.lavalink_task.cancel()
        if self.db is not None:
            await self.db.close()
        await super().close()
