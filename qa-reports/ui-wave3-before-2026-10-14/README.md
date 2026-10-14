# TrustOffice App Interior — Wave 3 BEFORE (2026-10-14)

Structure & parties pages, 1440px desktop, demo data (Smith Family Trust), QA user kit.qa@trustoffice-qa.dev.

| # | Page | Route |
|---|---|---|
| 1 | Trust & Entities | /structures |
| 2 | Legal Powers | /authority |
| 3 | Beneficiaries | /beneficiaries |
| 4-6 | Trust Health + Risk + State tabs | /governance |
| 7 | Beneficiary Reports | /beneficiary-reports |

Captured via SYSTEM/scripts/to-cdp-capture.py (ephemeral Chrome CDP, real login token).
Found-and-fixed while capturing: script route builder produced `//structures` (double slash → SPA 404) when called with leading-slash routes; script now strips and settle-waits for `.page-title` instead of fixed sleep.
