from typing import Any, Dict, List

from loguru import logger

from app.helper.google_spreadsheet.google_id import SpreadsheetID
from app.helper.google_spreadsheet.google_spreadsheet import Spreadsheet


class GoogleGetPatternMessage:
    def __init__(self, search_value):
        self.search_value = search_value

    def get_pattern_message(self, sheet_name="Шаблоны сообщений Twilio"):
        """
        Получает шаблон сообщения по ID.

        :param sheet_name: Название листа в таблице
        :return: Текст шаблона сообщения или None
        """
        spreadsheet = Spreadsheet(
            spreadsheet_id=SpreadsheetID.TABLE_TWILIO.value,
            table_range=sheet_name,
        )

        logger.info(f"Ищем шаблон с ID: '{self.search_value}' в листе '{sheet_name}'")

        results = spreadsheet.find_rows_by_column_value(
            search_value=self.search_value,
            column_index=1,
            exact_match=True,
            case_sensitive=False,
        )

        if results:
            logger.debug(f"Найдено {len(results)} совпадение(ий)")
            logger.debug(f"Первая найденная строка: {results[0]}")

            if len(results[0]) > 2:
                pattern_message = results[0][3]
                logger.success(f"Найден шаблон для ID '{self.search_value}': {pattern_message[:50]}...")
                return pattern_message
            else:
                logger.warning(f"Найдена строка, но недостаточно колонок: {results[0]}")
                return None
        else:
            logger.warning(f"Шаблон с ID '{self.search_value}' не найден")
            return None

    def get_pattern_message_full(self, sheet_name="Шаблоны сообщений Twilio") -> List[Dict[str, Any]]:
        """
        Получает полные данные шаблона(ов) сообщения по ID.

        :param sheet_name: Название листа в таблице
        :return: Список словарей с данными шаблонов
        """
        spreadsheet = Spreadsheet(
            spreadsheet_id=SpreadsheetID.TABLE_TWILIO.value,
            table_range=sheet_name,
        )

        logger.info(f"Ищем шаблон с ID: '{self.search_value}' в листе '{sheet_name}'")

        results = spreadsheet.find_rows_by_column_value(
            search_value=self.search_value,
            column_index=1,
            exact_match=True,
            case_sensitive=False,
        )

        templates = []

        if results:
            logger.debug(f"Найдено {len(results)} совпадение(ий)")

            for row in results:
                logger.debug(f"Найденная строка: {row}")

                if len(row) >= 4:
                    template = dict(
                        АМ=row[0] if len(row) > 0 else "",
                        sid=row[1] if len(row) > 1 else "",
                        Источник=row[2] if len(row) > 2 else "",
                        текст=row[3] if len(row) > 3 else "",
                        место_использования=row[4] if len(row) > 4 else "",
                    )
                    templates.append(template)
                    logger.success(f"Найден шаблон для ID '{self.search_value}': {template['текст'][:50]}...")
                else:
                    logger.warning(f"Найдена строка, но недостаточно колонок: {row}")

            logger.info(f"Всего найдено шаблонов: {len(templates)}")
            return templates
        else:
            logger.warning(f"Шаблон с ID '{self.search_value}' не найден")
            return []

    def get_all_rows(self, sheet_name="Шаблоны сообщений Twilio"):
        """Получить все строки из таблицы"""
        spreadsheet = Spreadsheet(
            spreadsheet_id=SpreadsheetID.TABLE_TWILIO.value,
            table_range=sheet_name,
        )
        results = spreadsheet.get_values()
        return results
