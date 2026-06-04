from loguru import logger



def get_balance_lesson(lms_id):
    """Получение баланса уроков пользователя"""
    logger.info(f"Start Balance for lms_id: {lms_id}")

    lms_customer = [] #TODO: взять с апи или БД данные
    logger.debug(f"get lms customer = {lms_customer}")

    if not lms_customer:
        logger.error(f"LMS customer not found for id: {lms_id}")
        return dict(paid_lessons=0, bonus_lessons=0, total_lessons=0)

    bonus_lessons = lms_customer.get("bonus_balance", 0)
    lessons = lms_customer.get("balance_lessons", 0)

    return dict(paid_lessons=lessons, bonus_lessons=bonus_lessons, total_lessons=lessons + bonus_lessons)
