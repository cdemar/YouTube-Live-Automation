"""Pure date-math functions — no mocking needed, just freezegun to control "today"."""
import datetime

import pytest
from freezegun import freeze_time

import handler

WEEKDAYS_2026 = {
    "monday": "2026-06-08",
    "tuesday": "2026-06-09",
    "wednesday": "2026-06-10",
    "thursday": "2026-06-11",
    "friday": "2026-06-12",
    "saturday": "2026-06-13",
    "sunday": "2026-06-14",
}


class TestGetLastSunday:
    @pytest.mark.parametrize("frozen_date", WEEKDAYS_2026.values(), ids=WEEKDAYS_2026.keys())
    def test_always_returns_a_sunday_strictly_in_the_past(self, frozen_date):
        with freeze_time(frozen_date):
            today = datetime.date.today()
            result = handler.get_last_sunday()

        assert result.weekday() == 6  # Monday=0 ... Sunday=6
        assert result < today
        assert (today - result).days <= 7

    def test_exact_value_on_a_tuesday(self):
        # Tuesday June 9, 2026 -> last Sunday is June 7, 2026.
        with freeze_time("2026-06-09"):
            assert handler.get_last_sunday() == datetime.date(2026, 6, 7)

    def test_when_today_is_sunday_returns_previous_sunday_not_today(self):
        # The "last completed Sunday" should never be today, even if today IS Sunday.
        with freeze_time(WEEKDAYS_2026["sunday"]):
            result = handler.get_last_sunday()
        assert result == datetime.date(2026, 6, 7)


class TestGetNextSunday:
    @pytest.mark.parametrize("frozen_date", WEEKDAYS_2026.values(), ids=WEEKDAYS_2026.keys())
    def test_always_returns_a_sunday_strictly_in_the_future(self, frozen_date):
        with freeze_time(frozen_date):
            today = datetime.date.today()
            result = handler.get_next_sunday()

        assert result.weekday() == 6
        assert result > today
        assert (result - today).days <= 7

    def test_exact_value_on_a_tuesday(self):
        # Tuesday June 9, 2026 -> next Sunday is June 14, 2026.
        with freeze_time("2026-06-09"):
            assert handler.get_next_sunday() == datetime.date(2026, 6, 14)

    def test_when_today_is_sunday_returns_next_sunday_not_today(self):
        with freeze_time(WEEKDAYS_2026["sunday"]):
            result = handler.get_next_sunday()
        assert result == datetime.date(2026, 6, 21)


class TestMakeStreamDatetime:
    def test_sets_correct_hour_minute_and_date(self):
        result = handler.make_stream_datetime(datetime.date(2026, 5, 11), 11, 15)
        assert (result.year, result.month, result.day) == (2026, 5, 11)
        assert (result.hour, result.minute) == (11, 15)

    def test_uses_america_los_angeles_timezone(self):
        result = handler.make_stream_datetime(datetime.date(2026, 5, 11), 11, 15)
        assert str(result.tzinfo) == "America/Los_Angeles"

    def test_dst_boundary_before_spring_forward_is_pst_utc_minus_8(self):
        # DST 2026 starts Sunday March 8 at 2am local. A stream the week before
        # (March 1) should resolve to standard time, UTC-8.
        result = handler.make_stream_datetime(datetime.date(2026, 3, 1), 11, 15)
        assert result.utcoffset() == datetime.timedelta(hours=-8)

    def test_dst_boundary_after_spring_forward_is_pdt_utc_minus_7(self):
        # March 8, 2026 11:15am is after that morning's 2am transition, so it
        # must resolve to daylight time, UTC-7 — not UTC-8.
        result = handler.make_stream_datetime(datetime.date(2026, 3, 8), 11, 15)
        assert result.utcoffset() == datetime.timedelta(hours=-7)


class TestFormatDate:
    def test_formats_as_month_day_year(self):
        assert handler.format_date(datetime.date(2026, 5, 11)) == "May 11, 2026"

    def test_single_digit_day_has_no_leading_zero(self):
        assert handler.format_date(datetime.date(2026, 5, 1)) == "May 1, 2026"
