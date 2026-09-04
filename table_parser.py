import os
import re
from docx import Document

def parse_students_tables(file_path):
    """
    Парсить файли зі списками студентів (.docx / .doc), коректно розрізняючи групи
    та ігноруючи службові рядки, шапки й заголовки на кшталт 'Список студентів зарахованих на II курс'.
    """
    target_path = file_path
    temp_created = False

    if file_path.lower().endswith('.doc'):
        try:
            import win32com.client as win32
            word = win32.Dispatch("Word.Application")
            word.Visible = False
            doc_win = word.Documents.Open(os.path.abspath(file_path))
            temp_docx = os.path.abspath("temp_parsed_file.docx")
            doc_win.SaveAs2(temp_docx, FileFormat=16)
            doc_win.Close()
            word.Quit()
            target_path = temp_docx
            temp_created = True
        except Exception as e:
            raise Exception(f"Помилка відкриття .doc файлу. Збережіть як .docx: {e}")

    try:
        doc = Document(target_path)
    except Exception as e:
        if temp_created and os.path.exists(target_path):
            os.remove(target_path)
        raise Exception(f"Не вдалося прочитати документ: {e}")

    groups_data = {}
    current_group = None
    current_year = "2026/2027"
    current_curator = "Не вказано"

    # Точні службові фрази виключно для шапок і кінцівок документів
    EXACT_STOP_PHRASES = [
        "список студентів", 
        "денного відділення", 
        "зараховані на ii курс", 
        "зараховані на іі курс", 
        "зараховані на 2 курс",
        "список студентів, які зараховані",
        "дрогобицький механіко-технологічний фаховий коледж"
    ]

    def process_row_cells(cells_text):
        nonlocal current_group, current_year, current_curator
        
        row_joined = " | ".join([c for c in cells_text if c])
        if not row_joined.strip():
            return

        row_lower = row_joined.lower()

        # Ігноруємо рядок, якщо він містить службові стоп-фрази
        if any(phrase in row_lower for phrase in EXACT_STOP_PHRASES):
            return

        # 1. Шукаємо назву групи (наприклад, ЕК-11, ОР-21, БО-11 тощо)
        group_match = re.search(r'\b([А-ЯІЇЄҐA-Z]{2,4}\s*[-–]\s*\d{2})\b', row_joined)
        if group_match:
            candidate_group = re.sub(r'\s+', '', group_match.group(1).upper())
            if len(candidate_group) <= 7:
                current_group = candidate_group
                if current_group not in groups_data:
                    groups_data[current_group] = {
                        "study_year": current_year,
                        "curator": "Не вказано",
                        "students": []
                    }

        # 2. Шукаємо навчальний рік
        year_match = re.search(r'(\d{4}\s*[\/\-]\s*\d{4})', row_joined)
        if year_match:
            current_year = year_match.group(1).replace(" ", "")

        # 3. Шукаємо куратора
        curator_match = re.search(r'Куратор\s*:\s*([А-ЯІЇЄҐA-Zа-яіїєґ\s\.]+)', row_joined, re.IGNORECASE)
        if curator_match and current_group:
            c_text = curator_match.group(1).split('|')[0].strip()
            c_clean = re.sub(r'\s+', ' ', c_text).strip()
            current_curator = c_clean
            groups_data[current_group]["curator"] = current_curator

        if not current_group:
            return

        if groups_data[current_group]["curator"] == "Не вказано" and current_curator != "Не вказано":
            groups_data[current_group]["curator"] = current_curator

        # 4. Шукаємо студента у клітинках
        full_name = ""
        name_idx = -1
        for idx, text in enumerate(cells_text):
            if re.match(r'^\d+[\.]?$', text):
                continue
            
            text_lower = text.lower()
            if any(phrase in text_lower for phrase in EXACT_STOP_PHRASES):
                continue

            # ПІБ має складатися мінімум з двох слів (прізвище та ім'я кирилицею)
            words = re.findall(r'[А-ЯІЇЄҐа-яіїєґ]{2,}', text)
            if len(words) >= 2:
                if not any(kw in text_lower for kw in ["куратор", "навч", "наказ", "рік"]):
                    full_name = text
                    name_idx = idx
                    break

        if not full_name:
            return

        full_name_clean = re.sub(r'\b25\+\b', '', full_name).strip()
        full_name_clean = re.sub(r'^\d+[\.\s]+', '', full_name_clean).strip()
        full_name_clean = " ".join(full_name_clean.split())

        if any(phrase in full_name_clean.lower() for phrase in EXACT_STOP_PHRASES):
            return
        if len(full_name_clean.split()) < 2:
            return

        other_cells = [cells_text[i] for i in range(len(cells_text)) if i != name_idx and not re.match(r'^\d+[\.]?$', cells_text[i])]
        combined_info = " ".join(other_cells) + " " + row_joined

        funding = "К"
        if re.search(r'\b(д\.?\s*з\.?|д\\з)\b', combined_info, re.IGNORECASE):
            funding = "ДЗ"

        notes_parts = []
        if "25+" in combined_info:
            notes_parts.append("25+")
        for tag in ["УБД", "ВПО", "сирота"]:
            if re.search(rf'\b{tag}\b', combined_info, re.IGNORECASE) and tag not in notes_parts:
                notes_parts.append(tag)
        if re.search(r'\bінв(?:алід)?\b', combined_info, re.IGNORECASE):
            if "інв" not in notes_parts:
                notes_parts.append("інв")

        phones = re.findall(r'(?:0\d{9})', combined_info)
        for p in phones:
            if p not in notes_parts:
                notes_parts.append(p)

        dates = re.findall(r'\b\d{2}\.\d{2}\.\d{4}\b', combined_info)
        for d in dates:
            if d not in notes_parts:
                notes_parts.append(d)

        note_str = ", ".join(notes_parts) if notes_parts else "—"

        existing_names = [s["full_name"].lower() for s in groups_data[current_group]["students"]]
        if full_name_clean.lower() not in existing_names:
            groups_data[current_group]["students"].append({
                "full_name": full_name_clean,
                "funding": funding,
                "note": note_str
            })

    for table in doc.tables:
        for row in table.rows:
            cells_text = [re.sub(r'\s+', ' ', c.text.strip()) for c in row.cells]
            process_row_cells(cells_text)

    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            process_row_cells([txt])

    if temp_created and os.path.exists(target_path):
        try:
            os.remove(target_path)
        except Exception:
            pass

    return groups_data