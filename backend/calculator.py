"""Pure payroll arithmetic. No OCR, I/O, network, or frontend dependencies.

Minutes are integers; decimal input uses Decimal. Unresolved work produces None,
never an invented zero. Written totals are compared only AFTER punch arithmetic.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

STATUSES = {'worked', 'off', 'blank', 'crossed_out', 'unknown'}


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


def format_minutes(minutes):
    if minutes is None:
        return {'minutes': None, 'hm': None, 'decimal': None}
    sign = '-' if minutes < 0 else ''
    hours, mins = divmod(abs(minutes), 60)
    return {'minutes': minutes, 'hm': f'{sign}{hours}:{mins:02d}',
            'decimal': str((Decimal(minutes) / 60).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))}


def adjustment_minutes(value):
    """Explicit signed decimal hours or H:MM. Round once to nearest minute."""
    text = str(value if value is not None else '').strip()
    if re.fullmatch(r'[+-]?\d{1,4}:\d{2}', text):
        sign = -1 if text.startswith('-') else 1
        hour, minute = text.lstrip('+-').split(':')
        if int(minute) > 59:
            raise ValueError('Adjustment minutes must be 00–59')
        result = sign * (int(hour) * 60 + int(minute))
    else:
        if not re.fullmatch(r'[+-]?\d{1,4}(?:\.\d{1,6})?', text):
            raise ValueError('Enter adjustment as decimal hours or H:MM')
        try:
            result = int((Decimal(text) * 60).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        except (InvalidOperation, OverflowError):
            raise ValueError('Invalid adjustment') from None
    if abs(result) > 60000:
        raise ValueError('Adjustment exceeds 1000 hours')
    return result


def calculate_day(day, confidence_threshold=.8):
    result = deepcopy(day)
    flags = []
    status = day.get('status', 'unknown')
    minutes = None
    if status not in STATUSES:
        flags.append('Unknown day status')
    elif status in {'off', 'blank', 'crossed_out'}:
        minutes = 0
        if status == 'crossed_out':
            flags.append('Crossed-out day: review exclusion')
        if str(day.get('in', '')).strip() or str(day.get('out', '')).strip():
            flags.append('Punch text on excluded day: verify status')
    elif status == 'unknown':
        flags.append('Unreadable day status: human review required')
    else:
        if not str(day.get('in') or '').strip() or not str(day.get('out') or '').strip():
            flags.append('Missing punch')
        else:
            try:
                start, start_explicit = parse_time(day.get('in'))
                end, end_explicit = parse_time(day.get('out'))
                modulus = 1440 if start_explicit and end_explicit else 720
                minutes = (end - start) % modulus
                if modulus == 720:
                    flags.append('AM/PM inferred')
                if minutes > 720:
                    flags.append('Shift over 12 hours')
                if minutes == 0:
                    flags.append('Zero-length shift: verify punches')
            except ValueError as error:
                flags.append(str(error))
    for key in ('confidence', 'in_confidence', 'out_confidence', 'status_confidence'):
        confidence = day.get(key)
        if confidence is not None and (not isinstance(confidence, (int, float)) or not confidence_threshold <= confidence <= 1):
            flags.append('Low OCR confidence: verify original crop')
            break
    if day.get('status_guessed'):
        flags.append('Status guessed from ink fraction: verify original crop')
    if day.get('ocr_recovered'):
        flags.append('Tentative OCR recovery: verify digits against source crop')
    if day.get('ocr_cross_check_skipped'):
        flags.append('Alternate OCR crop not checked: verify original crop')
    if day.get('ocr_conflict'):
        flags.append('OCR readings disagree: verify original crop')
    if day.get('source') == 'ocr' and not day.get('reviewed', False):
        flags.append('OCR row not yet reviewed')
    adjustment = None
    try:
        adjustment = adjustment_minutes(day.get('adjustment_hours', '0'))
        if day.get('adjustment_confirmed', True) is not True:
            adjustment = None
            flags.append('Adjustment note requires confirmation; not added')
    except ValueError as error:
        flags.append(str(error))
    result.update(computed=format_minutes(minutes), adjustment=format_minutes(adjustment), flags=flags)
    return result


def written_total_candidates(value):
    """Ambiguous 27.07 has BOTH 27:07 and decimal-hour interpretations."""
    text = str(value or '').lower().strip()
    text = re.sub(r'\s*(?:hours?|hrs?)\.?$', '', text).strip()
    match = re.fullmatch(r'(\d{1,4})[:.](\d{1,2})', text)
    candidates = []
    if match:
        hour, minute = int(match[1]), int(match[2])
        if minute < 60:
            candidates.append({'interpretation': 'H:MM', **format_minutes(hour * 60 + minute)})
        if '.' in text:
            candidates.append({'interpretation': 'decimal hours', **format_minutes(int((Decimal(text)*60).quantize(Decimal('1'), rounding=ROUND_HALF_UP)))})
    elif re.fullmatch(r'\d{1,3}', text):
        candidates.append({'interpretation': 'whole hours', **format_minutes(int(text) * 60)})
    return candidates


def calculate_card(card, confidence_threshold=.8):
    result = deepcopy(card)
    days = [calculate_day(day, confidence_threshold) for day in card.get('days', [])]
    if len(days) != 7:
        raise ValueError('Each card must contain exactly 7 day slots')
    punch_known = sum(day['computed']['minutes'] or 0 for day in days)
    adjustment_known = sum(day['adjustment']['minutes'] or 0 for day in days)
    punch_complete = all(day['computed']['minutes'] is not None for day in days)
    adjustment_complete = all(day['adjustment']['minutes'] is not None for day in days)
    regular = punch_known if punch_complete else None
    adjustments = adjustment_known if adjustment_complete else None
    grand = regular + adjustments if regular is not None and adjustments is not None else None
    totals = {'regular': format_minutes(regular), 'adjustments': format_minutes(adjustments),
              'grand': format_minutes(grand), 'known_punch_subtotal': format_minutes(punch_known),
              'complete': punch_complete and adjustment_complete}
    # Written total is intentionally inaccessible until AFTER all computation above.
    written = str(card.get('written_total') or '')
    candidates = written_total_candidates(written)
    comparisons = [{**candidate, 'difference': format_minutes(grand - candidate['minutes']) if grand is not None else format_minutes(None)} for candidate in candidates]
    match = grand is not None and any(candidate['minutes'] == grand for candidate in candidates)
    message = None
    if written:
        if not candidates:
            message = 'Unreadable written total; review before paying'
        elif grand is None:
            message = 'Unresolved punches or adjustments; review before paying'
        elif not match:
            message = 'Written total mismatch; review before paying'
        elif len(candidates) > 1:
            message = 'Written total format is ambiguous; review before paying'
    result.update(days=days, totals=totals,
                  cross_check={'raw': written, 'candidates': comparisons, 'matches': match, 'message': message},
                  needs_review=bool(message or any(day['flags'] for day in days)))
    return result


def calculate_cards(cards, confidence_threshold=.8):
    return [calculate_card(card, confidence_threshold) for card in cards]
