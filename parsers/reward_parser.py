"""
Парсер наказів про нагородження/подяки з .doc / .docx.

Студенти розпізнаються за прив'язкою до групи («… – група ЕК-11»).
Викладачі — імена без групи (2–3 слова) або з позначкою «викладач».
"""

import os
import re

from parsers.doc_io import cleanup_temp, open_word_document

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
ROLE_KEYWORDS = ["директор", "заступник", "секретар", "голова", "начальник", "проректор", "декан", "в.о."]
TEACHER_HINTS = ("викладач", "педагог", "вчител", "методист")

_NAME_GROUP = re.compile(
    r"([А-ЯІЇЄҐ][а-яіїєґ'’\-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+)?)"
    r"\s*[–-]\s*група\s*([А-ЯІЇЄҐA-Z]{2,4}\s*[-–]\s*\d{2})",
    re.IGNORECASE,
)
_NAME_ONLY = re.compile(
    r"^([А-ЯІЇЄҐ][а-яіїєґ'’\-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+)?)"
    r"(?:\s*[–-]\s*.+)?$"
)
# Розпізнавання імен у відмінковому відмінку (наприклад, "Івану БОЙЧУКУ")
_NAME_CASED = re.compile(
    r"([А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:у|ові|ю|а|я|ій|ію|єм|є|ю)\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:у|ові|ю|а|я|ій|ію|єм|є|ю)(?:\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:у|ові|ю|а|я|ій|ію|єм|є|ю))?)"
)


def _determine_level(text_lower, points_levels):
    for rule in points_levels:
        keywords = rule.get("keywords") or []
        if keywords and any(kw in text_lower for kw in keywords):
            return rule["label"], rule["points"]
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


def _collect_lines(doc):
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [re.sub(r"\s+", " ", c.text.strip()) for c in row.cells if c.text.strip()]
            if cells:
                lines.append("    ".join(cells))
    return lines


def parse_reward_order(file_path, points_levels=None, reprimand_levels=None):
    points_levels = points_levels or DEFAULT_POINTS_LEVELS
    reprimand_levels = reprimand_levels or DEFAULT_REPRIMAND_LEVELS

    doc, temp_path = open_word_document(file_path)
    try:
        lines = _collect_lines(doc)
        full_text = "\n".join(lines)
    finally:
        cleanup_temp(temp_path)

    order_num_match = re.search(r"№\s*([А-Яа-яA-Za-z0-9\-/]+)", full_text)
    order_number = order_num_match.group(1) if order_num_match else "Б/Н"
    date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", full_text)
    order_date = date_match.group(1) if date_match else "Не вказана"

    text_lower = full_text.lower()
    order_kind = _detect_order_kind(text_lower)
    levels = reprimand_levels if order_kind == "reprimand" else points_levels
    level_type, points = _determine_level(text_lower, levels)

    students = []
    teachers = []

    excluded = set()
    for idx, txt in enumerate(lines):
        if any(kw in txt.lower() for kw in ROLE_KEYWORDS):
            excluded.add(idx)
            excluded.add(idx + 1)

    def add_student(name, grp):
        name = name.strip()
        grp = re.sub(r"\s+", "", (grp or "").upper())
        if not any(s["full_name"].lower() == name.lower() and s.get("group_name") == grp for s in students):
            students.append({"full_name": name, "group_name": grp})

    def add_teacher(name):
        name = name.strip()
        if any(s["full_name"].lower() == name.lower() for s in students):
            return
        if not any(t["full_name"].lower() == name.lower() for t in teachers):
            teachers.append({"full_name": name, "group_name": None})

    for line_idx, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or line_idx in excluded:
            continue

        # Спочатку розпізнаємо студентів з групами
        for m in _NAME_GROUP.findall(line_clean):
            add_student(m[0], m[1])

        # Потім розпізнаємо викладачів (імена без групи)
        cols = re.split(r"\t{1,}| {2,}", line_clean)
        for col in cols:
            col = col.strip()
            match = _NAME_ONLY.match(col)
            if not match:
                continue
            name = match.group(1).strip()
            
            # Ігноруємо службові слова
            if any(w in col.lower() for w in ["директор", "заступник", "коледж", "наказ", "призначаю", "подяку", "доган"]):
                continue
            # Якщо є група в колонці - це вже оброблено як студент
            if "група" in col.lower():
                continue
            # Якщо ім'я вже є в студентах - пропускаємо
            if any(s["full_name"].lower() == name.lower() for s in students):
                continue
            # Додаємо як викладача
            add_teacher(name)

    return {
        "order_number": order_number,
        "order_date": order_date,
        "event_title": "—",
        "level_type": level_type,
        "points": points,
        "order_kind": order_kind,
        "students": students,
        "teachers": teachers,
    }
