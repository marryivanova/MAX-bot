#TODO: Итоговый список переменных, которые нужно взять из функционала нужно подставить текст

welcome_text = f"""
👋 Добро пожаловать!

"""

menu_text_consultation = """
<b> <b>

• <b>

• <b>

 <b>:</b>
"""

menu_text_core = """

"""

menu_text_balance = """
💰 <b>Мой баланс</b>

<i>Информация о ваших уроках:</i>

<u>Основные уроки:</u>
• <b>{paid_lessons}</b> — оплаченные уроки

<u>Бонусные уроки:</u>
• <b>{bonus_lessons}</b> — бонусные уроки

━━━━━━━━━━━━━━━━━━━
<b>Всего уроков: {total_lessons}</b>
"""

menu_text_lk = """

"""

menu_text_schedule = """
<b>📅 Расписание на неделю</b>

<ins>Актуальное расписание на текущую неделю</ins>

{schedule_content}

"""

menu_text_schedule_empty = """

📭 <i>Нет запланированных уроков</i>

"""

menu_text_schedule_need_form = """

⚠️ <b>Требуется заполнить данные</b>

"""

menu_text_schedule_error = """
⚠️ <b>Ошибка</b>

<i>Не удалось загрузить расписание. Попробуйте позже.</i>
"""

free_lessons_referral_first = """
<b>🎁</b>

"""

free_lessons_referral_second = """
➡️ <a href="{link}">СКОПИРОВАТЬ ССЫЛКУ</a> ⬅️
"""

free_lessons_fast_payment = """

"""
