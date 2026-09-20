
import re

from parsers.doc_io import cleanup_temp, open_word_document
from parsers.students_parser import INSTITUTION_KEYWORDS

STOP = (
    "список викладач",
    "педагогічн",
    "наказ",
    "директор",
    "заступник",
    "навч. рік",
    "н.р.",
)


def _looks_like_full_name_relaxed(text):
    text = re.sub(r"\s+", " ", text.strip())

    text = re.sub(r"\.$", "", text)
    words = text.split()
    if len(words) < 2 or len(words) > 3:
        return False


    ukr_pattern = re.compile(r"^[А-ЯІЇЄҐа-яіїєґ'’\-]+$")
    if not all(ukr_pattern.match(word) for word in words):
        return False


    if any(len(word) < 2 for word in words):
        return False

    return True


def _normalize_name(text):
    if not text:
        return text


    text = re.sub(r"\.$", "", text.strip())

    def capitalize_word(word):
        if not word:
            return word

        if "'" in word or "’" in word:
            parts = re.split(r"(['’])", word)
            return "".join([parts[0].capitalize() if parts[0] else "",
                           parts[1] if len(parts) > 1 else "",
                           parts[2].capitalize() if len(parts) > 2 else ""])
        return word.capitalize()

    words = text.split()
    normalized = " ".join(capitalize_word(word) for word in words)
    return normalized


def parse_teachers_list(file_path):
    doc, temp_path = open_word_document(file_path)
    try:
        names = []
        seen = set()

        def consider(text):
            text = re.sub(r"\s+", " ", (text or "").strip())
            if not text:
                return
            lower = text.lower()
            if any(s in lower for s in STOP):
                return
            if any(kw in lower for kw in INSTITUTION_KEYWORDS):
                return

            candidate = re.sub(r"^\d+[.)\s]+", "", text).strip()

            candidate = re.split(r"\s+[–-]\s+", candidate)[0].strip()

            if not _looks_like_full_name_relaxed(candidate):
                return


            normalized = _normalize_name(candidate)
            key = normalized.lower()
            if key in seen:
                return
            seen.add(key)

            names.append({"full_name": normalized})

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    consider(cell.text)
        for p in doc.paragraphs:
            consider(p.text)
        return names
    finally:
        cleanup_temp(temp_path)
