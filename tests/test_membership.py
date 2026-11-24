import io
import stat
import urllib.error

import pytest

from mt import membership

COMMITTED = {"TCS", "INFY", "RELIANCE"}


def _blocked():
    raise urllib.error.HTTPError("https://x", 403, "Forbidden", {}, None)


def test_same_list_no_banner(tmp_path):
    assert membership.check(COMMITTED, lambda: set(COMMITTED), tmp_path / "stamp") is None


def test_changed_list_banner_names_symbols(tmp_path):
    live = {"TCS", "INFY", "ETERNAL"}
    banner = membership.check(COMMITTED, lambda: live, tmp_path / "stamp")
    assert banner == "NIFTY 50 list changed: +ETERNAL −RELIANCE; update docs/data/nifty50.csv"


def test_blocked_fetch_skips(tmp_path, caplog):
    assert membership.check(COMMITTED, _blocked, tmp_path / "stamp") is None
    assert "HTTPError" in caplog.text


def test_checks_once_per_day(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return set(COMMITTED)

    stamp = tmp_path / "cfg" / "stamp"
    membership.check(COMMITTED, fetch, stamp, today="2026-11-24")
    membership.check(COMMITTED, fetch, stamp, today="2026-11-24")
    assert len(calls) == 1
    membership.check(COMMITTED, fetch, stamp, today="2026-11-25")
    assert len(calls) == 2
    assert stat.S_IMODE(stamp.stat().st_mode) == 0o600
    assert stat.S_IMODE(stamp.parent.stat().st_mode) == 0o700
    assert list(stamp.parent.glob("*.tmp")) == []


def test_failed_fetch_is_not_stamped(tmp_path):
    stamp = tmp_path / "stamp"
    membership.check(COMMITTED, _blocked, stamp, today="2026-11-24")
    assert not stamp.exists()


CSV = "Company Name,Industry,Symbol,Series,ISIN Code\nTata,IT,TCS,EQ,X\nInfosys,IT,INFY,EQ,Y\n"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _serve(monkeypatch, body: bytes):
    seen = {}

    def fake_open(req, timeout=None):
        seen["url"], seen["timeout"] = req.full_url, timeout
        return _Resp(body)

    monkeypatch.setattr(membership.urllib.request, "urlopen", fake_open)
    return seen


def test_fetch_parses_symbols_over_https_with_timeout(monkeypatch):
    seen = _serve(monkeypatch, CSV.encode())
    assert membership.fetch_nse() == {"TCS", "INFY"}
    assert seen["url"].startswith("https://nsearchives.nseindia.com/") and seen["timeout"] == 15


@pytest.mark.parametrize(
    "body",
    [
        b"Name,Symbol\nA,TCS\n",  # no Industry column
        b"Industry,Symbol\n" + b"".join(b"IT,S%d\n" % i for i in range(101)),
        b"Industry,Symbol\nIT,bad symbol!\n",
        b"Industry,Symbol\n" + b"IT,TCS\n" * 200_000,  # over 1 MB
    ],
)
def test_fetch_rejects_bad_files(monkeypatch, body):
    _serve(monkeypatch, body)
    with pytest.raises(ValueError):
        membership.fetch_nse()
