import os
import sys
import tempfile
import unittest

from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import export


class TestRatingExport(unittest.TestCase):
    def test_overall_by_points_groups_alphabetical_and_details_sheet(self):
        rows = [
            {"student_id": 1, "full_name": "Іванов Іван", "group_name": "ЕК-11", "total": 3},
            {"student_id": 2, "full_name": "Петренко Марія", "group_name": "ЕК-11", "total": 5},
            {"student_id": 3, "full_name": "Бойчук Назар", "group_name": "ОР-21", "total": 2},
        ]
        details = [
            {
                "student_id": 2, "full_name": "Петренко Марія", "group_name": "ЕК-11",
                "order_number": "12", "order_date": "01.09.2026",
                "event_title": "Подяка за конкурс", "level_type": "Міський / Місцевий",
                "points": 1, "source_filename": "nakaz.docx",
            },
            {
                "student_id": 2, "full_name": "Петренко Марія", "group_name": "ЕК-11",
                "order_number": "44", "order_date": "02.09.2026",
                "event_title": "Догана", "level_type": "Догана",
                "points": -0.5, "source_filename": "dogana.docx",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rating.xlsx")
            export.export_rating_to_xlsx(rows, path, detail_rows=details)
            wb = load_workbook(path)

        self.assertEqual(wb.sheetnames[0], "Загальний рейтинг")
        self.assertIn("ЕК-11", wb.sheetnames)
        self.assertIn("ОР-21", wb.sheetnames)
        self.assertIn("Деталі нарахувань", wb.sheetnames)
        self.assertEqual(wb["Загальний рейтинг"]["B4"].value, "Петренко Марія")
        # у групі — алфавіт, не бали: Іванов перед Петренко
        self.assertEqual(wb["ЕК-11"]["B4"].value, "Іванов Іван")
        self.assertEqual(wb["ЕК-11"]["B5"].value, "Петренко Марія")
        self.assertIn("№12", wb["ЕК-11"]["E5"].value)
        self.assertEqual(wb["Деталі нарахувань"]["C4"].value, "12")
        self.assertEqual(wb["Деталі нарахувань"]["H4"].value, "nakaz.docx")

    def test_sheet_names_are_sanitized(self):
        used = set()
        first = export._safe_sheet_name("ЕК/11:тест", used)
        second = export._safe_sheet_name("ЕК/11:тест", used)
        self.assertNotIn("/", first)
        self.assertNotIn(":", first)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
