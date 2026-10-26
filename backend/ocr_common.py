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


def tentative_clock_text(text):
    """Recover formatting only in an isolated punch crop; never invent digits.

    Used only after ordinary crop readings fail. Any result is explicitly flagged
    as tentative. It does not change the strict parser used for normal readings.
    """
    if clock_text(text):return clock_text(text)
    raw=text.strip()
    if not raw or len(raw)>60:return ''
    # A crop containing two times, a date, or a signed duration is ambiguous.
    if len(re.findall(r'\d{1,2}\s*[:.]\s*\d{2}',raw))>1:return ''
    if re.search(r'\d[./]\d{1,2}[./]\d',raw):return ''
    if raw.startswith(('+','-')):return ''
    normalized=raw.translate(str.maketrans({'L':'1','I':'1','l':'1','O':'0','o':'0','S':'5','s':'5',';':':','：':':'}))
    # Missing separator: 1125PM -> 11:25pm; only explicit numeric content and
    # an optional complete meridiem are allowed, never a fragment such as 3ioa.
    compact=re.fullmatch(r'(\d{3,4})\s*([ap]\s*\.?\s*m\.?)?',normalized,re.I)
    if compact:
        digits=compact[1];suffix=re.sub(r'[\s.]','',compact[2] or '').lower()
        return clock_text(f'{digits[:-2]}:{digits[-2:]}{suffix}')
    # Recover a visible H:MM prefix when a line contains stray suffix characters
    # or fragments of the next line. Do not infer an unknown AM/PM suffix.
    prefix=re.fullmatch(r'(\d{1,2})\s*:\s*(\d{2})(.*)',normalized)
    if prefix:
        remainder=prefix[3].strip()
        if len(remainder)>12 or re.match(r'[.:/]\s*\d',remainder):return ''
        meridiem=re.fullmatch(r'([ap]\s*\.?\s*m\.?)\s*[^\d]*',remainder,re.I)
        suffix=re.sub(r'[\s.]','',meridiem[1]).lower() if meridiem else ''
        return clock_text(f'{prefix[1]}:{prefix[2]}{suffix}')
    return ''
