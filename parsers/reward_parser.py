"""
Парсер наказів про нагородження/подяки з .docx.

Важлива відмінність від початкової версії: раніше в коді була
захардкоджена умова, яка МОВЧКИ виключала зі списку будь-якого студента
з прізвищем "Юрчак" (`if "юрчак" in st["full_name"].lower(): continue`).
Це означало, що реальна людина систематично не отримувала б бали за
свої нагороди без жодного попередження — неприпустима поведінка для
системи обліку успішності. Цю умову повністю прибрано.

Якщо потрібно виключити когось із конкретного наказу (напр. помилково
розпізнане ім'я), це робиться вручну в інтерфейсі кнопкою "Видалити"
у таблиці розпізнаних студентів — так рішення приймає людина і видно,
що саме було видалено.

Рівні заходів і бали тепер визначаються конфігурованим списком правил
(config.points_levels), а не захардкодженими словами "міжнародн"/"обласн"
прямо в коді парсера.
"""

import os
import re

from docx import Document

DEFAULT_POINTS_LEVELS = [
    {"keywords": ["міжнародн"], "label": "Міжнародний", "points": 3},
    {"keywords": ["обласн", "регіональн"], "label": "Обласний / Регіональний", "points": 2},
    {"keywords": [], "label": "Міський / Місцевий", "points": 1},
]

DEFAULT_REPRIMAND_LEVELS = [
    {"keywords": ["доган"], "label": "Догана", "points": 0.5},
]

REPRIMAND_KEYWORDS = ("доган",)
REWARD_KEYWORDS = ("подяк", "нагород")


def _convert_doc_to_docx(file_path):
    try:
        import win32com.client as win32
    except ImportError:
        raise Exception(
            "Читання файлів .doc підтримується лише на Windows з встановленим MS Word. "
            "Будь ласка, відкрийте файл у Word і збережіть його як .docx, після чого спробуйте ще раз."
        )
    word = win32.Dispatch("Word.Application")
    word.Visible = False
    try:
        doc_win = word.Documents.Open(os.path.abspath(file_path))
        temp_docx = os.path.abspath("temp_reward_file.docx")
        doc_win.SaveAs2(temp_docx, FileFormat=16)
        doc_win.Close()
        return temp_docx
    finally:
        word.Quit()


def _determine_level(text_lower, points_levels):
    for rule in points_levels:
        keywords = rule.get("keywords") or []
        if keywords and any(kw in text_lower for kw in keywords):
            return rule["label"], rule["points"]
    # останнє правило без ключових слів вважається варіантом "за замовчуванням"
    for rule in points_levels:
        if not rule.get("keywords"):
            return rule["label"], rule["points"]
    return "Не визначено", 1


def _detect_order_kind(text_lower):
    reprimand_hits = sum(text_lower.count(kw) for kw in REPRIMAND_KEYWORDS)
    reward_hits = sum(text_lower.count(kw) for kw in REWARD_KEYWORDS)
    if reprimand_hits > 0 and reprimand_hits >= reward_hits:
        return "reprimand"
    return "reward"


def parse_reward_order(file_path, points_levels=None, reprimand_levels=None):
    points_levels = points_levels or DEFAULT_POINTS_LEVELS
    reprimand_levels = reprimand_levels or DEFAULT_REPRIMAND_LEVELS
    target_path = file_path
    temp_created = False

    if file_path.lower().endswith(".doc"):
        target_path = _convert_doc_to_docx(file_path)
        temp_created = True

    try:
        doc = Document(target_path)
        full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        raise Exception(f"Не вдалося прочитати документ: {e}")
    finally:
        if temp_created and os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass

    order_num_match = re.search(r"№\s*([А-Яа-яA-Za-z0-9\-/]+)", full_text)
    order_number = order_num_match.group(1) if order_num_match else "Б/Н"

    date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", full_text)
    order_date = date_match.group(1) if date_match else "Не вказана"

    text_lower = full_text.lower()
    order_kind = _detect_order_kind(text_lower)
    levels = reprimand_levels if order_kind == "reprimand" else points_levels
    level_type, points = _determine_level(text_lower, levels)
    event_title = "—"

    students = []
    lines = full_text.split("\n")

    # Наприкінці наказу завжди йде підписний блок: посада на одному рядку,
    # а ПІБ підписанта — або на тому ж рядку, або одразу на наступному.
    # Раніше єдиним "захистом" від потрапляння підписанта у список
    # нагороджених був хардкод конкретного прізвища ("Юрчак") — це працювало
    # лише для однієї людини і ламалось для будь-кого іншого на її посаді.
    # Тепер рядок одразу після будь-якої посадової назви (директор,
    # заступник, секретар і т.д.) вважається підписом і виключається
    # незалежно від того, чиє ім'я там стоїть.
    ROLE_KEYWORDS = ["директор", "заступник", "секретар", "голова", "начальник", "проректор", "декан", "в.о."]
    excluded_line_indices = set()
    for idx, txt in enumerate(lines):
        if any(kw in txt.lower() for kw in ROLE_KEYWORDS):
            excluded_line_indices.add(idx)
            excluded_line_indices.add(idx + 1)

    for line_idx, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or line_idx in excluded_line_indices:
            continue

        matches_with_group = re.findall(
            r"([А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ]+)?)\s*[–-]\s*група\s*([А-ЯІЇЄҐA-Z]{2,4}\s*[-–]\s*\d{2})",
            line_clean, re.IGNORECASE,
        )
        for m in matches_with_group:
            name = m[0].strip()
            grp = re.sub(r"\s+", "", m[1].upper())
            if not any(s["full_name"].lower() == name.lower() and s["group_name"] == grp for s in students):
                students.append({"full_name": name, "group_name": grp})

        cols = re.split(r"\t{1,}| {2,}", line_clean)
        for col in cols:
            col = col.strip()
            if re.match(r"^[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+$", col):
                if not any(w in col.lower() for w in ["директор", "заступник", "коледж", "наказ", "призначаю", "викладач", "подяку", "доган"]):
                    if not any(s["full_name"].lower() == col.lower() for s in students):
                        students.append({"full_name": col, "group_name": None})

    return {
        "order_number": order_number,
        "order_date": order_date,
        "event_title": event_title,
        "level_type": level_type,
        "points": points,
        "order_kind": order_kind,
        "students": students,
    }
