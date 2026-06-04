from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel

from app.bitrix.core.bitrix_send_alert import AlertNotifier
from app.bitrix.core.model import ListAlertID
from db.crud_db.get_lms_id import get_info_contact_by_phone, get_users_with_conditions


class ReportReason(BaseModel):
    max_id: Optional[str | int] = None
    phone: Optional[str | int] = None
    lms_id: Optional[str | int] = None
    reason: Optional[str] = "БД не вернули результат"

# Todo: реализовать метод и модель
class GetClientContactDto(BaseModel):
    pass

def get_client_contact(param):
    pass


class MatchMaxId:
    def __init__(self, max_id: Optional[int | str], phone: int | str) -> None:
        self.max_id = max_id
        self.phone = phone
        self.scope_report: Optional[ReportReason] = None

    @staticmethod
    def normalize_phone(phone) -> str:
        if not phone:
            return ""
        return str(phone).strip().lstrip("+").replace(" ", "").replace("-", "")

    def get_contact_lms(self):
        result = get_client_contact(
            GetClientContactDto(
                max_id=self.max_id,
            )
        )
        logger.debug(f"Результат запроса с платформы: {result}")
        return result

    def comparison_max_id_phone(self) -> bool:
        lms_result = self.get_contact_lms()
        bd_result = get_info_contact_by_phone(chat_id=str(self.max_id), phone=self.phone)
        logger.debug(f"Результат запроса с БД: {bd_result}")

        if not lms_result or not bd_result:
            self.scope_report = ReportReason(
                max_id=self.max_id, phone=self.phone, reason="LMS или БД не вернули результат"
            )
            return False

        max_id_match = str(lms_result.get("max_id")) == str(bd_result.get("max_id"))
        phone_match = self.normalize_phone(lms_result.get("phone")) == self.normalize_phone(bd_result.get("phone"))
        result = max_id_match and phone_match

        if not result:
            self.scope_report = ReportReason(
                max_id=self.max_id,
                phone=self.phone,
                lms_id=lms_result.get("lms_customer_id"),
                reason="Не соответствует, нужно поменять",
            )
        else:
            self.scope_report = ReportReason(
                max_id=self.max_id,
                phone=self.phone,
                lms_id=lms_result.get("lms_customer_id"),
                reason="Данные совпадают",
            )

        logger.debug(f"Итоговый вердикт: {result}")
        return result

    def pull_statistics(self):
        """Отправляет алерт только при несовпадении данных"""
        if not self.scope_report:
            logger.warning("Нет данных. Выполните comparison_max_id_phone() сначала")

        if "Не соответствует" in str(self.scope_report.reason):
            notifier = AlertNotifier()

            message = (
                f"⚠️ [B]Несоответствие MAX_ID в БД и LMS[/B]\n\n"
                f"📌 MAX_ID: {self.scope_report.max_id}\n"
                f"📞 Телефон: {self.scope_report.phone}\n"
                f"🆔 Customer: {self.scope_report.lms_id}/\n\n"
                f"💡 Требуется синхронизация данных"
            )

            notifier.send_to_chat(
                chat_id=ListAlertID.id_alert_developers.value, message=message, system="MatchMaxIdChecker"
            )
            logger.info(f"Алерт отправлен для max_id={self.scope_report.max_id}")

        elif "не вернули результат" in str(self.scope_report.reason):
            notifier = AlertNotifier()

            message = (
                f"[B]Ошибка проверки MAX_ID[/B]\n\n"
                f"📌 MAX_ID: {self.scope_report.max_id}\n"
                f"📞 Телефон: {self.scope_report.phone}\n"
                f"⚠️ Ошибка: {self.scope_report.reason}\n\n"
                f"💡 Проверьте доступность LMS API и БД"
            )

            notifier.send_to_chat(
                chat_id=ListAlertID.id_alert_developers.value, message=message, system="MatchMaxIdChecker"
            )
            logger.info(f"Алерт об ошибке отправлен для max_id={self.scope_report.max_id}")

    @staticmethod
    def check_multiple_users(users: List[tuple]) -> Dict[str, Any]:
        """Проверяет множество пользователей и возвращает статистику"""

        mismatches = []
        errors = []
        success = []

        for max_id, phone in users:
            checker = MatchMaxId(max_id, phone)
            result = checker.comparison_max_id_phone()

            if checker.scope_report:
                if not result:
                    if "Не соответствует" in str(checker.scope_report.reason):
                        mismatches.append(checker.scope_report)
                    else:
                        errors.append(checker.scope_report)
                else:
                    success.append(checker.scope_report)

        report = dict(
            total=len(users),
            success=len(success),
            mismatches=len(mismatches),
            errors=len(errors),
            mismatches_list=mismatches,
            errors_list=errors,
        )

        if mismatches or errors:
            message = f"""\n📊 [B]РЕЗУЛЬТАТЫ ПРОВЕРКИ MAX_ID[/B]

    ✅ Успешно: {len(success)}
    ❌ Несоответствия: {len(mismatches)}  
    ⚠️ Ошибки: {len(errors)}
    📊 Всего: {len(users)}

    """
            if mismatches:
                message += "[B]❌ Несоответствия:[/B]\n\n"
                for m in mismatches:
                    message += f"• MAX_ID: {m.max_id}, Тел: {m.phone}, 🆔 Customer: {m.lms_id}/ \n"
            if errors:
                message += (
                    "\n\n[B]⚠️ Пользователь не найден на платформе!\n"
                    "   Нужно проверить:[/B]\n\n"
                    "[B]+  Есть ли карточка на платформе у этого юзера[/B]\n"
                    "[B]+  Верно ли юзер указал номер[/B]\n\n"
                )
                for e in errors:
                    message += f"• MAX_ID: {e.max_id}, Тел: {e.phone}\n"

            notifier = AlertNotifier()
            notifier.send_to_chat(
                chat_id=ListAlertID.id_alert_for_manager.value, message=message, system="MatchMaxIdChecker"
            )

        return report


def run_pull_report(limit=2000):
    users_with_limit = get_users_with_conditions(limit=limit)

    valid_users = [(max_id, phone) for max_id, phone in users_with_limit if max_id and str(max_id).strip()]

    logger.info(f"Получено {len(users_with_limit)} записей, валидных: {len(valid_users)}")

    if valid_users:
        report = MatchMaxId.check_multiple_users(valid_users)
        return report
    else:
        logger.warning("Нет валидных пользователей для проверки")
        return None
