"""Rate limits, as the server describes them rather than as we guess. [1.48]

Phase 0's second run stalled and then failed at concurrency 8. The cause was not that the
provider was rate-limiting — it was that the retry ignored `Retry-After`. Backoff capped
at 60s, so all four attempts landed inside the same closed quota window, the budget was
spent without ever waiting for the reset, and the run reported a provider failure for
what was really a scheduling mistake on our side.
"""

import datetime as dt
from email.utils import format_datetime

from src.llm import _retry_after


class _Resp:
    def __init__(self, headers):
        self.headers = headers


class _Exc(Exception):
    def __init__(self, headers):
        super().__init__("rate limited")
        self.response = _Resp(headers)


def test_a_stated_delay_in_seconds_is_read():
    assert _retry_after(_Exc({"retry-after": "30"})) == 30.0


def test_the_header_is_matched_whatever_its_case():
    assert _retry_after(_Exc({"Retry-After": "12"})) == 12.0


def test_an_http_date_is_read_as_a_delay():
    when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=45)
    got = _retry_after(_Exc({"retry-after": format_datetime(when)}))
    assert got is not None and 30 <= got <= 60


def test_a_date_already_past_is_no_wait_at_all():
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=90)
    assert _retry_after(_Exc({"retry-after": format_datetime(when)})) == 0.0


def test_an_unreasonable_delay_is_capped():
    """A server asking for an hour is refusing the run, not pacing it. A migration
    silently asleep that long is worse than one that stops and says why."""
    assert _retry_after(_Exc({"retry-after": "86400"})) == 300.0


def test_no_header_means_fall_back_to_backoff():
    assert _retry_after(_Exc({})) is None


def test_an_unparseable_header_is_not_an_error():
    """A malformed header must not become the reason a migration fails."""
    assert _retry_after(_Exc({"retry-after": "soon"})) is None


def test_an_exception_carrying_no_response_is_handled():
    assert _retry_after(Exception("boom")) is None


def test_headers_on_the_exception_itself_are_read():
    """Different SDKs hang the headers in different places."""
    e = Exception("x")
    e.headers = {"retry-after": "7"}
    assert _retry_after(e) == 7.0


# ── a call in flight is not a hang ────────────────────────────────────────────
#
# The heartbeat added to the orchestrator fires when a *target* completes, which says
# nothing while one provider call is wedged. With a 600s request timeout over four
# attempts, that is forty minutes of a run that looks idle and is not — the exact
# condition Phase 0 spent twenty minutes diagnosing by hand.

import time

from src import llm


def test_a_slow_call_says_so(capsys, monkeypatch):
    monkeypatch.setattr(llm, "_SLOW_CALL_SECONDS", 0.05)
    stop = llm._watchdog("generate_Thing", seconds=0.05)
    time.sleep(0.18)
    stop()
    out = capsys.readouterr().out
    assert "still waiting on the provider" in out
    assert "generate_Thing" in out


def test_it_keeps_saying_so(capsys):
    """One notice then silence is barely better than silence: the question a person has
    is "is it still going", and that has to be answerable more than once."""
    stop = llm._watchdog("generate_Thing", seconds=0.05)
    time.sleep(0.28)
    stop()
    assert capsys.readouterr().out.count("still waiting") >= 2


def test_a_fast_call_says_nothing(capsys):
    """Nine hundred calls each announcing themselves is not progress reporting."""
    stop = llm._watchdog("generate_Thing", seconds=5.0)
    stop()
    assert "still waiting" not in capsys.readouterr().out


def test_the_watchdog_stops_when_the_call_succeeds(capsys):
    calls = []
    stop = llm._watchdog("s", seconds=0.05)
    assert llm._cancelling(lambda: calls.append(1) or "done", stop) == "done"
    time.sleep(0.15)
    assert "still waiting" not in capsys.readouterr().out


def test_the_watchdog_stops_when_the_call_raises(capsys):
    """A timer left armed after a failure prints against a call that is no longer
    running, which is worse than not reporting at all."""
    stop = llm._watchdog("s", seconds=0.05)
    try:
        llm._cancelling(lambda: (_ for _ in ()).throw(ValueError("x")), stop)
    except ValueError:
        pass
    time.sleep(0.15)
    assert "still waiting" not in capsys.readouterr().out
