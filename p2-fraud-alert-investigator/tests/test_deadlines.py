from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from investigator.deadlines import is_business_day, receipt_business_day, uk_deadlines

LON = ZoneInfo("Europe/London")


def at(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=LON)


def test_ordinary_weekday_before_cutoff():
    d = uk_deadlines(at(2026, 10, 13, 10))  # Tuesday
    assert (d.received_on, d.decide_suspicion_by, d.execute_or_refuse_by) == \
        (date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 19))


def test_friday_after_cutoff_counts_as_monday():
    d = uk_deadlines(at(2026, 10, 16, 17, 30))
    assert d.received_on == date(2026, 10, 19)
    assert d.decide_suspicion_by == date(2026, 10, 20)
    assert d.execute_or_refuse_by == date(2026, 10, 23)


def test_exactly_at_cutoff_rolls_over():
    assert receipt_business_day(at(2026, 10, 13, 17, 0)) == date(2026, 10, 14)


def test_cutoff_is_configurable():
    assert receipt_business_day(at(2026, 10, 13, 17, 30), cutoff=time(18, 0)) == date(2026, 10, 13)


def test_weekend_counts_as_monday():
    assert uk_deadlines(at(2026, 10, 17, 9)).received_on == date(2026, 10, 19)


def test_bank_holidays_are_skipped():
    # Thu 24 Dec 2026 after cut-off -> Fri 25 (Christmas) and Mon 28 (substitute Boxing Day) are holidays.
    assert not is_business_day(date(2026, 12, 25)) and not is_business_day(date(2026, 12, 28))
    d = uk_deadlines(at(2026, 12, 24, 18))
    assert d.received_on == date(2026, 12, 29)
    assert d.decide_suspicion_by == date(2026, 12, 30)
    assert d.execute_or_refuse_by == date(2027, 1, 5)  # 1 Jan is a holiday


def test_utc_input_is_converted_to_london():
    # 16:30 UTC is 17:30 BST, so after cut-off.
    assert receipt_business_day(datetime(2026, 10, 13, 16, 30, tzinfo=ZoneInfo("UTC"))) == date(2026, 10, 14)


def test_naive_time_is_refused():
    with pytest.raises(ValueError):
        uk_deadlines(datetime(2026, 10, 13, 10))
