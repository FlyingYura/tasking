
import json
import os

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".dmtfk_config.json")

DEFAULT_CONFIG = {
    "db": {
        "host": "localhost",
        "port": "5432",
        "dbname": "college_db",
        "user": "postgres",
        "password": ""
    },


    "points_levels": [
        {"keywords": ["міжнародн"], "label": "Міжнародний", "points": 3},
        {"keywords": ["обласн", "регіональн"], "label": "Обласний / Регіональний", "points": 2},
        {"keywords": [], "label": "Міський / Місцевий", "points": 1}
    ],


    "reprimand_levels": [
        {"keywords": ["доган"], "label": "Догана", "points": 0.5}
    ],


    "stop_phrases": [
        "список студентів",
        "денного відділення",
        "зараховані на курс",
        "накз",
        "витяг з наказу"
    ],


    "match_threshold": 0.72,
    "appearance_mode": "Light"
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = json.loads(json.dumps(DEFAULT_CONFIG))
            for key, value in data.items():
                merged[key] = value
            return merged
        except Exception:
            return json.loads(json.dumps(DEFAULT_CONFIG))
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
