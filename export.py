"""
Експорт даних у файли .xlsx, щоб звіт можна було одразу відкрити в Excel,
відформатувати чи роздрукувати для директора.
"""

import re
from collections import OrderedDict, defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from scoring import format_achievement_line


_UKR_LETTERS = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"


def name_sort_key(name):
    """Алфавітний ключ з урахуванням української «і/ї/є/ґ», а не коду Unicode."""
    keys = []
    for ch in (name or "").casefold():
        pos = _UKR_LETTERS.find(ch)
        keys.append((0, pos) if pos >= 0 else (1, ch))
    return keys


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
    try:
        number = float(total)
    except (TypeError, ValueError):
        return total
    if number == int(number):
        return int(number)
    return number


def _style_header_row(ws, row_idx, col_count):
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1C7ED6")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Border(
        left=Side(style="thin", color="CED4DA"),
        right=Side(style="thin", color="CED4DA"),
        top=Side(style="thin", color="CED4DA"),
        bottom=Side(style="thin", color="CED4DA"),
    )
    for col in range(1, col_count + 1):
        cell = ws.cell(row_idx, col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin
    return thin


def _attach_details(rating_rows, detail_rows):
    by_id = defaultdict(list)
    by_name = defaultdict(list)
    for item in detail_rows or []:
        if item.get("student_id") is not None:
            by_id[item["student_id"]].append(item)
        by_name[(item.get("full_name"), item.get("group_name"))].append(item)

    enriched = []
    for row in rating_rows:
        details = []
        if row.get("student_id") is not None:
            details = by_id.get(row["student_id"]) or []
        if not details:
            details = by_name.get((row.get("full_name"), row.get("group_name"))) or []
        copy = dict(row)
        copy["details"] = details
        copy["details_text"] = "; ".join(format_achievement_line(item) for item in details) or "—"
        enriched.append(copy)
    return enriched


def _fill_student_sheet(ws, title, headers, rows, numbered=True):
    thin = Border(
        left=Side(style="thin", color="CED4DA"),
        right=Side(style="thin", color="CED4DA"),
        top=Side(style="thin", color="CED4DA"),
        bottom=Side(style="thin", color="CED4DA"),
    )
    stripe = PatternFill("solid", fgColor="F1F3F5")
    wrap = Alignment(wrap_text=True, vertical="center")

    last_col = get_column_letter(len(headers))
    ws.merge_cells(f"A1:{last_col}1")
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 22
    ws.append([])
    ws.append(headers)
    _style_header_row(ws, 3, len(headers))

    for idx, row in enumerate(rows, 1):
        values = []
        if numbered:
            values.append(idx)
        values.extend([
            row["full_name"],
            row["group_name"],
            _normalize_total(row["total"]),
            row.get("details_text") or "—",
        ])
        ws.append(values)
        excel_row = 3 + idx
        for cell in ws[excel_row]:
            cell.border = thin
            cell.alignment = wrap
            if idx % 2 == 0:
                cell.fill = stripe
        ws.row_dimensions[excel_row].height = 36

    widths = (8, 36, 14, 14, 70) if numbered else (36, 14, 14, 70)
    for col, width in zip(range(1, len(headers) + 1), widths):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A4"
    if rows:
        ws.auto_filter.ref = f"A3:{last_col}{3 + len(rows)}"


def _fill_details_sheet(ws, detail_rows):
    headers = ["ПІБ студента", "Група", "Номер наказу", "Дата", "Рівень", "Бали", "Файл наказу"]
    ws.merge_cells("A1:G1")
    ws["A1"] = "Деталі нарахувань: кожен рядок — одна подяка або догана"
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(headers)
    thin = _style_header_row(ws, 3, len(headers))
    stripe = PatternFill("solid", fgColor="F1F3F5")
    wrap = Alignment(wrap_text=True, vertical="center")

    for idx, item in enumerate(detail_rows or [], 1):
        ws.append([
            item.get("full_name"),
            item.get("group_name"),
            item.get("order_number"),
            item.get("order_date"),
            item.get("level_type"),
            _normalize_total(item.get("points")),
            item.get("source_filename") or "—",
        ])
        excel_row = 3 + idx
        for cell in ws[excel_row]:
            cell.border = thin
            cell.alignment = wrap
            if idx % 2 == 0:
                cell.fill = stripe

    for col, width in zip(range(1, 8), (36, 14, 16, 14, 22, 10, 32)):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A4"
    if detail_rows:
        ws.auto_filter.ref = f"A3:G{3 + len(detail_rows)}"


def export_rating_to_xlsx(rating_rows, file_path, detail_rows=None):
    rows = _attach_details(rating_rows, detail_rows)
    overall_rows = sorted(
        rows,
        key=lambda r: (-float(r.get("total") or 0), name_sort_key(r.get("full_name"))),
    )
    wb = Workbook()
    used = set()
    overall = wb.active
    overall.title = _safe_sheet_name("Загальний рейтинг", used)
    _fill_student_sheet(
        overall,
        "Загальний рейтинг",
        ["Місце", "ПІБ студента", "Група", "Загалом балів", "Накази"],
        overall_rows,
        numbered=True,
    )

    by_group = OrderedDict()
    for row in rows:
        by_group.setdefault(row.get("group_name") or "Без групи", []).append(row)

    for group_name, group_rows in by_group.items():
        alpha = sorted(group_rows, key=lambda r: name_sort_key(r.get("full_name")))
        sheet = wb.create_sheet(_safe_sheet_name(group_name, used))
        _fill_student_sheet(
            sheet,
            f"Група {group_name}",
            ["№", "ПІБ студента", "Група", "Загалом балів", "Накази"],
            alpha,
            numbered=True,
        )

    details = wb.create_sheet(_safe_sheet_name("Деталі нарахувань", used))
    _fill_details_sheet(details, detail_rows or [])

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


def export_teacher_rewards_to_xlsx(stats_rows, file_path, detail_rows=None):
    """Експорт подяок викладачів у Excel."""
    rows = _attach_teacher_details(stats_rows, detail_rows)
    wb = Workbook()
    used = set()
    overall = wb.active
    overall.title = _safe_sheet_name("Подяки викладачів", used)

    headers = ["№", "ПІБ викладача", "Посада", "Кількість подяк", "Накази"]
    _fill_teacher_sheet(overall, "Подяки викладачів", headers, rows, numbered=True)

    wb.save(file_path)


def _attach_teacher_details(stats_rows, detail_rows):
    by_id = defaultdict(list)
    for item in detail_rows or []:
        if item.get("teacher_id") is not None:
            by_id[item["teacher_id"]].append(item)

    enriched = []
    for row in stats_rows:
        details = []
        if row.get("teacher_id") is not None:
            details = by_id.get(row["teacher_id"]) or []
        copy = dict(row)
        copy["details"] = details
        copy["details_text"] = "; ".join(f"№{item['order_number']} від {item['order_date']}" for item in details) or "—"
        enriched.append(copy)
    return enriched


def _fill_teacher_sheet(ws, title, headers, rows, numbered=True):
    thin = Border(
        left=Side(style="thin", color="CED4DA"),
        right=Side(style="thin", color="CED4DA"),
        top=Side(style="thin", color="CED4DA"),
        bottom=Side(style="thin", color="CED4DA"),
    )
    stripe = PatternFill("solid", fgColor="F1F3F5")
    wrap = Alignment(wrap_text=True, vertical="center")

    last_col = get_column_letter(len(headers))
    ws.merge_cells(f"A1:{last_col}1")
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 22
    ws.append([])
    ws.append(headers)
    _style_header_row(ws, 3, len(headers))

    for idx, row in enumerate(rows, 1):
        values = []
        if numbered:
            values.append(idx)
        values.extend([
            row["full_name"],
            row["position"],
            row["reward_count"],
            row.get("details_text") or "—",
        ])
        ws.append(values)
        excel_row = 3 + idx
        for cell in ws[excel_row]:
            cell.border = thin
            cell.alignment = wrap
            if idx % 2 == 0:
                cell.fill = stripe
        ws.row_dimensions[excel_row].height = 36

    widths = (8, 36, 20, 12, 70) if numbered else (36, 20, 12, 70)
    for col, width in zip(range(1, len(headers) + 1), widths):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A4"
    if rows:
        ws.auto_filter.ref = f"A3:{last_col}{3 + len(rows)}"
