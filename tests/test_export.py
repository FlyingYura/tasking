import os
import sys
import tempfile
import unittest

from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import export


class TestRatingExport(unittest.TestCase):
    def test_overall_sheet_then_one_sheet_per_group(self):
        rows = [
            {"full_name": "Іванов Іван", "group_name": "ЕК-11", "total": 3},
            {"full_name": "Петренко Марія", "group_name": "ЕК-11", "total": 1},
            {"full_name": "Бойчук Назар", "group_name": "ОР-21", "total": 2},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rating.xlsx")
            export.export_rating_to_xlsx(rows, path)
            wb = load_workbook(path)

        self.assertEqual(wb.sheetnames[0], "Загальний рейтинг")
        self.assertIn("ЕК-11", wb.sheetnames)
        self.assertIn("ОР-21", wb.sheetnames)
        self.assertEqual(wb["Загальний рейтинг"]["A4"].value, 1)
        self.assertEqual(wb["Загальний рейтинг"]["B4"].value, "Іванов Іван")
        self.assertEqual(wb["ЕК-11"].max_row, 5)  # title + empty + header + 2 students
        self.assertEqual(wb["ОР-21"]["B4"].value, "Бойчук Назар")
        self.assertEqual(wb["ОР-21"]["A4"].value, 1)

    def test_sheet_names_are_sanitized(self):
        used = set()
        first = export._safe_sheet_name("ЕК/11:тест", used)
        second = export._safe_sheet_name("ЕК/11:тест", used)
        self.assertNotIn("/", first)
        self.assertNotIn(":", first)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
