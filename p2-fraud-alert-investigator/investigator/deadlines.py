"""UK deadlines for a held outbound payment (FCA FG24/6 paras 3.3-3.4; D3).

Suspicion must be established by the end of the business day after receipt; the payment can be held until
the end of the 4th business day after receipt. Business days exclude weekends and England & Wales bank
holidays. A payment received on a non-business day, or at or after the cut-off, counts as received on the
next business day (our modelling assumption, D3).
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
CUTOFF = time(17, 0)  # configurable per call
HOLIDAYS_FILE = Path(__file__).resolve().parent.parent / "data" / "uk_bank_holidays.json"


@cache
def bank_holidays(path: Path = HOLIDAYS_FILE) -> frozenset[date]:
    return frozenset(date.fromisoformat(d["date"]) for d in json.loads(path.read_text(encoding="utf-8"))["dates"])


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in bank_holidays()


def next_business_day(day: date) -> date:
    day += timedelta(days=1)
    while not is_business_day(day):
        day += timedelta(days=1)
    return day


def add_business_days(day: date, n: int) -> date:
    for _ in range(n):
        day = next_business_day(day)
    return day


def receipt_business_day(received_at: datetime, cutoff: time = CUTOFF) -> date:
    if received_at.tzinfo is None:
        # A naive time would silently mean the wrong deadline for a whole day around midnight.
        raise ValueError("received_at must be timezone-aware")
    local = received_at.astimezone(LONDON)
    day = local.date()
    if not is_business_day(day) or local.time() >= cutoff:
        day = next_business_day(day)
    return day


@dataclass(frozen=True)
class UkDeadlines:
    received_on: date           # the business day the payment counts as received
    decide_suspicion_by: date   # end of this business day
    execute_or_refuse_by: date  # end of this business day


def uk_deadlines(received_at: datetime, cutoff: time = CUTOFF) -> UkDeadlines:
    received_on = receipt_business_day(received_at, cutoff)
    return UkDeadlines(received_on, add_business_days(received_on, 1), add_business_days(received_on, 4))
