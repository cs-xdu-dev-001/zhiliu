from __future__ import annotations


_APScheduler_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _expand_numeric_weekday(part: str) -> set[int] | None:
    base, separator, step_text = part.partition("/")
    if separator:
        if not step_text.isdigit() or int(step_text) < 1:
            return None
        step = int(step_text)
    else:
        step = 1

    if base == "*":
        return set(range(0, 7, step))
    if base.isdigit():
        value = int(base)
        return {value} if value in range(0, 8) else None
    if "-" not in base:
        return None
    start_text, end_text = base.split("-", 1)
    if not start_text.isdigit() or not end_text.isdigit():
        return None
    start, end = int(start_text), int(end_text)
    if start not in range(0, 8) or end not in range(0, 8) or start > end:
        return None
    return set(range(start, end + 1, step))


def normalize_weekday_for_apscheduler(schedule: str) -> str:
    """Keep legacy croniter weekday numbers correct for APScheduler.

    The project historically exposed croniter's Sunday=0/Monday=1 convention,
    while APScheduler parses numeric weekdays as Monday=0. Named weekdays are
    understood consistently by both libraries, so only numeric weekday fields
    are expanded and rewritten to names.
    """
    fields = schedule.split()
    if len(fields) != 5:
        return schedule
    weekday = fields[4]
    if not any(character.isdigit() for character in weekday):
        return schedule

    values: set[int] = set()
    for part in weekday.split(","):
        if part == "*":
            return schedule
        expanded = _expand_numeric_weekday(part)
        if expanded is None:
            return schedule
        values.update(expanded)
    if not values:
        return schedule
    # croniter accepts 7 as Sunday; APScheduler's named value avoids ambiguity.
    normalized = {6 if value in {0, 7} else value - 1 for value in values}
    if normalized == set(range(7)):
        fields[4] = "*"
    else:
        fields[4] = ",".join(_APScheduler_WEEKDAYS[index] for index in sorted(normalized))
    return " ".join(fields)
