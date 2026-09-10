import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matching
from parsers.reward_parser import parse_reward_order, DEFAULT_POINTS_LEVELS, _determine_level, _detect_order_kind
from scoring import applied_points
from parsers.students_parser import parse_students_tables


class TestMatching(unittest.TestCase):
    def setUp(self):
        self.students = [
            {"id": 1, "full_name": "Ковальчук Іван Петрович", "group_name": "ЕК-11", "group_id": 1},
            {"id": 2, "full_name": "Коваленко Марія Іванівна", "group_name": "ЕК-11", "group_id": 1},
            {"id": 3, "full_name": "Ковалів Олена Сергіївна", "group_name": "ЕК-11", "group_id": 1},
            {"id": 4, "full_name": "Бойчук Назар Іванович", "group_name": "ОР-21", "group_id": 2},
        ]

    def test_exact_name_matches_confidently(self):
        match, score, _ = matching.find_best_match("Ковальчук Іван Петрович", "ЕК-11", self.students)
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], 1)
        self.assertGreaterEqual(score, 0.9)

    def test_reordered_first_last_name_still_matches(self):
        # накази часто пишуть "Ім'я ПРІЗВИЩЕ" замість "Прізвище Ім'я"
        match, score, _ = matching.find_best_match("Назар Бойчук", "ОР-21", self.students)
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], 4)

    def test_similar_surnames_are_not_confused(self):
        # стара логіка (перші 4 літери прізвища) плутала Ковальчук/Коваленко/Ковалів.
        # нова логіка на повному ПІБ повинна їх розрізняти.
        match, score, candidates = matching.find_best_match("Коваленко Марія Іванівна", "ЕК-11", self.students)
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], 2)

    def test_unknown_name_is_not_matched_blindly(self):
        match, score, candidates = matching.find_best_match("Нікітенко Тарас Юрійович", "ЕК-11", self.students, threshold=0.72)
        self.assertIsNone(match)

    def test_best_guess_is_still_returned_below_threshold(self):
        # Навіть якщо впевненість нижча за поріг, інтерфейс має що показати
        # користувачу як "найімовірніший варіант" замість голого "не знайдено".
        match, score, candidates = matching.find_best_match("Ковальов Ігор", "ЕК-11", self.students, threshold=0.9)
        self.assertIsNone(match)
        self.assertTrue(len(candidates) > 0)


class TestRewardLevels(unittest.TestCase):
    def test_default_level_used_when_no_keyword_matches(self):
        label, points = _determine_level("наказ про подяку студентам коледжу", DEFAULT_POINTS_LEVELS)
        self.assertEqual(label, "Міський / Місцевий")
        self.assertEqual(points, 1)

    def test_international_keyword_detected(self):
        label, points = _determine_level("за перемогу у міжнародній олімпіаді", DEFAULT_POINTS_LEVELS)
        self.assertEqual(label, "Міжнародний")
        self.assertEqual(points, 3)

    def test_no_hardcoded_person_is_excluded(self):
        # Раніше parse_reward_order МОВЧКИ видаляв усіх студентів з певним
        # прізвищем з будь-якого наказу. Перевіряємо функціонально: студент
        # з таким прізвищем має з'явитись у розпізнаному списку, як і будь-хто інший.
        from unittest import mock
        from parsers import reward_parser

        class FakeParagraph:
            def __init__(self, text):
                self.text = text

        class FakeDoc:
            def __init__(self, _path):
                self.paragraphs = [
                    FakeParagraph("Наказ № 12 від 01.09.2026"),
                    FakeParagraph("Оголосити подяку за перемогу у конкурсі:"),
                    FakeParagraph("Юрчак Оксана – група ЕК-11"),
                    FakeParagraph("Бойчук Назар – група ОР-21"),
                ]

        with mock.patch.object(reward_parser, "Document", FakeDoc):
            result = reward_parser.parse_reward_order("fake.docx")

        names = [s["full_name"].lower() for s in result["students"]]
        self.assertIn("юрчак оксана", names)
        self.assertIn("бойчук назар", names)

    def test_real_order_excludes_the_signing_deputy_director(self):
        # Реальний наказ №271: заступник директора з виховної роботи
        # підписується своїм ПІБ у звичайному регістрі одразу під рядком
        # посади. Раніше єдиним захистом від потрапляння підписанта у
        # список нагороджених студентів був хардкод її прізвища.
        # Тепер рядок одразу після будь-якої посадової назви виключається
        # автоматично, незалежно від того, чиє ім'я там стоїть.
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "order_271.docx")
        if not os.path.exists(fixture):
            self.skipTest("fixture order_271.docx not present")

        result = parse_reward_order(fixture)

        self.assertEqual(len(result["students"]), 17)
        names = [s["full_name"].lower() for s in result["students"]]
        self.assertNotIn("ірина юрчак", names)
        self.assertTrue(all(s["group_name"] for s in result["students"]))
        self.assertIn("вайді юліані", names)
        self.assertIn("писко анні", names)
        self.assertEqual(result.get("order_kind"), "reward")


class TestReprimandOrders(unittest.TestCase):
    def test_detect_reprimand_from_order_text(self):
        self.assertEqual(_detect_order_kind("оголосити догану студентам коледжу"), "reprimand")
        self.assertEqual(_detect_order_kind("наказ про подяку студентам коледжу"), "reward")

    def test_reprimand_does_not_subtract_from_zero(self):
        self.assertEqual(applied_points("reprimand", 0.5, 0), 0.0)

    def test_reprimand_subtracts_half_point(self):
        self.assertEqual(applied_points("reprimand", 0.5, 3), -0.5)

    def test_reprimand_does_not_go_below_zero(self):
        self.assertEqual(applied_points("reprimand", 0.5, 0.3), -0.3)

    def test_parse_reprimand_order_sets_kind_and_points(self):
        from parsers import reward_parser

        class FakeParagraph:
            def __init__(self, text):
                self.text = text

        class FakeDoc:
            def __init__(self, _path):
                self.paragraphs = [
                    FakeParagraph("Наказ № 44 від 11.09.2026"),
                    FakeParagraph("Оголосити догану за порушення правил внутрішнього розпорядку:"),
                    FakeParagraph("Бойчук Назар – група ОР-21"),
                ]

        with mock.patch.object(reward_parser, "Document", FakeDoc):
            result = reward_parser.parse_reward_order("fake.docx")

        self.assertEqual(result["order_kind"], "reprimand")
        self.assertEqual(result["level_type"], "Догана")
        self.assertEqual(result["points"], 0.5)
        self.assertEqual(result["students"][0]["full_name"], "Бойчук Назар")


class TestStudentsParser(unittest.TestCase):
    def test_25plus_removed_from_name_but_kept_in_note(self):
        # Раніше regex з "\b" межею слова не спрацьовував, коли "25+" стояло
        # перед пробілом, тож позначка інколи лишалась приклеєною до ПІБ.
        class FakeCell:
            def __init__(self, text):
                self.text = text

        class FakeRow:
            def __init__(self, cells_text):
                self.cells = [FakeCell(t) for t in cells_text]

        class FakeTable:
            def __init__(self, rows_text):
                self.rows = [FakeRow(r) for r in rows_text]

        class FakeDoc:
            def __init__(self, _path):
                self.tables = [FakeTable([
                    ["ЕК-11", "2025/2026"],
                    ["1", "Іванова Марія 25+", "К", ""],
                ])]
                self.paragraphs = []

        from parsers import students_parser
        with mock.patch.object(students_parser, "Document", FakeDoc):
            result = parse_students_tables("fake.docx")

        self.assertIn("ЕК-11", result)
        names = [s["full_name"] for s in result["ЕК-11"]["students"]]
        notes = [s["note"] for s in result["ЕК-11"]["students"]]
        self.assertIn("Іванова Марія", names)
        self.assertNotIn("25+", " ".join(names))
        self.assertTrue(any("25+" in n for n in notes))


class TestMultiFileImportMerge(unittest.TestCase):
    def test_merge_combines_groups_and_dedupes_students_across_files(self):
        import app

        result_file_1 = {
            "ЕК-11": {"study_year": "2025/2026", "curator": "Не вказано",
                       "students": [{"full_name": "Іван Іванов", "funding": "К", "note": "—"}]}
        }
        result_file_2 = {
            "ЕК-11": {"study_year": "Не вказано", "curator": "Петренко П.П.",
                       "students": [
                           {"full_name": "Марія Петрова", "funding": "К", "note": "—"},
                           {"full_name": "Іван Іванов", "funding": "К", "note": "—"},  # дублікат з іншого файлу
                       ]},
            "ОР-21": {"study_year": "2025/2026", "curator": "Сидорук С.С.",
                      "students": [{"full_name": "Назар Бойчук", "funding": "ДЗ", "note": "—"}]},
        }

        merged = app.StudentManagementApp._merge_parsed_groups([result_file_1, result_file_2])

        self.assertEqual(set(merged.keys()), {"ЕК-11", "ОР-21"})
        ek11_names = [s["full_name"] for s in merged["ЕК-11"]["students"]]
        self.assertEqual(len(ek11_names), 2)  # дублікат "Іван Іванов" не подвоївся
        self.assertIn("Іван Іванов", ek11_names)
        self.assertIn("Марія Петрова", ek11_names)
        self.assertEqual(merged["ЕК-11"]["curator"], "Петренко П.П.")  # підхопили з другого файлу
        self.assertEqual(merged["ЕК-11"]["study_year"], "2025/2026")  # не затерли значенням з другого файлу


if __name__ == "__main__":
    unittest.main()
