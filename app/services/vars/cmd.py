from enum import Enum


class CmdType(str, Enum):
    start = "/start"
    menu = "/menu"
    balance = "/balance"
    lk = "/lk"
    consultation = "/consultation"
    student = "/student"
    back_to_menu = "/back_to_menu"
    next = "/next"
    directions = "/directions"
    schedule = "/schedule"
    free_lessons = "/free_lessons"
