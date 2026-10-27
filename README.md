# Timecard Scanner

Device OCR with a stateless Python cropping and calculation API.

See [DEPLOYMENT.md](DEPLOYMENT.md) for Vercel frontend + Render backend setup. No uploaded photos are persisted by the application. Server OCR is disabled by default. Model downloads require user consent. Every recognized entry requires review.

Private fixture photos are deliberately excluded from this public repository. Tests involving those photos require local fixtures.

See [MISSING_ENTRIES.md](MISSING_ENTRIES.md) for real-photo missing-punch recovery checks and remaining errors.

## Editing timecards

Each employee has a collapsible table with visible source crops, Time in, Time out, and Hours. Tap a crop to enlarge it; View timecard shows the whole card. The phone layout fits both time fields without horizontal scrolling.

Enter or correct times directly. There are no status controls, notes/adjustment fields, or reviewed checkboxes. Clear both fields to exclude a day. Only complete valid pairs contribute to the employee total; incomplete or invalid pairs are excluded and flagged without blocking the other days. Notes and adjustments are ignored.

Edits recalculate on the backend. Explicit AM/PM supports overnight shifts; missing meridiem uses the existing modulo-12-hour calculation and shows a warning. Written totals remain a cross-check and cannot change calculated hours. OCR warnings are available under Check entry.
