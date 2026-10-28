"""Shared clock parsing; no business-hour assumptions or inference."""
import re


def normalize_time(value):
    text = str(value or '').strip().lower().translate(str.maketrans({'o': '0', 'l': '1', 'i': '1', ';': ':'}))
    text = re.sub(r'([ap])\s*\.?\s*m\.?', r'\1m', text)
    return re.sub(r'(?<=\d)\.$', '', re.sub(r'\s+', '', text))


def parse_time(value):
    """Return (minutes on clock, explicit meridiem). Reject trailing notes."""
    text = normalize_time(value)
    match = re.fullmatch(r'(\d{1,2})[:.](\d{1,2})(am|pm)?', text)
    if not match:
        raise ValueError('Unreadable time; enter H:MM with optional AM/PM')
    hour, minute, meridiem = int(match[1]), int(match[2]), match[3]
    if minute > 59 or (meridiem and not 1 <= hour <= 12) or (not meridiem and not 0 <= hour <= 23):
        raise ValueError('Time is outside the valid clock range')
    if meridiem:
        hour = hour % 12 + (12 if meridiem == 'pm' else 0)
    return hour * 60 + minute, bool(meridiem)


