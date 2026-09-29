import asyncio
import logging

from scarlet.db import LEGACY_DB_NAME, Database


def run(coro):
    return asyncio.run(coro)


async def _seed(path):
    db = await Database.open(str(path))
    await db.set_timezone(1, "Europe/London")
    await db.close()


def test_a_database_under_the_old_name_is_adopted(tmp_path, caplog):
    legacy = tmp_path / LEGACY_DB_NAME
    run(_seed(legacy))
    new = tmp_path / "scarlet.db"
    with caplog.at_level(logging.WARNING, logger="scarlet.db"):
        db = run(Database.open(str(new)))
    assert run(db.get_timezone(1)) == "Europe/London", "the rows should come across"
    run(db.close())
    assert new.exists() and not legacy.exists(), "the file is moved, not copied"
    assert "before the rename" in caplog.text, "the move should be logged"


def test_an_existing_new_database_is_never_overwritten(tmp_path):
    legacy = tmp_path / LEGACY_DB_NAME
    new = tmp_path / "scarlet.db"
    db = run(Database.open(str(new)))  # the live file exists first
    run(db.set_timezone(2, "Asia/Tokyo"))
    run(db.close())
    run(_seed(legacy))  # then an old one turns up beside it
    db = run(Database.open(str(new)))
    assert run(db.get_timezone(1)) is None, "the live file must win over the old one"
    assert run(db.get_timezone(2)) == "Asia/Tokyo", "the live rows must survive"
    run(db.close())
    assert legacy.exists(), "the old file is left for a human to look at"


def test_a_hot_journal_moves_with_the_file(tmp_path):
    legacy = tmp_path / LEGACY_DB_NAME
    run(_seed(legacy))
    (tmp_path / f"{LEGACY_DB_NAME}-journal").write_bytes(b"")
    db = run(Database.open(str(tmp_path / "scarlet.db")))
    run(db.close())
    assert not (tmp_path / f"{LEGACY_DB_NAME}-journal").exists(), (
        "the journal must not be left behind under the old name"
    )
