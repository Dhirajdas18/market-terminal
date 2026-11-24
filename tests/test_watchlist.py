import json
import os
import stat

from mt import watchlist

KNOWN = ["RELIANCE", "TCS", "INFY", "M&M"]


def test_load_drops_unknown_symbols(tmp_path):
    path = tmp_path / "w.json"
    path.write_text(json.dumps(["TCS", "GONE", "tcs", "RELIANCE", "TCS", "x" * 30, 5, None]))
    assert watchlist.load(path, known=KNOWN) == ["TCS", "RELIANCE"]


def test_load_corrupt_or_wrong_shape_is_empty(tmp_path):
    path = tmp_path / "w.json"
    for text in ("{not json", "", '{"TCS": 1}', '"TCS"', "null", "\x00\xff"):
        path.write_text(text)
        assert watchlist.load(path, known=KNOWN) == []


def test_load_missing_file_is_empty(tmp_path):
    assert watchlist.load(tmp_path / "nope.json", known=KNOWN) == []


def test_load_oversized_file_is_empty(tmp_path):
    path = tmp_path / "w.json"
    path.write_text(json.dumps(["TCS"] * 100_000))
    assert watchlist.load(path, known=KNOWN) == []


def test_save_then_load_round_trip(tmp_path):
    path = tmp_path / "cfg" / "w.json"
    watchlist.save(["INFY", "M&M"], path)
    assert watchlist.load(path, known=KNOWN) == ["INFY", "M&M"]


def test_save_is_private_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "cfg" / "w.json"
    watchlist.save(["TCS"], path)
    watchlist.save(["TCS", "INFY"], path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["w.json"]


def test_save_failure_keeps_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "w.json"
    watchlist.save(["TCS"], path)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    try:
        watchlist.save(["INFY"], path)
    except OSError:
        pass
    monkeypatch.undo()
    assert watchlist.load(path, known=KNOWN) == ["TCS"]
    assert [p.name for p in tmp_path.iterdir()] == ["w.json"]


def test_save_removes_the_temp_file_when_the_dump_fails(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise TypeError("not serialisable")

    monkeypatch.setattr(watchlist.json, "dump", boom)
    try:
        watchlist.save(["TCS"], tmp_path / "w.json")
    except TypeError:
        pass
    assert list(tmp_path.iterdir()) == []
