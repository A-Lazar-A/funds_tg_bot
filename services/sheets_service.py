from datetime import datetime
from typing import Dict
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import GOOGLE_SHEETS_CREDENTIALS_FILE, SPREADSHEET_ID, SHEET_HEADERS

class GoogleSheetsService:
    def __init__(self):
        # Get absolute path to credentials file
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        credentials_path = os.path.join(base_dir, GOOGLE_SHEETS_CREDENTIALS_FILE)
        
        self.credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        self.service = build('sheets', 'v4', credentials=self.credentials)
        self.spreadsheet_id = SPREADSHEET_ID

    def get_current_sheet_name(self) -> str:
        """Get current month sheet name in format 'Month YYYY'."""
        return datetime.now().strftime('%B %Y')

    def ensure_sheet_exists(self, sheet_name: str) -> None:
        """Create sheet if it doesn't exist."""
        try:
            # Try to get the sheet
            self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                ranges=[sheet_name]
            ).execute()
        except Exception:
            # Create new sheet
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': sheet_name
                        }
                    }
                }]
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()

            # Add headers
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'{sheet_name}!A1:F1',
                valueInputOption='RAW',
                body={'values': [SHEET_HEADERS]}
            ).execute()

    def add_transaction(self, transaction_type: str, category: str, amount: float, source: str, comment: str = '') -> None:
        """Add a new transaction to the current month's sheet."""
        sheet_name = self.get_current_sheet_name()
        self.ensure_sheet_exists(sheet_name)

        values = [[
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            transaction_type,
            category,
            amount,
            source,
            comment
        ]]

        body = {
            'values': values
        }

        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f'{sheet_name}!A:F',
            valueInputOption='RAW',
            body=body
        ).execute()

    def get_monthly_statistics(self) -> Dict:
        """Get statistics for the current month."""
        sheet_name = self.get_current_sheet_name()
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f'{sheet_name}!A2:E'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return {
                    'total_income': 0,
                    'total_expense': 0,
                    'top_expenses': [],
                    'avg_daily_expense': 0
                }

            total_income = 0
            total_expense = 0
            expenses_by_category = {}

            for row in values:
                if len(row) >= 4:
                    try:
                        # Convert string to float, handling both comma and dot separators
                        amount_str = str(row[3]).replace(',', '.')
                        amount = float(amount_str)
                        
                        if row[1] == 'Доход':
                            total_income += amount
                        else:
                            total_expense += amount
                            category = row[2]
                            expenses_by_category[category] = expenses_by_category.get(category, 0) + amount
                    except (ValueError, TypeError) as e:
                        print(f"Error converting amount '{row[3]}': {e}")
                        continue

            # Calculate top expenses
            top_expenses = sorted(
                expenses_by_category.items(),
                key=lambda x: x[1],
                reverse=True
            )[:3]

            # Calculate average daily expense
            days_in_month = datetime.now().day
            avg_daily_expense = total_expense / days_in_month if days_in_month > 0 else 0

            return {
                'total_income': total_income,
                'total_expense': total_expense,
                'top_expenses': top_expenses,
                'avg_daily_expense': avg_daily_expense
            }

        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {
                'total_income': 0,
                'total_expense': 0,
                'top_expenses': [],
                'avg_daily_expense': 0
            } 