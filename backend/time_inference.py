"""Optional AM/PM completion. This module contains every editable business bias.

It never creates missing clock digits, changes a complete suffix, or consults
written hours. It returns a possible interval; payroll totals stay in calculator.
"""
from dataclasses import dataclass, field
from itertools import product
import re
from .clock import normalize_time, parse_time


@dataclass(frozen=True)
class TimePolicy:
    enabled: bool = True
    partial_suffixes: bool = True
    schedule_biases: bool = True
    same_day_only: bool = True
    latest_out_minute: int = 23 * 60 + 59
    # Soft preferences, not a restriction on when an employee can start.
    morning_start_hour: int = 6
    preferred_out_suffix: str = 'pm'


DEFAULT_POLICY = TimePolicy()


@dataclass
class PairInference:
    start: str
    end: str
    minutes: int | None = None
    conflict: bool = False
    annotations: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)


@dataclass
class _Endpoint:
    text: str
    clock: str
    # One candidate for recognized full/partial suffixes or 24-hour clocks.
    # A bare 1..12-hour time has two candidates only when schedule bias is on.
    candidates: list
    original: str
    evidence: str | None = None


def _suffix_evidence(raw, clock):
    """Read only a complete clock plus an isolated a/p or am/pm suffix."""
    if not isinstance(raw, str) or len(raw) > 500:
        return None
    normalized = normalize_time(raw).translate(str.maketrans({'s': '5'}))
    match = re.fullmatch(r'(\d{1,2}[:.]\d{1,2})(am|pm|a|p)\.?', normalized)
    if not match:
        return None
    try:
        # Match the selected clock before using its raw suffix. Never apply
        # a suffix from another crop/time, or from the middle of a sentence.
        selected, _ = parse_time(clock)
        raw_clock, _ = parse_time(match[1])
        suffix = match[2] if len(match[2]) == 2 else match[2] + 'm'
        parse_time(match[1] + suffix)
    except ValueError:
        return None
    if selected % 720 != raw_clock % 720:
        return None
    return suffix, 'partial_suffix' if len(match[2]) == 1 else 'raw_suffix'


def _endpoint(value, raw, policy):
    text = str(value or '').strip()
    if not text:
        return None
    normalized = normalize_time(text)
    try:
        minutes, explicit = parse_time(text)
    except ValueError:
        # Also supports a manually entered trailing a/p, without changing the
        # shared strict parser or recognition/retry policy.
        partial = re.fullmatch(r'(\d{1,2}[:.]\d{1,2})[ap]\.?', normalized)
        if not partial or not policy.partial_suffixes:
            return None
        evidence = _suffix_evidence(text, partial[1])
        if not evidence:
            return None
        suffix, source = evidence
        completed = partial[1] + suffix
        return _Endpoint(completed, partial[1], [(parse_time(completed)[0], suffix)], text, source)
    if explicit:
        return _Endpoint(text, normalized[:-2], [(minutes, normalized[-2:])], text)
    hour = minutes // 60
    if hour == 0 or hour > 12:
        return _Endpoint(text, normalized, [(minutes, None)], text)
    evidence = _suffix_evidence(raw, normalized)
    if evidence and (evidence[1] != 'partial_suffix' or policy.partial_suffixes):
        suffix, source = evidence
        completed = normalized + suffix
        return _Endpoint(completed, normalized, [(parse_time(completed)[0], suffix)], text, source)
    candidates = [(minutes % 720, 'am'), (minutes % 720 + 720, 'pm')] if policy.schedule_biases else []
    return _Endpoint(text, normalized, candidates, text)


def _preferred_start(endpoint, policy):
    hour = parse_time(endpoint.clock)[0] // 60
    return 'am' if policy.morning_start_hour <= hour < 12 else 'pm'


def _annotate(result, name, endpoint, suffix, source):
    value = endpoint.clock + suffix
    if name == 'in':
        result.start = value
    else:
        result.end = value
    result.annotations[name] = {'original': endpoint.original, 'value': value,
                                'suffix': suffix, 'source': source}


def infer_time_pair(start, end, *, raw_start='', raw_end='', previous=None, policy=DEFAULT_POLICY):
    """Complete missing suffixes and return an auditable decision, without mutation."""
    result = PairInference(str(start or '').strip(), str(end or '').strip())
    if not policy.enabled:
        return result
    endpoints = [_endpoint(start, raw_start, policy), _endpoint(end, raw_end, policy)]
    for name, endpoint in zip(('in', 'out'), endpoints):
        if endpoint and endpoint.evidence:
            _annotate(result, name, endpoint, endpoint.candidates[0][1], endpoint.evidence)
    if all(endpoint and endpoint.candidates for endpoint in endpoints):
        first, last = endpoints
        pairs = [(a, b) for a, b in product(first.candidates, last.candidates)
                 if (not policy.same_day_only or b[0] >= a[0]) and b[0] <= policy.latest_out_minute]
        if pairs:
            # Business preferences are deliberately isolated here. No short-shift
            # cap: the supplied timecards include shifts longer than twelve hours.
            a, b = min(pairs, key=lambda pair: (pair[1][1] != policy.preferred_out_suffix,
                                               pair[0][1] != _preferred_start(first, policy)))
            result.minutes = b[0] - a[0] if b[0] >= a[0] else b[0] - a[0] + 1440
            for name, endpoint, candidate in [('in', first, a), ('out', last, b)]:
                if len(endpoint.candidates) == 2:
                    _annotate(result, name, endpoint, candidate[1], 'schedule')
        else:
            result.conflict = True
            result.flags.append('Times conflict with same-day working hours; review AM/PM before including hours')
    # Keep valid provenance on recalculation; editing an input clears its old
    # annotation in the UI. Raw OCR evidence is supplied only on initial scans.
    for name, value in [('in', result.start), ('out', result.end)]:
        old = previous.get(name) if isinstance(previous, dict) else None
        if name not in result.annotations and isinstance(old, dict):
            if (old.get('source') in {'partial_suffix', 'raw_suffix', 'schedule'}
                    and isinstance(old.get('value'), str) and normalize_time(old['value']) == normalize_time(value)
                    and old.get('suffix') in {'am', 'pm'}):
                result.annotations[name] = dict(old)
    for name, annotation in result.annotations.items():
        suffix = annotation['suffix'].upper()
        if annotation['source'] == 'schedule':
            message = f'{name.upper()} {suffix} assumed from schedule; verify source crop'
        elif annotation['source'] == 'partial_suffix':
            message = f"{name.upper()} {suffix} inferred from trailing '{suffix[0].lower()}'; verify source crop"
        else:
            message = f'{name.upper()} {suffix} recovered from raw OCR; verify source crop'
        result.flags.append(message)
    return result
