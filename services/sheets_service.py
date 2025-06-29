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

    def create_summary_charts(self):
        """Создаёт диаграммы на листе Summary: круговая по категориям, столбчатая по дням (доход/расход), круговая по источникам."""
        sheet_name = 'Summary'
        # Получить id листа
        spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
        sheet_id = None
        for s in spreadsheet['sheets']:
            if s['properties']['title'] == sheet_name:
                sheet_id = s['properties']['sheetId']
                break
        if sheet_id is None:
            return

        requests = []
        # Круговая диаграмма по расходам по категориям (D3:E)
        requests.append({
            'addChart': {
                'chart': {
                    'spec': {
                        'title': 'Расходы по категориям',
                        'pieChart': {
                            'legendPosition': 'RIGHT_LEGEND',
                            'threeDimensional': False,
                            'domain': {'sourceRange': {'sources': [{'sheetId': sheet_id, 'startRowIndex': 2, 'endRowIndex': 22, 'startColumnIndex': 3, 'endColumnIndex': 4}]}},
                            'series': {'sourceRange': {'sources': [{'sheetId': sheet_id, 'startRowIndex': 2, 'endRowIndex': 22, 'startColumnIndex': 4, 'endColumnIndex': 5}]}}
                        }
                    },
                    'position': {'overlayPosition': {'anchorCell': {'sheetId': sheet_id, 'rowIndex': 1, 'columnIndex': 8}}}
                }
            }
        })

        # Круговая диаграмма по расходам по категориям (F3:G)
        requests.append({
            'addChart': {
                'chart': {
                    'spec': {
                        'title': 'Расходы по категориям',
                        'pieChart': {
                            'legendPosition': 'RIGHT_LEGEND',
                            'threeDimensional': False,
                            'domain': {'sourceRange': {'sources': [{'sheetId': sheet_id, 'startRowIndex': 2, 'endRowIndex': 22, 'startColumnIndex': 5, 'endColumnIndex': 6}]}},
                            'series': {'sourceRange': {'sources': [{'sheetId': sheet_id, 'startRowIndex': 2, 'endRowIndex': 22, 'startColumnIndex': 6, 'endColumnIndex': 7}]}}
                        }
                    },
                    'position': {'overlayPosition': {'anchorCell': {'sheetId': sheet_id, 'rowIndex': 1, 'columnIndex': 8}}}
                }
            }
        })
       
        # Столбчатая диаграмма доход/расход по дням (H3:I и J3:K)
        requests.append({
            'addChart': {
                'chart': {
                    'spec': {
                        'title': 'Доходы и расходы по дням',
                        'basicChart': {
                            'chartType': 'COLUMN',
                            'legendPosition': 'BOTTOM_LEGEND',
                            'axis': [
                                {'position': 'BOTTOM_AXIS', 'title': 'Дата'},
                                {'position': 'LEFT_AXIS', 'title': 'Сумма'}
                            ],
                            'domains': [{
                                'domain': {'sourceRange': {'sources': [
                                    {'sheetId': sheet_id, 'startRowIndex': 3-1, 'endRowIndex': 32, 'startColumnIndex': 7, 'endColumnIndex': 8}, # H (дата)
                                ]}}
                            }],
                            'series': [
                                {'series': {'sourceRange': {'sources': [
                                    {'sheetId': sheet_id, 'startRowIndex': 3-1, 'endRowIndex': 32, 'startColumnIndex': 8, 'endColumnIndex': 9} # I (доход)
                                ]}}},
                                {'series': {'sourceRange': {'sources': [
                                    {'sheetId': sheet_id, 'startRowIndex': 3-1, 'endRowIndex': 32, 'startColumnIndex': 10, 'endColumnIndex': 11} # K (расход)
                                ]}}}
                            ],
                        }
                    },
                    'position': {'overlayPosition': {'anchorCell': {'sheetId': sheet_id, 'rowIndex': 20, 'columnIndex': 8}}}
                }
            }
        })
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={'requests': requests}
        ).execute()

    def ensure_summary_sheet(self):
        """Создаёт лист 'Summary' с формулами для метрик и таблиц, если его ещё нет."""
        sheet_name = 'Summary'
        # Проверка наличия листа
        try:
            self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                ranges=[sheet_name]
            ).execute()
            return  # Лист уже есть
        except Exception:
            pass  # Листа нет, создаём

        # Получить список всех листов (месяцев)
        spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
        month_sheets = [s['properties']['title'] for s in spreadsheet['sheets'] if s['properties']['title'] != sheet_name]

        # 1. Создать лист и получить его sheetId
        add_sheet_response = self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={'requests': [{'addSheet': {'properties': {'title': sheet_name}}}]}
        ).execute()
        sheet_id = add_sheet_response['replies'][0]['addSheet']['properties']['sheetId']

        # 2. Вставить текст "Выберите месяц:" в D1 и выпадающий список в E1
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f'{sheet_name}!D1',
            valueInputOption='USER_ENTERED',
            body={'values': [['Выберите месяц:']]}
        ).execute()

        # 3. Добавить data validation (выпадающий список) в E1
        requests = [
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 4,
                        "endColumnIndex": 5
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [{"userEnteredValue": name} for name in month_sheets]
                        },
                        "showCustomUi": True,
                        "strict": True
                    }
                }
            }
        ]
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={"requests": requests}
        ).execute()

        # Формулы с INDIRECT для выбранного месяца (E1)
        summary_values = [
            ["Общая сумма доходов", '=SUMIF(INDIRECT($E$1&"!B:B"); "Доход"; INDIRECT($E$1&"!D:D"))'],
            ["Общая сумма расходов", '=SUMIF(INDIRECT($E$1&"!B:B"); "Расход"; INDIRECT($E$1&"!D:D"))'],
            ["Баланс", "=B1-B2"],
            ["Расходы по категориям", ""],
            ["Доходы по категориям", ""],
            ["Динамика по дням", ""],
        ]
        expense_by_cat_formula = '=QUERY(INDIRECT($E$1&"!B:D"); "select C, sum(D) where B = \'Расход\' group by C label sum(D) \'Сумма\'")'
        income_by_cat_formula = '=QUERY(INDIRECT($E$1&"!B:D"); "select C, sum(D) where B = \'Доход\' group by C label sum(D) \'Сумма\'")'
        daily_expense_formula = '=QUERY(ARRAYFORMULA({INT(INDIRECT($E$1&"!A:A"))\ INDIRECT($E$1&"!B:B")\ INDIRECT($E$1&"!D:D")});"select Col1, sum(Col3) where Col2 = \'Расход\' group by Col1 order by Col1 label sum(Col3) \'Сумма\', Col1 \'Дата\'")'
        daily_income_formula = '=QUERY(ARRAYFORMULA({INT(INDIRECT($E$1&"!A:A"))\ INDIRECT($E$1&"!B:B")\ INDIRECT($E$1&"!D:D")});"select Col1, sum(Col3) where Col2 = \'Доход\' group by Col1 order by Col1 label sum(Col3) \'Сумма\', Col1 \'Дата\'")'

        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f'{sheet_name}!A1:B7',
            valueInputOption='USER_ENTERED',
            body={'values': summary_values}
        ).execute()
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f'{sheet_name}!D3',
            valueInputOption='USER_ENTERED',
            body={'values': [[expense_by_cat_formula]]}
        ).execute()
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f'{sheet_name}!F3',
            valueInputOption='USER_ENTERED',
            body={'values': [[income_by_cat_formula]]}
        ).execute()
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f'{sheet_name}!H3',
            valueInputOption='USER_ENTERED',
            body={'values': [[daily_expense_formula]]}
        ).execute()
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f'{sheet_name}!J3',
            valueInputOption='USER_ENTERED',
            body={'values': [[daily_income_formula]]}
        ).execute()

        # Применить формат даты к столбцам H и J (только дата, без времени)
        date_format_request = {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 2,  # начиная с 3-й строки (индекс 2)
                    "endRowIndex": 1000,  # на всякий случай до 1000
                    "startColumnIndex": 7,  # H
                    "endColumnIndex": 8
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "DATE"
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat"
            }
        }
        date_format_request_j = {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 2,
                    "endRowIndex": 1000,
                    "startColumnIndex": 9,  # J
                    "endColumnIndex": 10
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "DATE"
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat"
            }
        }
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={"requests": [date_format_request, date_format_request_j]}
        ).execute()

        # После вставки формул — создать диаграммы
        self.create_summary_charts() 