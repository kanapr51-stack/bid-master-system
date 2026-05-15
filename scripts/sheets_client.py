"""
Google Sheets client using Service Account credentials.
"""

import os
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_SA_PATH = Path(__file__).parent.parent / "credentials" / "service_account.json"


def get_client() -> gspread.Client:
    """Return an authenticated gspread Client using Service Account."""
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", str(_SA_PATH))
    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    return gspread.authorize(creds)


def open_sheet(spreadsheet_id: str, worksheet_name: str | None = None) -> gspread.Worksheet:
    """
    Open a worksheet by spreadsheet ID.

    Args:
        spreadsheet_id: The ID from the Google Sheets URL
                        (https://docs.google.com/spreadsheets/d/<ID>/edit)
        worksheet_name: Sheet tab name; defaults to the first sheet if omitted.
    """
    gc = get_client()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    if worksheet_name:
        return spreadsheet.worksheet(worksheet_name)
    return spreadsheet.sheet1


# --- Quick usage example ---
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python sheets_client.py <spreadsheet_id> [worksheet_name]")
        sys.exit(1)

    sheet_id = sys.argv[1]
    sheet_name = sys.argv[2] if len(sys.argv) > 2 else None

    ws = open_sheet(sheet_id, sheet_name)
    print(f"✅ เชื่อมต่อสำเร็จ: '{ws.title}' ({ws.row_count} rows × {ws.col_count} cols)")

    rows = ws.get_all_values()
    print(f"📄 {len(rows)} แถว | ตัวอย่างแถวแรก: {rows[0] if rows else '(ว่าง)'}")
