# Developer Platform H1 Biweekly CTO Reporting

This repository now includes an automated report pipeline for the **Developer Platform OKRs & Initiatives** update that should run every 2 weeks, starting on **2026-04-10**.

## Source of truth

The report is generated from a snapshot exported from Coda:

- Required page URL:  
  `https://coda.io/d/Developer-Platform-Mission_dLGZ7ZRwER_/2026-Developer-Platforms-OKRs-Initiatives_suSYCzE2#_lusqZqZ0`

The generator validates `metadata.source_url` in the snapshot to ensure the report is based on this Coda page.

## Output

Generated report path:

- `reports/cto/okr-update-YYYY-MM-DD.md`
- `reports/cto/latest.md` (copy of the latest generated report)

The report contains:

1. Executive summary (progress + risk signal)
2. KPI snapshot table
3. Changes since last update
4. OKR health table + distribution chart
5. Initiative at-risk callouts
6. Risk profile table + exposure chart
7. Decisions required table (owner + due date)
8. Major callouts:
   - wins
   - issues
   - major structural changes from previous cycle

## Snapshot format

Update `data/coda_snapshots/current.json` every cycle (and copy prior current to `previous.json` before replacing).

Top-level structure:

```json
{
  "metadata": {
    "period": "H1 2026",
    "source_url": "https://coda.io/d/Developer-Platform-Mission_dLGZ7ZRwER_/2026-Developer-Platforms-OKRs-Initiatives_suSYCzE2#_lusqZqZ0",
    "prepared_by": "Program Manager",
    "snapshot_date": "2026-04-10"
  },
  "okrs": [],
  "initiatives": [],
  "risks": []
}
```

Field expectations:

- `okrs[]`:
  - `id`, `name`, `owner`, `status`, `progress`, `confidence`
- `initiatives[]`:
  - `id`, `name`, `okr_id`, `owner`, `status`, `progress`, `next_milestone`
  - optional decision fields:
    - `decision_required`, `decision_summary`, `decision_due`
- `risks[]`:
  - `id`, `title`, `owner`, `severity` (1-5), `likelihood` (1-5), `status`, `mitigation`
  - optional decision fields:
    - `decision_required`, `decision_summary`, `decision_due`

## Manual generation

```bash
python scripts/generate_cto_okr_report.py \
  --current data/coda_snapshots/current.json \
  --previous data/coda_snapshots/previous.json \
  --output reports/cto/okr-update-2026-04-10.md \
  --report-date 2026-04-10
```

If running off-schedule for draft/testing:

```bash
python scripts/generate_cto_okr_report.py \
  --current data/coda_snapshots/current.json \
  --previous data/coda_snapshots/previous.json \
  --output reports/cto/okr-update-draft.md \
  --report-date 2026-04-11 \
  --force
```

## Automation

GitHub Actions workflow:

- `.github/workflows/biweekly-cto-okr-report.yml`

Behavior:

- Runs every Friday on cron
- Generates report **only** when `report-date` aligns with 14-day cadence from 2026-04-10
- Commits report updates automatically when generated
- Supports manual `workflow_dispatch` with optional `report_date`
- Publishes generated report to Google Docs (when credentials are configured)

## Google Docs publishing (Option 2 - automated)

The workflow can automatically publish each generated report to Google Docs.

### One-time Google Cloud setup

1. In Google Cloud, enable APIs:
   - Google Docs API
   - Google Drive API
2. Create a Service Account and generate a JSON key.
3. Share your target Google Doc (or target Drive folder) with the service account email.
4. Add repository secrets/variables:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` (**required**): full JSON credentials content
   - `GOOGLE_DOC_ID` (optional): existing doc ID to overwrite each cycle (rolling doc mode)
   - `GOOGLE_DRIVE_FOLDER_ID` (optional): folder for newly created docs
   - `GOOGLE_DOC_SHARE_EMAILS` (optional): comma-separated readers to grant access
   - `GOOGLE_DOC_TITLE_TEMPLATE` (optional repo variable): default `Developer Platform OKR Update - {report_date}`

### Publish modes

- **Rolling single doc** (recommended for CTO bookmark):
  - Set `GOOGLE_DOC_ID`
  - Each cycle overwrites the same Google Doc with latest content
- **New doc each cycle**:
  - Leave `GOOGLE_DOC_ID` unset
  - Script creates a new Google Doc titled from template and optionally moves it to `GOOGLE_DRIVE_FOLDER_ID`

### Local/manual publish command

```bash
python3 scripts/publish_report_to_google_docs.py \
  --report-path reports/cto/okr-update-2026-04-10.md \
  --credentials-file /path/to/service-account.json \
  --report-date 2026-04-10 \
  --doc-id <existing-doc-id>
```

Or create a new doc:

```bash
python3 scripts/publish_report_to_google_docs.py \
  --report-path reports/cto/okr-update-2026-04-10.md \
  --credentials-file /path/to/service-account.json \
  --report-date 2026-04-10 \
  --folder-id <drive-folder-id>
```

## Operating cadence every 2 weeks

1. Move last cycle `current.json` to `previous.json`.
2. Export latest Coda data to `current.json`.
3. Run workflow manually (or wait for scheduled run).
4. Review generated report narrative and refine callouts before sharing with CTO.
