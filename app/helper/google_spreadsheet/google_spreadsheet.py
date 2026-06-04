from functools import wraps
from os import path
from pickle import dump, load
from socket import timeout
from time import sleep
from typing import Callable

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient import errors
from googleapiclient.discovery import build

from tokens import CREDENTIALS_FILE, PICKLE_FILE

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def wait_time_error(cls):
    """Decorate wait time error."""

    @wraps(cls)
    def wrapper(*args, **kwargs):
        try:
            instance = cls(*args, **kwargs)
            return instance
        except errors.HttpError as e:
            status = int(e.resp.get("status"))
            if status == 429:
                sleep(90)
                instance = cls(*args, **kwargs)
                return instance
        except timeout as e:
            sleep(90)
            instance = cls(*args, **kwargs)
            return instance

    return wrapper


def for_all_methods(decorator: Callable) -> Callable:
    """Decorate all methods in class."""

    @wraps(decorator)
    def decorate(cls):
        for i_method_name in dir(cls):
            if i_method_name.startswith("__") is False:
                cur_method = getattr(cls, i_method_name)
                decorate_method = decorator(cur_method)
                setattr(cls, i_method_name, decorate_method)
        return cls

    return decorate


@for_all_methods(wait_time_error)
class Spreadsheet:

    def __init__(self, spreadsheet_id, table_range):
        """
        :param spreadsheet_id:
        :param table_range:
        """
        self.pickle_file = PICKLE_FILE
        self.credentials_file = CREDENTIALS_FILE

        self.service = build("sheets", "v4", credentials=self.get_credentials())
        self.spreadsheet_id = spreadsheet_id
        self.range = table_range

    def get_credentials(self):

        creds = None

        if path.exists(self.pickle_file):
            with open(self.pickle_file, "rb") as token:
                creds = load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                creds = flow.run_local_server()

            with open(self.pickle_file, "wb") as token:
                dump(creds, token)

        return creds

    def find_rows_by_column_value(self, search_value, column_index=0, exact_match=True, case_sensitive=False):
        """
        Находит строки по значению в конкретном столбце.

        :param search_value: Значение для поиска
        :param column_index: Индекс столбца (начинается с 0)
        :param exact_match: Точное совпадение (True) или частичное (False)
        :param case_sensitive: Учитывать регистр
        :return: Список найденных строк
        """
        all_values = self.get_values()
        if not all_values:
            return []

        if not case_sensitive:
            search_value = str(search_value).lower()

        matching_rows = []
        for row in all_values:
            if len(row) > column_index:
                cell_value = row[column_index]
                cell_str = str(cell_value)
                compare_value = cell_str if case_sensitive else cell_str.lower()

                if exact_match:
                    if compare_value == search_value:
                        matching_rows.append(row)
                else:
                    if search_value in compare_value:
                        matching_rows.append(row)

        return matching_rows

    def get_values(self):

        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=self.range,
            )
            .execute()
        )

        return result.get("values", [])

    def get_sheet_titles(self):
        """Get sheet titles from spreadsheet."""
        spreadsheet_metadata = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()

        sheets = spreadsheet_metadata.get("sheets", "")
        sheet_titles = []
        for sheet in sheets:
            sheet_titles.append(sheet.get("properties", {}).get("title", ""))

        return sheet_titles
