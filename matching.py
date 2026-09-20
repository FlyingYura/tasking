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


def find_best_match(candidate_name, candidates, threshold=0.72, candidate_group=None):
    target = normalize_name(candidate_name)
    if not target:
        return None, 0.0, []

    pool = candidates
    if candidate_group:
        same_group = [c for c in candidates if c.get("group_name", "").upper() == candidate_group.upper()]
        if same_group:
            pool = same_group

    scored = sorted(
        ((c, _best_ratio(target, c["full_name"])) for c in pool),
        key=lambda pair: pair[1],
        reverse=True,
    )

    if not scored:
        return None, 0.0, []

    best, best_score = scored[0]
    top_candidates = [c for c, _score in scored[:5]]

    if best_score >= threshold:
        return best, best_score, top_candidates
    return None, best_score, top_candidates
