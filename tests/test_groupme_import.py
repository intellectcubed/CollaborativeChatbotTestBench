"""Raw GroupMe export lines are read in memory: sender IDs become roster pseudonyms, nothing else is kept."""

import json

import pytest

from driver.batches.files import NY, BatchError, is_groupme_export, parse_groupme

PSEUDO = {"111": "Member-1", "222": "Member-2"}


def line(**over):
    base = {"id": "1001", "created_at": 1657131170, "sender_id": "111", "sender_type": "user",
            "name": "Someone Real", "text": "34 is good Saturday", "deleted_at": None, "system": False}
    base.update(over)
    return json.dumps(base)


def test_detects_groupme_by_its_keys():
    assert is_groupme_export(line())
    assert not is_groupme_export('{"id": "b1", "created_at": "2026-03-14T13:00:00-04:00", "member": "Member-1", "text": "x"}')


def test_maps_sender_to_pseudonym_and_converts_unix_time_to_new_york():
    batch = parse_groupme(line(), "export", PSEUDO)
    (m,) = batch.messages
    assert m.member == "Member-1"
    assert m.text == "34 is good Saturday"
    assert m.created_at.tzinfo is not None
    assert m.created_at.astimezone(NY).utcoffset() is not None
    assert m.created_at.timestamp() == 1657131170


def test_names_and_sender_ids_are_not_kept_in_the_batch():
    batch = parse_groupme(line(), "export", PSEUDO)
    dumped = repr(batch)
    assert "Someone Real" not in dumped
    assert "111" not in dumped


def test_skips_system_deleted_empty_and_unknown_senders_with_a_note():
    content = "\n".join([
        line(id="1", sender_type="system"),
        line(id="2", deleted_at=1657131999),
        line(id="3", text=""),
        line(id="4", sender_id="999"),
        line(id="5"),
    ])
    batch = parse_groupme(content, "export", PSEUDO)
    assert [m.id for m in batch.messages] == ["5"]
    assert any("system or bot" in n for n in batch.notes)
    assert any("deleted" in n for n in batch.notes)
    assert any("no text" in n for n in batch.notes)
    assert any("not on the roster" in n for n in batch.notes)


def test_messages_are_put_in_time_order():
    content = "\n".join([line(id="2", created_at=1657131200), line(id="1", created_at=1657131100)])
    batch = parse_groupme(content, "export", PSEUDO)
    assert [m.id for m in batch.messages] == ["1", "2"]


def test_bad_time_and_duplicate_ids_are_reported_with_line_numbers():
    content = "\n".join([line(id="1", created_at="not a time"), line(id="2"), line(id="2")])
    with pytest.raises(BatchError) as exc:
        parse_groupme(content, "export", PSEUDO)
    assert any(e.startswith("line 1:") for e in exc.value.errors)
    assert any("duplicate id 2" in e for e in exc.value.errors)
