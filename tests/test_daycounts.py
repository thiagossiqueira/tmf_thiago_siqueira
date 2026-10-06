from calendars.daycounts import DayCounts


DAYCOUNT = DayCounts(
    "bus/252",
    calendar="cdr_anbima",
)


def test_november_20_is_national_holiday_from_2024():
    # Lei 14.759/2023 made 20-Nov a national holiday.
    # Under BUS/252, [2024-11-20, 2024-11-21) must therefore
    # contain zero business days.
    assert DAYCOUNT.days(
        "2024-11-20",
        "2024-11-21",
    ) == 0


def test_november_20_2023_remains_business_day():
    # The law entered into force only after 20-Nov-2023.
    assert DAYCOUNT.days(
        "2023-11-20",
        "2023-11-21",
    ) == 1
