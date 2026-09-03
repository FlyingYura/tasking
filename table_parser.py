import os
import re
from docx import Document

def parse_students_tables(file_path):
    """
    Парсить файл зі списками студентів (.docx або .doc).
    Повертає словник {group_name: {"year": ..., "curator": ..., "students": [...]}}
    """
    temp_created = False
    target_path = file_path

    # Якщо старий .doc — конвертуємо в тимчасовий .docx через Win32 Word
    if file_path.lower().endswith('.doc'):
        try:
            import win32com.client as win32
            word = win32.Dispatch("Word.Application")
            word.Visible = False
            doc_win = word.Documents.Open(os.path.abspath(file_path))
            temp_docx = os.path.abspath("temp_parsed_file.docx")
            doc_win.SaveAs2(temp_docx, FileFormat=16)  # 16 = wdFormatXMLDocument (.docx)
            doc_win.Close()
            word.Quit()
            target_path = temp_docx
            temp_created = True
        except Exception as e:
            raise Exception(f"Помилка відкриття .doc файлу. Будь ласка, збережіть його як .docx: {e}")

    try:
        doc = Document(target_path)
    except Exception as e:
        if temp_created and os.path.exists(target_path):
            os.remove(target_path)
        raise Exception(f"Не вдалося прочитати документ: {e}")

    groups_data = {}

    for table in doc.tables:
        if len(table.rows) < 2:
            continue

        # Зчитуємо метадані з першого рядка (шапки)
        header_text = " ".join([cell.text.replace("\n", " ").strip() for cell in table.rows[0].cells])

        # Пошук назви групи (наприклад: ЕК-11, ЕК-12, ПК-21, тощо)
        group_match = re.search(r'([А-ЯІЇЄҐA-Z]{2,4}\s*[-–]\s*\d{2})', header_text, re.IGNORECASE)
        if not group_match:
            continue
        group_name = re.sub(r'\s+', '', group_match.group(1).upper())

        # Навчальний рік (наприклад: 2026/2027)
        year_match = re.search(r'(\d{4}\s*[\/\-]\s*\d{4})', header_text)
        study_year = year_match.group(1).replace(" ", "") if year_match else "2026/2027"

        # Куратор
        curator = "Не вказано"
        curator_match = re.search(r'Куратор\s*:\s*([^,\.\n\r]+(?:\s+[А-ЯІЇЄҐA-Z][а-яіїєґa-z]+){1,2})', header_text, re.IGNORECASE)
        if curator_match:
            curator = curator_match.group(1).strip()
        else:
            # Альтернативний пошук куратора по клітинках
            for cell in table.rows[0].cells:
                if "куратор" in cell.text.lower():
                    c_clean = re.sub(r'куратор\s*:\s*', '', cell.text, flags=re.IGNORECASE).strip()
                    curator = " ".join(c_clean.split())
                    break

        students_list = []

        # Обробка рядків зі студентами
        for row in table.rows[1:]:
            cells_text = [re.sub(r'\s+', ' ', c.text.strip()) for c in row.cells]
            # Відкидаємо порожні або службові рядки
            row_combined = " ".join(cells_text).strip()
            if not row_combined or "куратор" in row_combined.lower():
                continue

            # Знаходимо ПІБ (клітинка з кириличним ім'ям щонайменше з двох слів)
            full_name = ""
            name_idx = -1
            for idx, text in enumerate(cells_text):
                # Відкидаємо порядкові номери
                if re.match(r'^\d+$', text):
                    continue
                # Шукаємо два або три слова кирилицею
                if len(re.findall(r'[А-ЯІЇЄҐа-яіїєґ]{2,}', text)) >= 2 and not any(kw in text.lower() for kw in ["д.з", "наказ", "курс"]):
                    full_name = text
                    name_idx = idx
                    break

            if not full_name:
                continue

            # Очищаємо ПІБ від поміток на кшталт "25+" або номерів
            full_name_clean = re.sub(r'\b25\+\b', '', full_name).strip()
            full_name_clean = re.sub(r'^\d+[\.\s]+', '', full_name_clean).strip()

            # Решта клітинок містять форму фінансування, телефони, дати та примітки
            other_cells = [cells_text[i] for i in range(len(cells_text)) if i != name_idx and not re.match(r'^\d+$', cells_text[i])]
            combined_info = " ".join(other_cells)

            # Визначаємо джерело фінансування
            funding = "К"  # За замовчуванням контракт, якщо не вказано ДЗ
            if re.search(r'\bд\.?\s*з\.?\b', combined_info, re.IGNORECASE):
                funding = "ДЗ"
            elif re.search(r'\bк\b', combined_info, re.IGNORECASE):
                funding = "К"

            # Збираємо примітки
            notes_parts = []

            # 1. Помітка "25+"
            if "25+" in row_combined:
                notes_parts.append("25+")

            # 2. Пільгові категорії (УБД, інв / інвалід, ВПО)
            for tag in ["УБД", "ВПО"]:
                if re.search(rf'\b{tag}\b', row_combined, re.IGNORECASE) and tag not in notes_parts:
                    notes_parts.append(tag)
            if re.search(r'\bінв(?:алід)?\b', row_combined, re.IGNORECASE):
                if "інв" not in notes_parts:
                    notes_parts.append("інв")

            # 3. Витягуємо номер телефону
            phones = re.findall(r'(?:0\d{9})', row_combined)
            for p in phones:
                if p not in notes_parts:
                    notes_parts.append(p)

            # 4. Витягуємо дати народження / наказів
            dates = re.findall(r'\b\d{2}\.\d{2}\.\d{4}\b', row_combined)
            for d in dates:
                if d not in notes_parts:
                    notes_parts.append(d)

            # 5. Номери наказів і переведень (наприклад: "II курс ПЗСО №265 від 20.08.2026")
            orders = re.findall(r'(?:[IІ]{1,3}\s+курс[^;,\n]+|Наказ\s*№?\s*\d+[^;,\n]+)', row_combined, re.IGNORECASE)
            for o in orders:
                clean_o = o.strip()
                if clean_o and clean_o not in notes_parts:
                    notes_parts.append(clean_o)

            note_str = ", ".join(notes_parts) if notes_parts else "—"

            students_list.append({
                "full_name": full_name_clean,
                "funding": funding,
                "note": note_str
            })

        if students_list:
            groups_data[group_name] = {
                "study_year": study_year,
                "curator": curator,
                "students": students_list
            }

    if temp_created and os.path.exists(target_path):
        try:
            os.remove(target_path)
        except Exception:
            pass

    return groups_data