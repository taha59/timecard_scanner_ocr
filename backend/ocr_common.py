"""Conservative parsing shared by platform-independent OCR adapters."""
import re

from .calculator import parse_time


def clock_text(text):
    """Keep a clock prefix; never guess digits or a malformed AM/PM suffix."""
    text = text.strip()
    match = re.fullmatch(r'([0-9OoIlISs]{1,2}\s*[:.]\s*[0-9OoIlISs]{2})([^\d]*)', text)
    if not match:
        return ''
    clock = re.sub(r'\s+', '', match[1]).translate(
        str.maketrans({'I':'1','l':'1','O':'0','o':'0','S':'5','s':'5'}))
    suffix = re.sub(r'[\s.]', '', match[2]).lower()
    if suffix in {'am', 'pm'}:
        clock += suffix
    try:
        parse_time(clock)
        return clock
    except ValueError:
        return ''
