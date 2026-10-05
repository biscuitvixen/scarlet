"""What this build is: the commit behind it, and when that commit was made.

The number in the project metadata is a claim about compatibility that
nobody bumps on a bot that changes every week, so it is not what gets
shown. The commit is provenance: which exact source produced the
container currently running, which is the thing worth knowing when
something misbehaves and the tag says only "latest". Its date is there
because a sha says nothing to a person reading a profile.

Both reach the process as environment variables baked in at image build
time, because the build context carries no git metadata. Running from a
checkout they are usually absent, and the package version stands in so
the line is never blank.

The commit goes on her profile, under the About Me text, rewritten once
at login when it has changed. The date joins it only in /version and the
startup log, where someone is actually asking.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version

# the version is read from the installed package rather than repeated here,
# so the one in the project metadata stays the only copy
PACKAGE = "scarlet"

UNKNOWN = "unknown"

# a short commit is enough to find the source and short enough to read out
SHA_LENGTH = 7


def package_version() -> str:
    try:
        return installed_version(PACKAGE)
    except PackageNotFoundError:
        # running from a source tree that was never installed
        return UNKNOWN


def short_sha(sha: str | None) -> str | None:
    """Trim a commit to something readable, None when there isn't one."""
    trimmed = (sha or "").strip()
    return trimmed[:SHA_LENGTH] if trimmed else None


def describe(version: str, sha: str | None = None, date: str | None = None) -> str:
    """`8fa4a66 (2026-10-05)`, `8fa4a66` without a date, or the version.

    The version is the fallback for a checkout, where nothing bakes the
    commit in; it is at least a name for what is running.
    """
    trimmed = short_sha(sha)
    if trimmed is None:
        return version
    date = (date or "").strip()
    return f"{trimmed} ({date})" if date else trimmed


def about_text(about: str, build: str) -> str:
    """The profile text: the tagline, then what is running under it."""
    return f"{about.strip()}\n\nRunning {build}"
