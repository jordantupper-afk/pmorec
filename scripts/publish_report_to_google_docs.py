#!/usr/bin/env python3
"""
Publish a generated OKR markdown report to Google Docs.

Supports two modes:
- Update an existing Google Doc (`--doc-id`)
- Create a new Google Doc when `--doc-id` is not provided
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish markdown OKR report to Google Docs."
    )
    parser.add_argument("--report-path", required=True, help="Path to markdown report.")
    parser.add_argument(
        "--credentials-file",
        required=True,
        help="Path to Google service account JSON credentials.",
    )
    parser.add_argument(
        "--report-date",
        required=True,
        help="Report date in YYYY-MM-DD (used for title).",
    )
    parser.add_argument(
        "--doc-id",
        help="Existing Google Doc ID to overwrite. If omitted, creates a new doc.",
    )
    parser.add_argument(
        "--folder-id",
        help="Optional Google Drive folder ID for new docs.",
    )
    parser.add_argument(
        "--title-template",
        default="Developer Platform OKR Update - {report_date}",
        help="Template for newly created document title.",
    )
    parser.add_argument(
        "--share-emails",
        default="",
        help="Comma-separated email list to grant reader access.",
    )
    parser.add_argument(
        "--output-link-file",
        help="Optional path to write the published Google Doc URL.",
    )
    return parser.parse_args()


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def markdown_to_google_doc_text(markdown: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Convert markdown to plain text and return style hints.
    Style hints are dictionaries with:
      - type: heading|bullet
      - start: document start index
      - end: document end index
      - level: heading level (only for heading)
    """
    style_hints: list[dict[str, Any]] = []
    output_chunks: list[str] = []
    cursor = 1  # Google Docs body content starts at index 1.
    in_code_block = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            out_line = line
        elif not in_code_block:
            heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
            bullet_match = re.match(r"^-\s+(.*)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                out_line = heading_match.group(2).strip()
                if out_line:
                    start = cursor
                    end = cursor + len(out_line)
                    style_hints.append(
                        {"type": "heading", "start": start, "end": end, "level": level}
                    )
            elif bullet_match:
                out_line = bullet_match.group(1).strip()
                if out_line:
                    start = cursor
                    end = cursor + len(out_line)
                    style_hints.append({"type": "bullet", "start": start, "end": end + 1})
            else:
                out_line = line
        else:
            out_line = line

        output_chunks.append(out_line)
        output_chunks.append("\n")
        cursor += len(out_line) + 1

    text = "".join(output_chunks)
    if not text:
        text = "\n"
    return text, style_hints


def create_clients(credentials_file: str):
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=SCOPES
    )
    docs = build("docs", "v1", credentials=credentials)
    drive = build("drive", "v3", credentials=credentials)
    return docs, drive


def clear_document(docs_service: Any, doc_id: str) -> None:
    document = docs_service.documents().get(documentId=doc_id).execute()
    body = document.get("body", {}).get("content", [])
    if not body:
        return
    end_index = body[-1].get("endIndex", 1)
    if end_index <= 2:
        return
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index - 1}}}
            ]
        },
    ).execute()


def apply_text_with_styles(
    docs_service: Any, doc_id: str, text: str, style_hints: list[dict[str, Any]]
) -> None:
    requests: list[dict[str, Any]] = [{"insertText": {"location": {"index": 1}, "text": text}}]

    for hint in style_hints:
        if hint["type"] == "heading":
            level = max(1, min(6, int(hint["level"])))
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": hint["start"], "endIndex": hint["end"]},
                        "paragraphStyle": {"namedStyleType": f"HEADING_{level}"},
                        "fields": "namedStyleType",
                    }
                }
            )
        elif hint["type"] == "bullet":
            requests.append(
                {
                    "createParagraphBullets": {
                        "range": {"startIndex": hint["start"], "endIndex": hint["end"]},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                }
            )

    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


def move_to_folder(drive_service: Any, doc_id: str, folder_id: str) -> None:
    file_meta = drive_service.files().get(fileId=doc_id, fields="parents").execute()
    previous_parents = ",".join(file_meta.get("parents", []))
    drive_service.files().update(
        fileId=doc_id,
        addParents=folder_id,
        removeParents=previous_parents,
        fields="id,parents",
    ).execute()


def share_document(drive_service: Any, doc_id: str, share_emails: str) -> None:
    emails = [e.strip() for e in share_emails.split(",") if e.strip()]
    for email in emails:
        drive_service.permissions().create(
            fileId=doc_id,
            sendNotificationEmail=False,
            body={"type": "user", "role": "reader", "emailAddress": email},
        ).execute()


def main() -> int:
    args = parse_args()
    docs_service, drive_service = create_clients(args.credentials_file)

    markdown = read_text(args.report_path)
    text, style_hints = markdown_to_google_doc_text(markdown)

    if args.doc_id:
        doc_id = args.doc_id
        clear_document(docs_service, doc_id)
    else:
        title = args.title_template.format(report_date=args.report_date)
        document = docs_service.documents().create(body={"title": title}).execute()
        doc_id = document["documentId"]
        if args.folder_id:
            move_to_folder(drive_service, doc_id, args.folder_id)

    apply_text_with_styles(docs_service, doc_id, text, style_hints)

    if args.share_emails:
        share_document(drive_service, doc_id, args.share_emails)

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"Google Doc published: {doc_url}")

    if args.output_link_file:
        with open(args.output_link_file, "w", encoding="utf-8") as f:
            f.write(doc_url + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
