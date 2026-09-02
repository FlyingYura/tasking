import os
import re
from docx import Document

def parse_order_file(file_path):
    """Зчитує файл наказу, визначає рівень і бали для кожного окремого блоку без пропуску повторюваних імен."""
    full_text = ""
    
    # 1. Читання файлу (.docx або .doc через win32com)
    if file_path.lower().endswith('.docx'):
        try:
            doc = Document(file_path)
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception as e:
            raise Exception(f"Не вдалося прочитати .docx файл: {e}")
            
    elif file_path.lower().endswith('.doc'):
        text_extracted = False
        try:
            import win32com.client as win32
            word = win32.Dispatch("Word.Application")
            word.Visible = False
            doc_win = word.Documents.Open(os.path.abspath(file_path))
            paragraphs_text = [p.Range.Text.strip() for p in doc_win.Paragraphs if p.Range.Text.strip()]
            full_text = "\n".join(paragraphs_text)
            doc_win.Close()
            word.Quit()
            text_extracted = True
        except Exception:
            pass
            
        if not text_extracted:
            try:
                doc = Document(file_path)
                full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            except Exception:
                raise Exception(
                    "Не вдалося прочитати .doc файл напряму. Будь ласка, відкрийте його у Word "
                    "і збережіть як документ Word (.docx)."
                )
    else:
        try:
            doc = Document(file_path)
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception as e:
            raise Exception(f"Непідтримуваний формат файлу: {e}")

    # 2. Пошук номера наказу
    order_num_match = re.search(r'(?:наказ|№|N)\s*([№N]?\s*[А-Яа-яA-Za-z0-9\-/]+)', full_text, re.IGNORECASE)
    order_number = order_num_match.group(1).replace('№', '').strip() if order_num_match else "Б/Н"

    # 3. Пошук дати наказу
    date_match = re.search(r'(?:від|от)\s+(\d{1,2}[\.,\s]+[а-яА-Я]+\s+\d{4}|\d{2}\.\d{2}\.\d{4})', full_text, re.IGNORECASE)
    order_date = date_match.group(1) if date_match else "Не вказано"

    # 4. Загальний рівень для інформаційної панелі
    text_lower = full_text.lower()
    if "міжнародн" in text_lower:
        overall_level = "Міжнародний / Змішаний"
        overall_points = 3
    elif "обласн" in text_lower:
        overall_level = "Обласний"
        overall_points = 2
    else:
        overall_level = "Місцевий (по коледжу)"
        overall_points = 1

    # Назва заходу
    event_name = "Участь у заході / конкурсі"
    for line in full_text.split('\n'):
        line_clean = line.strip()
        if any(kw in line_clean.lower() for kw in ["конкурс", "змагань", "олімпіад", "акредитації", "представництво"]):
            event_name = line_clean
            break

    # 5. Поблочний збір студентів (без фільтрації дублікатів, щоб усі згадки та номінації враховувалися)
    students = []
    lines = full_text.split('\n')
    
    current_points = 1  # За замовчуванням місцевий рівень (1 бал)

    for line in lines:
        line = line.strip()
        if not line:
            continue

        line_lower = line.lower()

        # Динамічно визначаємо бали для поточного блоку тексту
        if any(kw in line_lower for kw in ["прошу оголосити подяку", "подяку студентам", "службове подання"]):
            if "міжнародн" in line_lower:
                current_points = 3
            elif "обласн" in line_lower:
                current_points = 2
            elif any(acc_kw in line_lower for acc_kw in ["акредитації", "представництво", "гідне", "по коледжу"]):
                current_points = 1

        # Шукаємо рядок зі студентом: Ім'я Прізвище (Група)
        match = re.search(r'([А-ЯІЇЄҐ][а-яіїєґ]+\s+[А-ЯІЇЄҐA-Za-zІЇЄҐа-яіїєґ\.\-]+)\s*\(([^)]+)\)', line)
        if match:
            full_name = match.group(1).strip()
            group_name = match.group(2).strip()
            
            # Фільтруємо хибні спрацьовування
            if len(group_name) < 10 and not any(w in group_name.lower() for w in ["м.", "обл", "україна", "номінац", "інженерія"]):
                students.append({
                    "full_name": full_name,
                    "group_name": group_name,
                    "points": current_points  # 3 бали для міжнародного блоку, 1 бал для акредитації
                })

    return {
        "order_number": order_number,
        "order_date": order_date,
        "level": overall_level,
        "event_name": event_name,
        "points": overall_points,
        "students": students
    }