"""
Парсер списків студентів із .docx (таблиці та абзаци наказів про зарахування).

Порівняно з початковою версією:
  * стоп-фрази для заголовків/шапок беруться з конфігурації (config.py),
    а не захардкоджені в коді — тому парсер не прив'язаний до назви
    одного конкретного навчального закладу і працює для будь-якого
    коледжу/факультету без правок коду;
  * підтримка .doc через MS Word (win32com) залишається опціональною:
    якщо пакет недоступний (Linux/macOS, або немає встановленого Word),
    користувачу одразу пояснюється, що файл треба зберегти як .docx,
    замість незрозумілого технічного винятку.
"""

import os
import re

from docx import Document


DEFAULT_STOP_PHRASES = [
    "список студентів",
    "денного відділення",
    "зараховані на курс",
]


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
        temp_docx = os.path.abspath("temp_parsed_file.docx")
        doc_win.SaveAs2(temp_docx, FileFormat=16)
        doc_win.Close()
        return temp_docx
    finally:
        word.Quit()


def parse_students_tables(file_path, stop_phrases=None):
    """
    Повертає dict: { "ГРУПА": {"study_year": ..., "curator": ..., "students": [...]}, ... }
    """
    stop_phrases = [p.lower() for p in (stop_phrases or DEFAULT_STOP_PHRASES)]

    target_path = file_path
    temp_created = False

    if file_path.lower().endswith(".doc"):
        target_path = _convert_doc_to_docx(file_path)
        temp_created = True

    try:
        doc = Document(target_path)
    except Exception as e:
        raise Exception(f"Не вдалося прочитати документ: {e}")
    finally:
        if temp_created and os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass

    groups_data = {}
    current_group = None
    current_year = "Не вказано"
    current_curator = "Не вказано"

    def process_row_cells(cells_text):
        nonlocal current_group, current_year, current_curator

        row_joined = " | ".join([c for c in cells_text if c])
        if not row_joined.strip():
            return
        row_lower = row_joined.lower()

        if any(phrase in row_lower for phrase in stop_phrases):
            return

        group_match = re.search(r"\b([А-ЯІЇЄҐA-Z]{2,4}\s*[-–]\s*\d{2})\b", row_joined)
        if group_match:
            candidate_group = re.sub(r"\s+", "", group_match.group(1).upper())
            if len(candidate_group) <= 7:
                current_group = candidate_group
                if current_group not in groups_data:
                    groups_data[current_group] = {
                        "study_year": current_year,
                        "curator": "Не вказано",
                        "students": [],
                    }

        year_match = re.search(r"(\d{4}\s*[/\-]\s*\d{4})", row_joined)
        if year_match:
            current_year = year_match.group(1).replace(" ", "")
            if current_group and groups_data[current_group]["study_year"] == "Не вказано":
                groups_data[current_group]["study_year"] = current_year

        curator_match = re.search(r"Куратор\s*:\s*([А-ЯІЇЄҐA-Zа-яіїєґ\s.]+)", row_joined, re.IGNORECASE)
        if curator_match and current_group:
            c_text = curator_match.group(1).split("|")[0].strip()
            current_curator = re.sub(r"\s+", " ", c_text).strip()
            groups_data[current_group]["curator"] = current_curator

        if not current_group:
            return

        if groups_data[current_group]["curator"] == "Не вказано" and current_curator != "Не вказано":
            groups_data[current_group]["curator"] = current_curator

        full_name = ""
        name_idx = -1
        for idx, text in enumerate(cells_text):
            if re.match(r"^\d+[.]?$", text):
                continue
            text_lower = text.lower()
            if any(phrase in text_lower for phrase in stop_phrases):
                continue
            words = re.findall(r"[А-ЯІЇЄҐа-яіїєґ]{2,}", text)
            if len(words) >= 2 and not any(kw in text_lower for kw in ["куратор", "навч", "наказ", "рік"]):
                full_name = text
                name_idx = idx
                break

        if not full_name:
            return

        full_name_clean = re.sub(r"\s*25\+\s*", " ", full_name)
        full_name_clean = re.sub(r"^\d+[.\s]+", "", full_name_clean).strip()
        full_name_clean = " ".join(full_name_clean.split())

        if any(phrase in full_name_clean.lower() for phrase in stop_phrases):
            return
        if len(full_name_clean.split()) < 2:
            return

        other_cells = [cells_text[i] for i in range(len(cells_text)) if i != name_idx and not re.match(r"^\d+[.]?$", cells_text[i])]
        combined_info = " ".join(other_cells) + " " + row_joined

        funding = "К"
        if re.search(r"\b(д\.?\s*з\.?|д\\з)\b", combined_info, re.IGNORECASE):
            funding = "ДЗ"

        notes_parts = []
        if "25+" in combined_info:
            notes_parts.append("25+")
        for tag in ["УБД", "ВПО", "сирота"]:
            if re.search(rf"\b{tag}\b", combined_info, re.IGNORECASE) and tag not in notes_parts:
                notes_parts.append(tag)
        if re.search(r"\bінв(?:алід)?\b", combined_info, re.IGNORECASE) and "інв" not in notes_parts:
            notes_parts.append("інв")

        for p in re.findall(r"(?:0\d{9})", combined_info):
            if p not in notes_parts:
                notes_parts.append(p)
        for d in re.findall(r"\b\d{2}\.\d{2}\.\d{4}\b", combined_info):
            if d not in notes_parts:
                notes_parts.append(d)

        note_str = ", ".join(notes_parts) if notes_parts else "—"

        existing_names = [s["full_name"].lower() for s in groups_data[current_group]["students"]]
        if full_name_clean.lower() not in existing_names:
            groups_data[current_group]["students"].append({
                "full_name": full_name_clean,
                "funding": funding,
                "note": note_str,
            })

    for table in doc.tables:
        for row in table.rows:
            cells_text = [re.sub(r"\s+", " ", c.text.strip()) for c in row.cells]
            process_row_cells(cells_text)

    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            process_row_cells([txt])

    return groups_data
