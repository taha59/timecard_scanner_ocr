# Timecard Scanner

Device OCR with a stateless Python cropping and calculation API.

See [DEPLOYMENT.md](DEPLOYMENT.md) for Vercel frontend + Render backend setup. No uploaded photos are persisted by the application. Server OCR is disabled by default. Model downloads require user consent. Every recognized entry requires review.

Private fixture photos are deliberately excluded from this public repository. Tests involving those photos require local fixtures.

See [MISSING_ENTRIES.md](MISSING_ENTRIES.md) for real-photo missing-punch recovery checks and remaining errors.
