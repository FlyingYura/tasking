"""
Модуль конфігурації застосунку.

Раніше параметри підключення до БД вводились вручну щоразу при запуску,
а рівні нагород ("Міжнародний" / "Обласний" / "Місцевий") та їх бали
були захардкоджені у коді. Тепер усе це зберігається в локальному
JSON-файлі профілю користувача, редагується через діалог "Налаштування"
і завантажується автоматично при старті програми.
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".doc_flow_app_config.json")

DEFAULT_CONFIG = {
    "db": {
        "host": "localhost",
        "port": "5432",
        "dbname": "college_db",
        "user": "postgres",
        "password": ""
    },
    # Рівні заходів для автоматичного визначення балів з тексту наказу.
    # Перевіряються по порядку зверху вниз; перший, що збігається — застосовується.
    # Порожній список ключових слів = варіант "за замовчуванням".
    "points_levels": [
        {"keywords": ["міжнародн"], "label": "Міжнародний", "points": 3},
        {"keywords": ["обласн", "регіональн"], "label": "Обласний / Регіональний", "points": 2},
        {"keywords": [], "label": "Міський / Місцевий", "points": 1}
    ],
    # Службові фрази-заголовки, які треба ігнорувати при парсингу списків студентів.
    # Навмисно НЕ містять назви конкретного навчального закладу — це робить
    # парсер придатним для будь-якого коледжу/університету без правок коду.
    "stop_phrases": [
        "список студентів",
        "денного відділення",
        "зараховані на курс",
        "накз",
        "витяг з наказу"
    ],
    # Поріг подібності імен (0..1) для автоматичного співставлення студента
    # з наказу зі студентом у базі. Нижче порогу — потрібне ручне підтвердження.
    "match_threshold": 0.72
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
            for key, value in data.items():
                merged[key] = value
            return merged
        except Exception:
            return json.loads(json.dumps(DEFAULT_CONFIG))
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
