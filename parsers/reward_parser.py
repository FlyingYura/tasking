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
# Конкретні адміністратори, яких потрібно виключити з обробки
ADMIN_EXCLUSIONS = [
    "Богдан ЗВІР",
    "Ірина Юрчак"
]
TEACHER_HINTS = ("викладач", "педагог", "вчител", "методист")

_NAME_GROUP = re.compile(
    r"([А-ЯІЇЄҐ][а-яіїєґ'’\-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+)?)"
    r"\s*[–-]\s*група\s*([А-ЯІЇЄҐA-Z]{2,4}\s*[-–]\s*\d{2})",
    re.IGNORECASE,
)
# Патерн для розпізнавання імен у відмінковому відмінку (наприклад, "Івану БОЙЧУКУ")
_NAME_CASED = re.compile(
    r"([А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:у|ові|ю|а|я|ій|ію|єм|є|й|ів|ь)\s+" +
    r"[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:у|ові|ю|а|я|ій|ію|єм|є|й|ів|ь|ьій|ій|а|у|і|ю|и|ої|е|ої)(?:\s+" +
    r"[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:у|ові|ю|а|я|ій|ію|єм|є|й|ів|ь|ій|ій|а|у|і|ю|и|ої|е|ої)?)?"
)
_NAME_ONLY = re.compile(
    r"^([А-ЯІЇЄҐ][а-яіїєґ'’\-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+)?)"
    r"(?:\s*[–-]\s*.+)?$"
)
# Покращений патерн для виявлення імен викладачів (більш гнучкий)
_TEACHER_NAME = re.compile(
    r"([А-ЯІЇЄҐ][а-яіїєґ'’\-]+\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+)?)"
)
# Розпізнавання імен у відмінковому відмінку (наприклад, "Івану БОЙЧУКУ")
_NAME_CASED = re.compile(
    r"([А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:у|ові|ю|а|я|ій|ію|єм|є|й|ів)\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:у|ові|ю|а|я|ій|ію|єм|є|й|ів|ь)(?:\s+[А-ЯІЇЄҐ][а-яіїєґ'’\-]+(?:у|ові|ю|а|я|ій|ію|єм|є|й|ів|ь|ій|ій|а|у|і|ю|и|ої|е|ої))?)"
)


def _normalize_name_from_case(name):
    """Нормалізує ім'я з відмінкового відмінка в називний.
    Примітка: Це спрощена нормалізація, для точнішої роботи потрібен морфологічний аналізатор."""
    if not name:
        return None
    
    # Спрощена нормалізація - просто повертаємо ім'я без змін для парсингу
    # Справжня нормалізація вимагає морфологічного аналізатора
    # Для now просто повертаємо ім'я як є, оскільки база даних може мати варіативні форми
    return name


def _determine_level(text_lower, points_levels):
    """Визначає рівень подяки на основі тексту секції."""
    # Перевіряємо, чи є згадка про міжнародний/всеукраїнський рівень
    has_international = any(kw in text_lower for kw in ["міжнародн", "міжнарод"])
    has_national = any(kw in text_lower for kw in ["всеукраїнськ", "всеукраїн"])
    
    # Перевіряємо, чи є зайняті місця (1, 2, 3 або I, II, III)
    has_place = any(kw in text_lower for kw in ["перше місце", "друге місце", "третє місце", 
                                                   "1 місце", "2 місце", "3 місце",
                                                   "i місце", "ii місце", "iii місце",
                                                   "i-ше місце", "ii-ге місце", "iii-тє місце"])
    
    if has_international or has_national:
        if has_place:
            return "Міжнародний/Всеукраїнський (1-3 місце)", 2
        else:
            return "Міжнародний/Всеукраїнський (участь)", 1
    else:
        # Місцевий рівень - 0.5 балів
        return "Місцевий", 0.5


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


def _extract_sections_with_students(lines):
    """Витягує секції (§1, §2, 1., 2., etc.) та студентів у кожній секції з їх контекстом."""
    sections = []
    current_section = None
    current_context = ""
    
    for line in lines:
        line_clean = line.strip()
        
        # Виявляємо початок нової секції (§1, §2 або 1., 2., etc.)
        section_match = re.match(r"^§?(\d+)[\.\)]", line_clean)
        if section_match:
            # Зберігаємо попередню секцію
            if current_section and current_section["students"]:
                sections.append(current_section)
            
            # Починаємо нову секцію
            section_num = section_match.group(1)
            current_section = {
                "section_num": section_num,
                "context": line_clean,
                "students": []
            }
            current_context = line_clean
        elif current_section:
            # Додаємо контекст до поточної секції
            if line_clean and not re.match(r"^§?\d+[\.\)]", line_clean):
                current_context += " " + line_clean
                current_section["context"] = current_context
            
            # Шукаємо студентів у рядку
            for m in _NAME_GROUP.findall(line_clean):
                current_section["students"].append({
                    "full_name": m[0],
                    "group_name": re.sub(r"\s+", "", (m[1] or "").upper()),
                    "section_context": current_context
                })
    
    # Додаємо останню секцію
    if current_section and current_section["students"]:
        sections.append(current_section)
    
    return sections


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
    
    # Визначаємо загальний рівень наказу
    level_type, points = _determine_level(text_lower, levels)

    # Витягуємо секції з індивідуальними контекстами
    sections = _extract_sections_with_students(lines)
    
    students = []
    teachers = []

    excluded = set()
    for idx, txt in enumerate(lines):
        if any(kw in txt.lower() for kw in ROLE_KEYWORDS):
            excluded.add(idx)
            excluded.add(idx + 1)

    def add_student(name, grp, commendation_type=None, commendation_points=None):
        name = name.strip()
        grp = re.sub(r"\s+", "", (grp or "").upper())
        
        # Перевіряємо, чи студент вже є в списку
        existing = next((s for s in students if s["full_name"].lower() == name.lower() and s.get("group_name") == grp), None)
        
        if existing:
            # Якщо студент вже є, додаємо новий тип подяки
            if commendation_type and commendation_type not in existing.get("commendation_types", []):
                existing.setdefault("commendation_types", []).append(commendation_type)
                existing.setdefault("commendation_points", []).append(commendation_points or points)
        else:
            # Додаємо нового студента
            student_data = {"full_name": name, "group_name": grp}
            if commendation_type:
                student_data["commendation_types"] = [commendation_type]
                student_data["commendation_points"] = [commendation_points or points]
            students.append(student_data)

    def add_teacher(name):
        name = name.strip()
        if not name or len(name.split()) < 2:
            return
        # Перевіряємо, чи це не адміністратор
        if any(admin.lower() in name.lower() or name.lower() in admin.lower() for admin in ADMIN_EXCLUSIONS):
            return
        if any(s["full_name"].lower() == name.lower() for s in students):
            return
        if not any(t["full_name"].lower() == name.lower() for t in teachers):
            teachers.append({"full_name": name, "group_name": None})

    # Обробляємо секції з індивідуальними рівнями
    if sections and order_kind != "reprimand":
        for section in sections:
            section_context = section["context"].lower()
            # Визначаємо рівень для цієї секції
            section_level, section_points = _determine_level(section_context, levels)
            
            for student in section["students"]:
                add_student(
                    student["full_name"], 
                    student["group_name"],
                    commendation_type=section_level,
                    commendation_points=section_points
                )
    else:
        # Якщо немає секцій або це догана - використовуємо розширений метод для студентів
        for line_idx, line in enumerate(lines):
            line_clean = line.strip()
            if not line_clean or line_idx in excluded:
                continue

            # Спочатку розпізнаємо студентів з групами
            for m in _NAME_GROUP.findall(line_clean):
                add_student(m[0], m[1])
            
            # Додатково шукаємо імена без групи, але які можуть бути студентами
            # Розбиваємо рядок на колонки
            cols = re.split(r"\t{1,}| {2,}", line_clean)
            for col in cols:
                col = col.strip()
                if not col or "група" in col.lower():
                    continue
                
                # Шукаємо імена в колонці (більш гнучкий патерн)
                names_in_col = re.findall(r"[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z'’\-]+\s+[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z'’\-]+(?:\s+[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z'’\-]+)?", col)
                for name in names_in_col:
                    name = name.strip()
                    # Якщо ім'я вже є в студентах - пропускаємо
                    if any(s["full_name"].lower() == name.lower() for s in students):
                        continue
                    # Додаємо як студента без групи
                    add_student(name, "Невідомо")

    # Обробляємо викладачів окремо для всіх рядків (тільки для подяк, не для доган)
    if order_kind != "reprimand":
        for line_idx, line in enumerate(lines):
            line_clean = line.strip()
            if not line_clean or line_idx in excluded:
                continue

            # Розбиваємо рядок на колонки по табах і подвійних пробілах
            cols = re.split(r"\t{1,}| {2,}", line_clean)
            
            for col in cols:
                col = col.strip()
                if not col:
                    continue
                
                # Якщо є група в колонці - це вже оброблено як студент
                if "група" in col.lower():
                    continue
                
                # Шукаємо імена в колонці з більш гнучким патерном
                names_in_col = re.findall(r"[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z'’\-]+\s+[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z'’\-]+(?:\s+[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z'’\-]+)?", col)
                
                for name in names_in_col:
                    name = name.strip()
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
