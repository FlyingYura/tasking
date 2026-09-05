"""
Співставлення студента з наказу зі студентом у базі даних.

Стара логіка брала перші 4 літери прізвища і шукала їх ЯК ПІДРЯДОК
у будь-якому імені з тієї ж групи ("кова" збіжиться і з Ковальчук,
і з Коваленко, і з Ковалів) — це давало помилкові співпадіння без
жодного попередження користувачу.

Тут натомість використовується коефіцієнт подібності рядків
(difflib.SequenceMatcher) по повністю нормалізованому ПІБ, з
перевіркою обох порядків слів (наказ часто пише "Ім'я ПРІЗВИЩЕ",
а список студентів — "Прізвище Ім'я"). Якщо найкращий збіг нижче
порогу впевненості — студент позначається як "не визначено" і
винесений на ручне підтвердження в інтерфейсі, а не мовчки
пропускається чи прив'язується навмання.
"""

import difflib
import re


def normalize_name(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _best_ratio(target, candidate_full_name):
    cand_norm = normalize_name(candidate_full_name)
    ratio = difflib.SequenceMatcher(None, target, cand_norm).ratio()

    words = cand_norm.split()
    if len(words) >= 2:
        reordered = " ".join([words[1], words[0]] + words[2:])
        ratio = max(ratio, difflib.SequenceMatcher(None, target, reordered).ratio())
    return ratio


def find_best_match(candidate_name, candidate_group, students, threshold=0.72):
    """
    students: список словників {id, full_name, group_name, group_id}
    Повертає (студент_або_None, score, список_кандидатів_для_ручного_вибору)

    top_candidates завжди містить принаймні найкращий здогад (навіть якщо
    він нижче порогу довіри) — щоб інтерфейс міг одразу показати
    користувачу "ось хто це, ймовірно, є" замість голого "не знайдено".
    """
    target = normalize_name(candidate_name)
    if not target:
        return None, 0.0, []

    pool = students
    if candidate_group:
        same_group = [s for s in students if s["group_name"].upper() == candidate_group.upper()]
        if same_group:
            pool = same_group

    scored = sorted(
        ((s, _best_ratio(target, s["full_name"])) for s in pool),
        key=lambda pair: pair[1],
        reverse=True,
    )

    if not scored:
        return None, 0.0, []

    best_student, best_score = scored[0]
    top_candidates = [s for s, _score in scored[:5]]

    if best_score >= threshold:
        return best_student, best_score, top_candidates
    return None, best_score, top_candidates
