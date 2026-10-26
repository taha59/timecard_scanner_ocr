# Handwriting against the IN/OUT strip

The normalized printed strip ends at x=190, but ordinary recognition cells begin
at x=198. The cleaner also removes three boundary columns. Handwriting in this
margin could lose a leading digit: 10:55 became 0:55, or 11:45 became 1:45.

Device recognition now checks dark ink near that boundary and prepares an extra
crop starting at x=190. Printed green pixels are suppressed for this retry.
The browser runs it after the existing retries, only for unresolved punches or
hours starting with 0, 1, or 2 that may have lost a leading 1. Existing valid
times remain preferred unless the wider reading restores that leading digit
with matching minutes and a compatible meridiem. All recoveries remain flagged
for review, and conflicting readings remain visible. Older prepared scans can
still finish without the new crop. The review image also includes the strip
margin so the user can inspect the complete handwriting.

The PP-OCRv6 recognition model and weights are unchanged. No photos are saved on
the server. Real supplied photos were tested locally, without uploading employee
photos to hosting or using synthetic timecards for accuracy claims.

Native ONNX comparison against release 7a81062: the three earlier real-photo
regression sets retained their clock-digit scores (47/48, 39/44, and 6/6). In the
new seven-card case, the affected card improved from 1/6 to 5/6 correct OUT clock
fields, with no missing OUT field after the fix. Native ONNX and browser WASM
can differ; these numbers compare clock digits modulo 12 hours, not AM/PM.

Final browser WASM check on the seven-card photo read all six affected OUT
punches correctly, including their PM suffixes. Existing IN meridiem errors and
an unknown OFF status remain: this is not a claim that the whole card is correct.
172 Python tests, browser retry policy checks, worker reuse/cancel/access checks,
and the production frontend build passed.
