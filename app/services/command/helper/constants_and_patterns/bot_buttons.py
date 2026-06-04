buttons = [[{"type": "request_contact", "text": "📱 Поделиться контактом 📱"}]]

users_response = [[{"type": "callback", "text": "Подтверждаю ✅", "payload": "/next"}]]

call_manager = [[{"type": "callback", "text": "ОК!", "payload": "/call_manager"}]]

sign_up_lesson = [
    [{"type": "callback", "text": "Записаться", "payload": "/sign_up_lesson"}],
    [{"type": "callback", "text": "🔙 Назад в главное меню", "payload": "/back_to_menu"}],
]

balance_menu_keyboard = [[{"type": "callback", "text": "🔙 Назад в главное меню", "payload": "/back_to_menu"}]]

lk_text_buttons = [[{"type": "link", "text": "Личный кабинет", "url": ""}]] #TODO: тут вставить ссылку

core_menu_keyboard = [
    [{"type": "callback", "text": "🎒 Курсы", "payload": "/directions"}],
    [{"type": "callback", "text": "👤 Личный кабинет", "payload": "/lk"}],
    [{"type": "callback", "text": "💰 Мой баланс", "payload": "/balance"}],
    [{"type": "callback", "text": "📅 Расписание", "payload": "/schedule"}],
    [{"type": "callback", "text": "🎁 Получить 2 подарок", "payload": "/free_lessons"}],
]

# TODO: тут нужно добавть внопки в меню с командами
buttons_choice = [
    [{"type": "callback", "text": "📞 Получить консультацию менеджера", "payload": "/consultation"}],
    [{"type": "callback", "text": "✅ Обучаюсь в вашей школе", "payload": "/student"}],
]

buttons_direction = [
    [{"type": "callback", "text": "🔙 Назад в главное меню", "payload": "/back_to_menu"}],
]

buttons_direction_programming = [
    [{"type": "callback", "text": "🔙 Назад в главное меню", "payload": "/back_to_menu"}],
]

buttons_direction_rep = [
    [{"type": "callback", "text": "🔙 Назад в главное меню", "payload": "/back_to_menu"}],
]

buttons_direction_design = []
