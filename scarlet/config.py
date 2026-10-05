from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All runtime configuration, read from environment variables.

    Field names map to env vars case-insensitively, so discord_token
    is filled from DISCORD_TOKEN and so on.
    """

    discord_token: str
    guild_id: int | None = None

    # a blank line in .env ("GUILD_ID=") should mean unset, not crash
    @field_validator("guild_id", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return None if v == "" else v

    # INFO says what she did with each message; DEBUG adds the step by step
    # of the time parsing, which is where a quiet failure usually hides.
    # Set LOG_LEVEL=DEBUG in .env and restart, no rebuild needed
    log_level: str = "INFO"

    # on by default, since compose always brings lavalink up alongside her.
    # turn it off to drop the music cog and skip the node entirely, which is
    # what you want running her outside compose: wavelink retries an
    # unreachable node forever and buries every other log line doing it
    music_enabled: bool = True
    lavalink_url: str = "http://lavalink:2333"
    lavalink_password: str = "youshallnotpass"
    # seconds she lingers in a voice channel with nothing playing before
    # disconnecting on her own
    music_idle_timeout: int = 300

    db_path: str = "/app/data/scarlet.db"

    # the commit the image was built from and its date, baked in by the
    # Dockerfile. empty running from a checkout, where you already know what
    # you are running
    git_sha: str = ""
    git_date: str = ""

    # the first line of her profile. the build goes underneath it at login,
    # so the whole About Me is owned here and never only on Discord
    bot_about: str = "I may not be real - but I am still fluffy!"
