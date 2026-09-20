
import difflib
import re


def normalize_name(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def normalize_ukrainian_case(name):
    if not name:
        return None


    name = re.sub(r"([А-ЯІЇЄҐа-яіїєґ']+?)(у|ові|ю|а|я|ій|ію|єм|є|й|ів|ь)\s+", r"\1 ", name, flags=re.IGNORECASE)
    name = re.sub(r"\s([А-ЯІЇЄҐа-яіїєґ']+?)(у|ові|ю|а|я|ій|ію|єм|є|й|ів|ь)$", r" \1", name, flags=re.IGNORECASE)


    name = re.sub(r"\s+", " ", name.strip())

    return name.lower()


def normalize_ukrainian_name_advanced(name):
    if not name:
        return None


    words = name.split()
    normalized_words = []

    for word in words:

        word = re.sub(r"(у|ові|ю|а|я|ій|ію|єм|є|й|ів|ь)$", "", word, flags=re.IGNORECASE)
        normalized_words.append(word)


    normalized = " ".join(normalized_words)
    return re.sub(r"\s+", " ", normalized.strip()).lower()


def _best_ratio(target, candidate_full_name):
    cand_norm = normalize_name(candidate_full_name)
    ratio = difflib.SequenceMatcher(None, target, cand_norm).ratio()

    words = cand_norm.split()
    if len(words) >= 2:
        reordered = " ".join([words[1], words[0]] + words[2:])
        ratio = max(ratio, difflib.SequenceMatcher(None, target, reordered).ratio())
    return ratio


def _best_ratio_advanced(target, candidate_full_name):
    cand_norm = normalize_ukrainian_name_advanced(candidate_full_name)
    ratio = difflib.SequenceMatcher(None, target, cand_norm).ratio()

    words = cand_norm.split()
    if len(words) >= 2:
        reordered = " ".join([words[1], words[0]] + words[2:])
        ratio = max(ratio, difflib.SequenceMatcher(None, target, reordered).ratio())
    return ratio


def find_best_match(candidate_name, candidate_group, students, threshold=0.72):
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


def find_best_teacher_match(candidate_name, teachers, threshold=0.72):
    target = normalize_name(candidate_name)
    if not target:
        return None, 0.0, []

    scored = sorted(
        ((t, _best_ratio(target, t["full_name"])) for t in teachers),
        key=lambda pair: pair[1],
        reverse=True,
    )

    if not scored:
        return None, 0.0, []

    best_teacher, best_score = scored[0]
    top_candidates = [t for t, _score in scored[:5]]

    if best_score >= threshold:
        return best_teacher, best_score, top_candidates
    return None, best_score, top_candidates
