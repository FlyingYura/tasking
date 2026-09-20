
import os
import re

from parsers.doc_io import cleanup_temp, open_word_document

DEFAULT_POINTS_LEVELS = [
    {"keywords": ["міжнародн"], "label": "Міжнародний", "points": 3},
    {"keywords": ["обласн", "регіональн"], "label": "Обласний / Регіональний", "points": 2},
    {"keywords": [], "label": "Міський / Місцевий", "points": 1},
]


_NATIONAL_OR_INTL_KEYWORDS = ("всеукраїнськ", "міжнародн")


_PLACE_PATTERN = re.compile(
    r"(?:1|2|3|i|ii|iii)[\s\-]*(?:ше|ге|тє|е|є)?\s*місц\w*"
    r"|(?:перш|друг|трет)\w*\s*місц\w*",
    re.IGNORECASE,
)


def _determine_competition_level(text_lower):
    has_scope = any(kw in text_lower for kw in _NATIONAL_OR_INTL_KEYWORDS)
    has_place = bool(_PLACE_PATTERN.search(text_lower))
    if has_scope and has_place:
        return "Всеукраїнський/Міжнародний (1-3 місце)", 2
    if has_scope:
        return "Всеукраїнський/Міжнародний (участь)", 1
    return "Місцевий / Інші", 0.5

DEFAULT_REPRIMAND_LEVELS = [
    {"keywords": ["доган"], "label": "Догана", "points": 0.5},
]

REPRIMAND_KEYWORDS = ("доган",)
REWARD_KEYWORDS = ("подяк", "нагород")
ROLE_KEYWORDS = ["директор", "заступник", "секретар", "голова", "начальник", "проректор", "декан", "в.о."]

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


def _determine_level(text_lower, levels):
    for rule in levels:
        keywords = rule.get("keywords") or []
        if keywords and any(kw in text_lower for kw in keywords):
            return rule["label"], rule["points"]

    for rule in levels:
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


def _extract_sections_with_students(lines):
    sections = []
    current_section = None
    current_context = ""

    for line in lines:
        line_clean = line.strip()


        section_match = re.match(r"^§\s*(\d+)", line_clean)
        if section_match:

            if current_section and current_section["students"]:
                sections.append(current_section)


            section_num = section_match.group(1)
            current_section = {
                "section_num": section_num,
                "context": line_clean,
                "students": []
            }
            current_context = line_clean
        elif current_section:


            if line_clean:
                current_context += " " + line_clean
                current_section["context"] = current_context


            for m in _NAME_GROUP.findall(line_clean):
                current_section["students"].append({
                    "full_name": m[0],
                    "group_name": re.sub(r"\s+", "", (m[1] or "").upper()),
                    "section_context": current_context
                })


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


    if order_kind == "reprimand":
        level_type, points = _determine_level(text_lower, reprimand_levels)
    else:
        level_type, points = _determine_competition_level(text_lower)


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


        existing = next((s for s in students if s["full_name"].lower() == name.lower() and s.get("group_name") == grp), None)

        if existing:

            if commendation_type and commendation_type not in existing.get("commendation_types", []):
                existing.setdefault("commendation_types", []).append(commendation_type)
                existing.setdefault("commendation_points", []).append(points if commendation_points is None else commendation_points)
        else:

            student_data = {"full_name": name, "group_name": grp}
            if commendation_type:
                student_data["commendation_types"] = [commendation_type]
                student_data["commendation_points"] = [points if commendation_points is None else commendation_points]
            students.append(student_data)

    def add_teacher(name):
        name = name.strip()
        if not name or len(name.split()) < 2:
            return

        if any(admin.lower() in name.lower() or name.lower() in admin.lower() for admin in ADMIN_EXCLUSIONS):
            return
        if any(s["full_name"].lower() == name.lower() for s in students):
            return
        if not any(t["full_name"].lower() == name.lower() for t in teachers):
            teachers.append({"full_name": name, "group_name": None})


    if sections:
        for section in sections:
            section_context = section["context"].lower()
            if order_kind == "reprimand":
                section_level, section_points = _determine_level(section_context, reprimand_levels)
            else:
                section_level, section_points = _determine_competition_level(section_context)

            for student in section["students"]:
                add_student(
                    student["full_name"],
                    student["group_name"],
                    commendation_type=section_level,
                    commendation_points=section_points
                )


    for line_idx, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or line_idx in excluded:
            continue

        for m in _NAME_GROUP.findall(line_clean):
            add_student(m[0], m[1])

        cols = re.split(r"\t{1,}| {2,}", line_clean)
        for col in cols:
            col = col.strip()
            if not col or "група" in col.lower():
                continue

            names_in_col = re.findall(r"[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z'’\-]+\s+[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z'’\-]+(?:\s+[А-ЯІЇЄҐA-Z][А-ЯІЇЄҐа-яіїєґA-Za-z'’\-]+)?", col)
            for name in names_in_col:
                name = name.strip()
                if any(s["full_name"].lower() == name.lower() for s in students):
                    continue
                add_teacher(name)


    if order_kind == "reprimand":
        teachers = []

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
