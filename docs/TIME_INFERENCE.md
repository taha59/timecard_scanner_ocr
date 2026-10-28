# Editing the AM/PM policy

All suffix assumptions live in [`backend/time_inference.py`](../backend/time_inference.py).
The rule function is pure: it returns a decision and annotations without changing
its inputs, calling OCR, or using written totals. Clock parsing is separate in
[`backend/clock.py`](../backend/clock.py).

## Rule order

1. Keep complete AM/PM suffixes exactly as entered or recognized.
2. Complete an isolated trailing `a` or `p`, ignoring case, spacing, and dots.
   On initial OCR results, the raw reading must match the selected clock digits.
   Letters elsewhere in a sentence do not count as evidence.
3. For remaining missing suffixes, choose a valid pair within the same workday.
   Prefer PM for OUT. Prefer AM for IN from 6:00 through 11:59; otherwise prefer
   PM for ambiguous 12-hour starts. These are soft preferences, not opening hours.
4. Finish no later than 11:59 PM. Do not turn conflicting punches into overnight
   hours. Keep their text for correction, flag them, and exclude them from totals.

Missing/unreadable clock digits remain missing. A valid 24-hour clock such as
`13:00` keeps its meaning. Shifts longer than twelve hours are allowed and retain
the calculator's existing review warning.

| Input | Result |
| --- | --- |
| `9:00a` → `5:00p` | `9:00am` → `5:00pm` |
| `3:15` → `11:40` | `3:15pm` → `11:40pm` |
| `11:00` → `2:00` | `11:00am` → `2:00pm` |
| `9:00am` → `10:35` | `9:00am` → `10:35pm`, 13:35 hours |
| `11:00pm` → `2:00am` | Text unchanged; same-day conflict, excluded |

## Change or disable a rule

Edit the `TimePolicy` field defaults near the top of `time_inference.py`.
`DEFAULT_POLICY = TimePolicy()` uses those settings everywhere in the app.

| Setting | Purpose |
| --- | --- |
| `partial_suffixes` | Complete trailing `a`/`p` before schedule guesses |
| `schedule_biases` | Add missing suffixes using pair/schedule preferences |
| `morning_start_hour` | Start of the AM preference window, currently 6 |
| `preferred_out_suffix` | OUT preference, currently `pm` |
| `same_day_only` | Reject overnight interpretations, currently true |
| `latest_out_minute` | Latest OUT in minutes after midnight, currently `23*60+59` |

For example, `morning_start_hour=7` shifts the morning preference to 7 AM.
Set an individual boolean to `False` to disable that part of the policy.

To disable the entire policy without changing code, set this backend environment
variable and restart/redeploy Render:

```dotenv
TIME_INFERENCE_ENABLED=false
```

That restores the earlier interpretation of newly processed bare clock strings.
It does not remove suffixes already populated in an open browser tab. Start a new
scan to compare policies. The legacy calculator API remains usable without a
policy: its optional `time_policy` parameter defaults to `None`.

## Integration and review

All three app paths use the same policy: device results, optional server OCR,
and `/api/calculate`. Only initial OCR results pass raw suffix evidence; edits
use the current fields so stale raw OCR cannot change a correction.

Each inferred field gets `time_inference` metadata (`original`, `value`, `suffix`,
`source`) and a review flag. The UI displays a small `AM assumed`, `PM inferred`,
or recovered label. Explicitly editing that field clears its previous annotation;
editing an employee name or written total preserves it. Raw OCR stays available
in the source inspector. OCR confidence is not raised by an assumption.

Tests are in `tests/test_time_inference.py`. They cover the rule examples,
conflicts, disabling rules, unchanged explicit suffixes, repeated calculation,
stale raw data, and replay through crops from a real supplied photo. Fixed-reading
tests verify parsing/policy plumbing, not handwriting recognition accuracy.
