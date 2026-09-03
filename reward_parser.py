import os
import re
from docx import Document

def parse_reward_order(file_path):
    target_path = file_path
    temp_created = False

    if file_path.lower().endswith('.doc'):
        try:
            import win32com.client as win32
            word = win32.Dispatch("Word.Application")
            word.Visible = False
            doc_win = word.Documents.Open(os.path.abspath(file_path))
            temp_docx = os.path.abspath("temp_reward_file.docx")
            doc_win.SaveAs2(temp_docx, FileFormat=16)
            doc_win.Close()
            word.Quit()
            target_path = temp_docx
            temp_created = True
        except Exception as e:
            raise Exception(f"Помилка відкриття .doc файлу: {e}")

    try:
        doc = Document(target_path)
        full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        if temp_created and os.path.exists(target_path):
            os.remove(target_path)
        raise Exception(f"Не вдалося прочитати документ: {e}")

    if temp_created and os.path.exists(target_path):
        try:
            os.remove(target_path)
        except Exception:
            pass

    order_num_match = re.search(r'№\s*([А-Яа-яA-Za-z0-9\-/]+)', full_text)
    order_number = order_num_match.group(1) if order_num_match else "Б/Н"

    date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', full_text)
    order_date = date_match.group(1) if date_match else "Не вказана"

    text_lower = full_text.lower()
    if any(w in text_lower for w in ["міжнародн"]):
        level_type = "Міжнародний"
        points = 3
    elif any(w in text_lower for w in ["обласн", "регіональн"]):
        level_type = "Обласний / Регіональний"
        points = 2
    else:
        level_type = "Міський / Місцевий"
        points = 1

    event_title = "Подяка за активну участь"
    for p in doc.paragraphs:
        txt = p.text.strip()
        if "про підсумки" in txt.lower() or "свята" in txt.lower() or "конкурс" in txt.lower() or "наук" in txt.lower():
            event_title = txt
            break

    students = []
    lines = full_text.split('\n')
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # 1. Шукаємо рядки виду: "ВАЙДІ Юліані – група ДЗ-21"
        matches_with_group = re.findall(r'([А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+(?:\s+[А-ЯІЇЄҐ][а-яіїєґ]+)?)\s*[\–\-]\s*група\s*([А-ЯІЇЄҐA-Z]{2,4}\s*[-–]\s*\d{2})', line_clean, re.IGNORECASE)
        for m in matches_with_group:
            name = m[0].strip()
            grp = re.sub(r'\s+', '', m[1].upper())
            if not any(s['full_name'].lower() == name.lower() and s['group_name'] == grp for s in students):
                students.append({"full_name": name, "group_name": grp})

        # 2. Розбиваємо рядки на колонки (для списків типу Івану БОЙЧУКУ / Назару ТКАЧУ)
        cols = re.split(r'\t{1,}| {2,}', line_clean)
        for col in cols:
            col = col.strip()
            # Шукаємо імена з двох слів у давальному/інших відмінках
            if re.match(r'^[А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐ][а-яіїєґ]+$', col):
                if not any(w in col.lower() for w in ["директор", "заступник", "коледж", "наказ", "призначаю", "викладач", "подяку"]):
                    if not any(s['full_name'].lower() == col.lower() for s in students):
                        students.append({"full_name": col, "group_name": None})

    return {
        "order_number": order_number,
        "order_date": order_date,
        "event_title": event_title,
        "level_type": level_type,
        "points": points,
        "students": students
    }