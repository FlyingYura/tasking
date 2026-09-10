"""
Експорт даних у файли .xlsx (замість єдиного варіанту — простого текстового
дампу всіх таблиць), щоб звіт можна було одразу відкрити в Excel,
відформатувати чи роздрукувати для директора.
"""

import re
from collections import OrderedDict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def _safe_sheet_name(name, used):
    cleaned = re.sub(r"[:\\/?*\[\]]", " ", str(name or "Група")).strip() or "Група"
    cleaned = cleaned[:31]
    base = cleaned
    index = 2
    while cleaned.lower() in {item.lower() for item in used}:
        suffix = f" ({index})"
        cleaned = (base[: 31 - len(suffix)] + suffix).strip()
        index += 1
    used.add(cleaned)
    return cleaned


def _normalize_total(total):
    if isinstance(total, float) and total == int(total):
        return int(total)
    return total


def _fill_rating_sheet(ws, rating_rows, title):
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1C7ED6")
    header_align = Alignment(horizontal="center", vertical="center")
    thin = Border(
        left=Side(style="thin", color="CED4DA"),
        right=Side(style="thin", color="CED4DA"),
        top=Side(style="thin", color="CED4DA"),
        bottom=Side(style="thin", color="CED4DA"),
    )
    stripe = PatternFill("solid", fgColor="F1F3F5")

    ws.merge_cells("A1:D1")
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 22

    headers = ["Місце", "ПІБ студента", "Група", "Загалом балів"]
    ws.append([])
    ws.append(headers)
    for cell in ws[3]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin

    for idx, row in enumerate(rating_rows, 1):
        values = [idx, row["full_name"], row["group_name"], _normalize_total(row["total"])]
        ws.append(values)
        excel_row = 3 + idx
        for cell in ws[excel_row]:
            cell.border = thin
            if idx % 2 == 0:
                cell.fill = stripe
        ws.cell(excel_row, 1).alignment = Alignment(horizontal="center")
        ws.cell(excel_row, 4).alignment = Alignment(horizontal="center")

    for col, width in zip(range(1, 5), (10, 42, 16, 16)):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:D{3 + len(rating_rows)}"


def export_rating_to_xlsx(rating_rows, file_path):
    wb = Workbook()
    used = set()
    overall = wb.active
    overall.title = _safe_sheet_name("Загальний рейтинг", used)
    _fill_rating_sheet(overall, rating_rows, "Загальний рейтинг")

    by_group = OrderedDict()
    for row in rating_rows:
        by_group.setdefault(row.get("group_name") or "Без групи", []).append(row)

    for group_name, rows in by_group.items():
        sheet = wb.create_sheet(_safe_sheet_name(group_name, used))
        _fill_rating_sheet(sheet, rows, f"Рейтинг групи {group_name}")

    wb.save(file_path)


def export_group_to_xlsx(group_name, study_year, curator, students_rows, file_path):
    wb = Workbook()
    ws = wb.active
    ws.title = _safe_sheet_name(group_name, set())

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
