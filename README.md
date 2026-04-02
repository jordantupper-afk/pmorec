# pmorec

Automated biweekly reporting for Developer Platform OKRs and initiatives.

## Included workflow

- `scripts/generate_cto_okr_report.py` - generates a CTO-ready markdown update.
- `scripts/publish_report_to_google_docs.py` - publishes generated report to Google Docs.
- `.github/workflows/biweekly-cto-okr-report.yml` - scheduled GitHub Action.
- `docs/cto-biweekly-okr-reporting.md` - operating guide and data contract.

## Quick start

```bash
python3 scripts/generate_cto_okr_report.py \
  --current data/coda_snapshots/current.json \
  --previous data/coda_snapshots/previous.json \
  --output reports/cto/okr-update-2026-04-10.md \
  --report-date 2026-04-10
```
