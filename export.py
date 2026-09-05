"""
Експорт даних у файли .xlsx (замість єдиного варіанту — простого текстового
дампу всіх таблиць), щоб звіт можна було одразу відкрити в Excel,
відформатувати чи роздрукувати для директора.
"""

from openpyxl import Workbook
from openpyxl.styles import Font


def export_rating_to_xlsx(rating_rows, file_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Рейтинг"

    headers = ["Місце", "ПІБ студента", "Група", "Загалом балів"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for idx, row in enumerate(rating_rows, 1):
        ws.append([idx, row["full_name"], row["group_name"], row["total"]])

    for col, width in zip("ABCD", (8, 40, 14, 16)):
        ws.column_dimensions[col].width = width

    wb.save(file_path)


def export_group_to_xlsx(group_name, study_year, curator, students_rows, file_path):
    wb = Workbook()
    ws = wb.active
    ws.title = group_name[:31] if group_name else "Група"

    ws.append([f"Група: {group_name}", f"Навчальний рік: {study_year}", f"Куратор: {curator}"])
    ws.append([])
    headers = ["№", "ПІБ студента", "Фінансування", "Примітка"]
    ws.append(headers)
    for cell in ws[3]:
        cell.font = Font(bold=True)

    for idx, row in enumerate(students_rows, 1):
        ws.append([idx, row[1], row[2], row[3]])

    for col, width in zip("ABCD", (5, 40, 14, 30)):
        ws.column_dimensions[col].width = width

    wb.save(file_path)
