
import os
import tempfile

from docx import Document


def convert_doc_to_docx(file_path, prefix="aktiv_plus_"):
    try:
        import win32com.client as win32
    except ImportError:
        raise Exception(
            "Читання файлів .doc підтримується лише на Windows з встановленим MS Word. "
            "Відкрийте файл у Word і збережіть як .docx, після чого спробуйте ще раз."
        )
    word = win32.Dispatch("Word.Application")
    word.Visible = False
    fd, temp_docx = tempfile.mkstemp(prefix=prefix, suffix=".docx")
    os.close(fd)
    try:
        doc_win = word.Documents.Open(os.path.abspath(file_path))
        try:
            doc_win.SaveAs2(temp_docx, FileFormat=16)
        finally:
            doc_win.Close()
        return temp_docx
    except Exception:
        try:
            os.remove(temp_docx)
        except OSError:
            pass
        raise
    finally:
        word.Quit()


def open_word_document(file_path):
    path = file_path
    temp_path = None
    if file_path.lower().endswith(".doc") and not file_path.lower().endswith(".docx"):
        temp_path = convert_doc_to_docx(file_path)
        path = temp_path
    try:
        doc = Document(path)
    except Exception as exc:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise Exception(f"Не вдалося прочитати документ: {exc}") from exc
    return doc, temp_path


def cleanup_temp(temp_path):
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass
