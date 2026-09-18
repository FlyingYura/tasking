import logging
import os
import subprocess
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

import config as cfg
import database
import export
import matching
from parsers.reward_parser import parse_reward_order
from parsers.students_parser import parse_students_tables
from scoring import applied_points, format_achievement_line, format_points

logging.basicConfig(
    filename=os.path.join(os.path.expanduser("~"), "aktiv_plus_app.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

COLUMN_LABELS = {
    "id": "ID",
    "full_name": "ПІБ",
    "group_name": "Група",
    "funding": "Фінансування",
    "note": "Примітка",
    "name": "Назва",
    "study_year": "Навчальний рік",
    "curator": "Куратор",
    "order_number": "Номер наказу",
    "order_date": "Дата",
    "level_type": "Рівень",
    "default_points": "Бали наказу",
    "source_filename": "Файл наказу",
    "student_id": "ID студента",
    "order_id": "ID наказу",
    "points_awarded": "Нараховані бали",
    "position": "Посада",
    "teacher_id": "ID викладача",
}

TABLE_LABELS = {
    "groups": "Групи",
    "students": "Студенти",
    "orders": "Накази",
    "achievements": "Нарахування балів",
    "teachers": "Викладачі",
    "teacher_rewards": "Подяки викладачів",
}


def apply_treeview_style(root, appearance_mode):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    is_dark = appearance_mode == "Dark" or (
        appearance_mode == "System" and ctk.get_appearance_mode() == "Dark"
    )
    if is_dark:
        bg, fg, heading_bg, heading_fg = "#1e1e1e", "#f8f9fa", "#2b2b2b", "#f8f9fa"
        selected, stripe, field = "#1864ab", "#252525", "#1e1e1e"
    else:
        bg, fg, heading_bg, heading_fg = "#ffffff", "#212529", "#e7f5ff", "#1864ab"
        selected, stripe, field = "#1971c2", "#f8f9fa", "#ffffff"

    style.configure(
        "App.Treeview",
        background=bg,
        foreground=fg,
        fieldbackground=field,
        rowheight=28,
        font=("Segoe UI", 10),
        borderwidth=0,
    )
    style.configure(
        "App.Treeview.Heading",
        background=heading_bg,
        foreground=heading_fg,
        font=("Segoe UI", 10, "bold"),
        relief="flat",
        padding=6,
    )
    style.map(
        "App.Treeview",
        background=[("selected", selected)],
        foreground=[("selected", "#ffffff")],
    )
    style.configure("App.Treeview", oddrow=stripe)
    return is_dark


def run_async(widget, work_fn, on_success=None, on_error=None):
    """Виконує роботу у фоновому потоці, щоб не блокувати інтерфейс
    (парсинг великих документів чи мережеві звернення до БД раніше
    "заморожували" все вікно)."""

    def target():
        try:
            result = work_fn()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Помилка фонової операції")
            widget.after(0, lambda: on_error(exc) if on_error else None)
            return
        widget.after(0, lambda: on_success(result) if on_success else None)

    threading.Thread(target=target, daemon=True).start()


class SettingsDialog(ctk.CTkToplevel):
    """Одне вікно налаштувань: БД, подяки, догани, тема."""

    def __init__(self, master, on_saved):
        super().__init__(master)
        self.title("Налаштування")
        self.geometry("560x720")
        self.minsize(520, 560)
        self.grab_set()
        self.on_saved = on_saved
        self.cfg = cfg.load_config()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=18, pady=12)

        ctk.CTkLabel(scroll, text="Підключення до бази даних", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(4, 8))
        db = self.cfg["db"]
        self.entries = {}
        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="x")
        for row, (key, label) in enumerate([
            ("host", "Хост"), ("port", "Порт"), ("dbname", "Назва БД"),
            ("user", "Користувач"), ("password", "Пароль"),
        ]):
            ctk.CTkLabel(grid, text=label).grid(row=row, column=0, padx=(0, 12), pady=6, sticky="w")
            show = "*" if key == "password" else ""
            entry = ctk.CTkEntry(grid, width=280, show=show)
            entry.insert(0, str(db.get(key, "")))
            entry.grid(row=row, column=1, pady=6, sticky="w")
            self.entries[key] = entry
        ctk.CTkLabel(
            scroll,
            text="Пароль зберігається локально у файлі профілю. На спільному комп'ютері краще лишити поле порожнім.",
            text_color="gray", justify="left", wraplength=480,
        ).pack(anchor="w", pady=(4, 16))

        ctk.CTkLabel(scroll, text="Подяки / бали", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ctk.CTkLabel(scroll, text="Ключові слова в тексті наказу → рівень і бали", text_color="gray").pack(anchor="w", pady=(0, 6))
        self.level_rows = []
        levels_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        levels_frame.pack(fill="x")
        for level in self.cfg["points_levels"]:
            self._add_level_row(self.level_rows, levels_frame, level)
        ctk.CTkButton(
            scroll, text="+ Додати рівень подяки", width=180,
            command=lambda: self._add_level_row(self.level_rows, levels_frame, {"keywords": [], "label": "", "points": 1}),
        ).pack(anchor="w", pady=(8, 16))

        ctk.CTkLabel(scroll, text="Догани / бали", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ctk.CTkLabel(scroll, text="Значення, яке віднімається (навіть якщо зараз 0 — щоб пізніша подяка його перекрила).", text_color="gray", wraplength=480, justify="left").pack(anchor="w", pady=(0, 6))
        self.reprimand_rows = []
        reprimand_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        reprimand_frame.pack(fill="x")
        for level in self.cfg.get("reprimand_levels") or cfg.DEFAULT_CONFIG["reprimand_levels"]:
            self._add_level_row(self.reprimand_rows, reprimand_frame, level)
        ctk.CTkButton(
            scroll, text="+ Додати рівень догани", width=180,
            command=lambda: self._add_level_row(self.reprimand_rows, reprimand_frame, {"keywords": [], "label": "", "points": 0.5}),
        ).pack(anchor="w", pady=(8, 16))

        ctk.CTkLabel(scroll, text="Тема програми", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(4, 8))
        current_theme = self.cfg.get("appearance_mode", "Light")
        theme_label = "Темна" if current_theme == "Dark" else "Світла"
        self.theme_var = ctk.StringVar(value=theme_label)
        self.theme_switch = ctk.CTkSegmentedButton(
            scroll, values=["Світла", "Темна"], variable=self.theme_var,
            command=self._preview_theme, width=240,
        )
        self.theme_switch.pack(anchor="w")

        ctk.CTkButton(self, text="Зберегти", fg_color="#1d4e89", height=36, command=self.save).pack(pady=(0, 16), padx=18, fill="x")

    def _add_level_row(self, rows, parent, level):
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", pady=3)
        kw_entry = ctk.CTkEntry(row_frame, width=150, placeholder_text="ключові слова через кому")
        kw_entry.insert(0, ", ".join(level.get("keywords", [])))
        kw_entry.pack(side="left", padx=3)
        label_entry = ctk.CTkEntry(row_frame, width=160, placeholder_text="назва рівня")
        label_entry.insert(0, level.get("label", ""))
        label_entry.pack(side="left", padx=3)
        pts_entry = ctk.CTkEntry(row_frame, width=50, placeholder_text="бали")
        pts_entry.insert(0, format_points(level.get("points", 1)))
        pts_entry.pack(side="left", padx=3)
        rows.append((kw_entry, label_entry, pts_entry))

    @staticmethod
    def _collect_levels(rows, default_points):
        levels = []
        for kw_entry, label_entry, pts_entry in rows:
            label = label_entry.get().strip()
            if not label:
                continue
            keywords = [w.strip().lower() for w in kw_entry.get().split(",") if w.strip()]
            try:
                points = float(pts_entry.get().strip().replace(",", "."))
            except ValueError:
                points = default_points
            levels.append({"keywords": keywords, "label": label, "points": points})
        return levels

    def save(self):
        new_db = {k: e.get().strip() for k, e in self.entries.items()}
        levels = self._collect_levels(self.level_rows, 1)
        reprimands = self._collect_levels(self.reprimand_rows, 0.5)

        self.cfg["db"] = new_db
        if levels:
            self.cfg["points_levels"] = levels
        if reprimands:
            self.cfg["reprimand_levels"] = reprimands
        self.cfg["appearance_mode"] = "Dark" if self.theme_var.get() == "Темна" else "Light"
        cfg.save_config(self.cfg)
        self.destroy()
        self.on_saved(self.cfg)

    def _preview_theme(self, value):
        mode = "Dark" if value == "Темна" else "Light"
        ctk.set_appearance_mode(mode)
        if hasattr(self.master, "apply_appearance"):
            self.master.apply_appearance(mode)

    def _on_close(self):
        original = self.cfg.get("appearance_mode", "Light")
        ctk.set_appearance_mode(original)
        if hasattr(self.master, "apply_appearance"):
            self.master.apply_appearance(original)
        self.destroy()


class MatchResolutionDialog(ctk.CTkToplevel):
    """Ручне підтвердження студента, якого не вдалося однозначно
    розпізнати автоматично (раніше такі студенти або збігалися
    навмання за 4 літерами прізвища, або взагалі губились)."""

    def __init__(self, master, candidate_name, candidate_options, on_resolved):
        super().__init__(master)
        self.title("Підтвердіть студента")
        self.geometry("420x260")
        self.grab_set()
        self.on_resolved = on_resolved

        ctk.CTkLabel(
            self, text=f"У наказі знайдено: «{candidate_name}»\nОберіть відповідного студента з бази:",
            justify="left",
        ).pack(padx=20, pady=(20, 10), anchor="w")

        options_display = [f"{s['full_name']} ({s['group_name']})" for s in candidate_options]
        options_display.append("— жоден із запропонованих —")

        self.choice = ctk.CTkOptionMenu(self, values=options_display or ["— немає варіантів —"], width=350)
        self.choice.pack(padx=20, pady=10)
        if options_display:
            self.choice.set(options_display[0])

        self.candidate_options = candidate_options

        ctk.CTkButton(self, text="Підтвердити", fg_color="#2b8a3e", command=self._confirm).pack(pady=15)

    def _confirm(self):
        selected = self.choice.get()
        chosen = None
        for s in self.candidate_options:
            if selected.startswith(s["full_name"]):
                chosen = s
                break
        self.destroy()
        self.on_resolved(chosen)


class TeacherMatchResolutionDialog(ctk.CTkToplevel):
    """Ручне підтвердження викладача, якого не вдалося однозначно
    розпізнати автоматично. Аналогічно до діалогу для студентів."""

    def __init__(self, master, candidate_name, candidate_options, on_resolved):
        super().__init__(master)
        self.title("Підтвердіть викладача")
        self.geometry("420x260")
        self.grab_set()
        self.on_resolved = on_resolved

        ctk.CTkLabel(
            self, text=f"У наказі знайдено: «{candidate_name}»\nОберіть відповідного викладача з бази:",
            justify="left",
        ).pack(padx=20, pady=(20, 10), anchor="w")

        options_display = [f"{t['full_name']}" for t in candidate_options]
        options_display.append("— жоден із запропонованих —")

        self.choice = ctk.CTkOptionMenu(self, values=options_display or ["— немає варіантів —"], width=350)
        self.choice.pack(padx=20, pady=10)
        if options_display:
            self.choice.set(options_display[0])

        self.candidate_options = candidate_options

        ctk.CTkButton(self, text="Підтвердити", fg_color="#2b8a3e", command=self._confirm).pack(pady=15)

    def _confirm(self):
        selected = self.choice.get()
        chosen = None
        for t in self.candidate_options:
            if selected == t["full_name"]:
                chosen = t
                break
        self.destroy()
        self.on_resolved(chosen)


def open_attachment_bytes(filename, blob):
    if not blob:
        raise FileNotFoundError("До цього наказу файл не прикріплено.")
    suffix = os.path.splitext(filename or "order.bin")[1] or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(blob)
    tmp.close()
    try:
        os.startfile(tmp.name)  # Windows
    except AttributeError:
        subprocess.Popen(["xdg-open", tmp.name])
    return tmp.name


class StudentHistoryDialog(ctk.CTkToplevel):
    def __init__(self, master, student_name, group_name, total_points, history, open_file_fn):
        super().__init__(master)
        self.title(f"Нарахування: {student_name}")
        self.geometry("860x460")
        self.grab_set()
        self.history = history
        self.open_file_fn = open_file_fn

        ctk.CTkLabel(
            self,
            text=f"{student_name}  ·  група {group_name}  ·  у рейтингу: {format_points(total_points)}",
            font=("Segoe UI", 14, "bold"),
            justify="left",
        ).pack(padx=16, pady=(16, 8), anchor="w")

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=8)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        columns = ("date", "number", "level", "commendation_type", "pts", "file")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", style="App.Treeview")
        for col, text, w in [
            ("date", "Дата", 120), ("number", "№ наказу", 130),
            ("level", "Рівень", 140), ("commendation_type", "Тип подяки", 250), ("pts", "Бали", 80), ("file", "Файл", 200),
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="w" if col in ("file", "commendation_type") else "center")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", lambda _e: self._open_selected())

        if not history:
            self.tree.insert("", "end", values=("", "Немає подяк і доган", "", "", "", "", ""))
        else:
            for item in history:
                pts = format_points(item["points"])
                if float(item["points"]) > 0:
                    pts = f"+{pts}"
                filename = item.get("source_filename") or ("є файл" if item.get("has_file") else "—")
                commendation_type = item.get("commendation_type") or item.get("level_type") or "—"
                
                # Якщо є детальна інформація про типи, показуємо просто "змішані"
                if "commendation_types" in item and len(item["commendation_types"]) > 1:
                    commendation_display = "змішані"
                else:
                    commendation_display = commendation_type
                
                self.tree.insert("", "end", iid=str(item["order_id"]), values=(
                    item.get("order_date") or "",
                    item.get("order_number") or "",
                    item.get("level_type") or "",
                    commendation_display,
                    pts,
                    filename,
                ))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(4, 16))
        ctk.CTkButton(btns, text="Відкрити файл наказу", width=180, command=self._open_selected).pack(side="left")
        ctk.CTkButton(btns, text="Закрити", width=110, command=self.destroy).pack(side="right")

    def _open_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Файл наказу", "Оберіть рядок наказу в таблиці.")
            return
        order_id = selected[0]
        item = next((h for h in self.history if str(h["order_id"]) == str(order_id)), None)
        if not item or not item.get("has_file"):
            messagebox.showinfo("Файл наказу", "До цього наказу файл не прикріплено.")
            return
        try:
            self.open_file_fn(item["order_id"])
        except Exception as exc:
            messagebox.showerror("Не вдалося відкрити файл", str(exc))


class TeacherHistoryDialog(ctk.CTkToplevel):
    def __init__(self, master, teacher_name, reward_count, history, open_file_fn):
        super().__init__(master)
        self.title(f"Подяки: {teacher_name}")
        self.geometry("860x460")
        self.grab_set()
        self.history = history
        self.open_file_fn = open_file_fn

        ctk.CTkLabel(
            self,
            text=f"{teacher_name}  ·  кількість подяк: {reward_count}",
            font=("Segoe UI", 14, "bold"),
            justify="left",
        ).pack(padx=16, pady=(16, 8), anchor="w")

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=8)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        columns = ("date", "number", "level", "file")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", style="App.Treeview")
        for col, text, w in [
            ("date", "Дата", 120), ("number", "№ наказу", 130),
            ("level", "Рівень", 180), ("file", "Файл", 200),
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="w" if col == "file" else "center")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", lambda _e: self._open_selected())

        if not history:
            self.tree.insert("", "end", values=("", "Немає подяк", "", ""))
        else:
            for item in history:
                filename = item.get("source_filename") or ("є файл" if item.get("has_file") else "—")
                self.tree.insert("", "end", iid=str(item["order_id"]), values=(
                    item.get("order_date") or "",
                    item.get("order_number") or "",
                    item.get("level_type") or "",
                    filename,
                ))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(4, 16))
        ctk.CTkButton(btns, text="Відкрити файл наказу", width=180, command=self._open_selected).pack(side="left")
        ctk.CTkButton(btns, text="Закрити", width=110, command=self.destroy).pack(side="right")

    def _open_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Файл наказу", "Оберіть рядок наказу в таблиці.")
            return
        order_id = selected[0]
        item = next((h for h in self.history if str(h["order_id"]) == str(order_id)), None)
        if not item or not item.get("has_file"):
            messagebox.showinfo("Файл наказу", "До цього наказу файл не прикріплено.")
            return
        try:
            self.open_file_fn(item["order_id"])
        except Exception as exc:
            messagebox.showerror("Не вдалося відкрити файл", str(exc))


class StudentManagementApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ДМТФК+ — документообіг")
        self.minsize(1100, 800)

        # Встановлення іконки програми
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass  # Якщо іконку не вдалося встановити, програма продовжує роботу

        self.app_config = cfg.load_config()
        ctk.set_appearance_mode(self.app_config.get("appearance_mode", "Light"))
        self.db = None
        self.live_db = None
        self._viewing_backup = False

        self.loaded_data = None
        self.loaded_reward_data = None
        self.loaded_teachers_data = None
        self.import_type = "students"
        self.selected_group_id = None
        self.selected_db_table = None
        self._db_table_by_label = {}
        self._db_columns = []
        self._edit_entry = None
        self._edit_meta = None
        self._treeviews = []

        self.create_widgets()
        self.apply_appearance()
        self.after(50, self._maximize)
        self.after(200, self.auto_connect)

    def _maximize(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                self.geometry("1400x900")

    def apply_appearance(self, mode=None):
        mode = mode or self.app_config.get("appearance_mode", "Light")
        ctk.set_appearance_mode(mode)
        apply_treeview_style(self, mode)
        self._style_sidebar(mode)
        for tree in getattr(self, "_treeviews", []):
            try:
                tree.tag_configure("odd", background="#f8f9fa" if mode != "Dark" else "#252525")
                tree.tag_configure("even", background="#ffffff" if mode != "Dark" else "#1e1e1e")
            except tk.TclError:
                pass

    def _style_sidebar(self, mode):
        if not hasattr(self, "sidebar"):
            return
        dark = mode == "Dark"
        self.sidebar.configure(fg_color="#141414" if dark else "#152536")
        self.sidebar_title.configure(text_color="#f8f9fa")
        self.sidebar_caption.configure(text_color="#adb5bd")
        for key, btn in getattr(self, "nav_buttons", {}).items():
            if key == getattr(self, "_active_page", "import"):
                btn.configure(fg_color="#1d4e89", text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color="#e9ecef")

    # -- каркас вікна --------------------------------------------------
    def create_widgets(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_menubar()

        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#152536")
        self.sidebar.grid(row=0, column=0, rowspan=4, sticky="nsw")
        self.sidebar.grid_propagate(False)

        self.sidebar_title = ctk.CTkLabel(self.sidebar, text="ДМТФК+", font=("Segoe UI", 22, "bold"), text_color="#ffffff")
        self.sidebar_title.pack(anchor="w", padx=22, pady=(28, 2))
        self.sidebar_caption = ctk.CTkLabel(self.sidebar, text="Документообіг", font=("Segoe UI", 12), text_color="#adb5bd")
        self.sidebar_caption.pack(anchor="w", padx=22, pady=(0, 28))

        self.nav_buttons = {}
        nav_items = [
            ("import", "Імпорт списків"),
            ("students", "Студенти"),
            ("rewards", "Накази"),
            ("rating", "Рейтинг студентів"),
            ("teacher_rewards", "Подяки викладачів"),
            ("db", "База даних"),
        ]
        for key, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar, text=label, anchor="w", height=40, corner_radius=8,
                fg_color="transparent", hover_color="#1d4e89", text_color="#e9ecef",
                font=("Segoe UI", 14), command=lambda k=key: self.show_page(k),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = btn

        ctk.CTkFrame(self.sidebar, height=1, fg_color="#2c3e50").pack(fill="x", padx=16, pady=18)
        ctk.CTkButton(
            self.sidebar, text="Налаштування", anchor="w", height=36, corner_radius=8,
            fg_color="transparent", hover_color="#1d4e89", text_color="#e9ecef",
            command=self.open_settings,
        ).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(
            self.sidebar, text="Відкрити копію .bak", anchor="w", height=36, corner_radius=8,
            fg_color="transparent", hover_color="#1d4e89", text_color="#e9ecef",
            command=self.open_backup_view,
        ).pack(fill="x", padx=12, pady=2)

        top_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        top_frame.grid(row=0, column=1, padx=18, pady=(12, 4), sticky="ew")
        top_frame.grid_columnconfigure(2, weight=1)

        self.status_dot = ctk.CTkLabel(top_frame, text="●", text_color="#c92a2a", font=("Segoe UI", 18))
        self.status_dot.grid(row=0, column=0, padx=(4, 0))
        self.status_label = ctk.CTkLabel(top_frame, text="Немає з'єднання з БД", font=("Segoe UI", 13))
        self.status_label.grid(row=0, column=1, padx=8, sticky="w")

        actions = ctk.CTkFrame(top_frame, fg_color="transparent")
        actions.grid(row=0, column=3, sticky="e")
        ctk.CTkButton(actions, text="Експорт рейтингу", width=150, fg_color="#1d4e89", command=self.export_rating).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Зберегти копію", width=130, fg_color="#1d4e89", command=self.save_database_backup).pack(side="left", padx=4)

        self.backup_banner = ctk.CTkFrame(self, fg_color="#fff3bf", corner_radius=6)
        self.backup_banner.grid(row=1, column=1, padx=18, pady=(0, 4), sticky="ew")
        self.backup_banner_label = ctk.CTkLabel(
            self.backup_banner, text="", font=("Segoe UI", 13), text_color="#5c4b00"
        )
        self.backup_banner_label.pack(side="left", padx=12, pady=8)
        ctk.CTkButton(
            self.backup_banner, text="Закрити копію", width=130, fg_color="#e67700",
            command=self.close_backup_view,
        ).pack(side="right", padx=10, pady=6)
        self.backup_banner.grid_remove()

        self.content_host = ctk.CTkFrame(self, corner_radius=10)
        self.content_host.grid(row=2, column=1, padx=18, pady=(0, 8), sticky="nsew")
        self.content_host.grid_rowconfigure(0, weight=1)
        self.content_host.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.tab_import = self._make_page("import")
        self.tab_view_students = self._make_page("students")
        self.tab_rewards = self._make_page("rewards")
        self.tab_rating = self._make_page("rating")
        self.tab_teacher_rewards = self._make_page("teacher_rewards")
        self.tab_db = self._make_page("db")

        self.setup_import_tab()
        self.setup_view_students_tab()
        self.setup_rewards_tab()
        self.setup_rating_tab()
        self.setup_teacher_rewards_tab()
        self.setup_db_tab()
        self.show_page("import")

        self.status_bar = ctk.CTkFrame(self, height=32, corner_radius=0)
        self.status_bar.grid(row=3, column=1, sticky="ew")
        self.status_hint = ctk.CTkLabel(
            self.status_bar,
            text="F5 — оновити   ·   Двічі клацніть студента в рейтингу, щоб побачити накази",
            text_color="gray",
            font=("Segoe UI", 12),
        )
        self.status_hint.pack(side="left", padx=16, pady=6)
        self.bind("<F5>", lambda _e: self.refresh_all_views())

    def _make_page(self, key):
        frame = ctk.CTkFrame(self.content_host, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        self.pages[key] = frame
        return frame

    def show_page(self, name):
        self._active_page = name
        self.pages[name].tkraise()
        self._style_sidebar(self.app_config.get("appearance_mode", "Light"))

    def _build_menubar(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Експорт рейтингу…", command=self.export_rating)
        file_menu.add_separator()
        file_menu.add_command(label="Зберегти копію бази (.bak)…", command=self.save_database_backup)
        file_menu.add_command(label="Відкрити копію для перегляду (.bak)…", command=self.open_backup_view)
        file_menu.add_command(label="Відновити робочу базу з копії (.bak)…", command=self.restore_database_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Вихід", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)

        data_menu = tk.Menu(menubar, tearoff=0)
        data_menu.add_command(label="Оновити всі таблиці", command=self.refresh_all_views)
        data_menu.add_separator()
        data_menu.add_command(label="Очистити накази та бали…", command=self.clear_rewards_only)
        data_menu.add_command(label="Очистити всю базу…", command=self.clear_entire_database)
        menubar.add_cascade(label="Дані", menu=data_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Налаштування…", command=self.open_settings)
        menubar.add_cascade(label="Вигляд", menu=view_menu)
        self.configure(menu=menubar)

    # -- підключення до БД -----------------------------------------------
    def auto_connect(self):
        db_cfg = self.app_config["db"]
        if db_cfg.get("host") and db_cfg.get("dbname") and db_cfg.get("user"):
            self.connect_db(show_success=False)

    def open_settings(self):
        SettingsDialog(self, on_saved=self.on_settings_saved)

    def on_settings_saved(self, new_cfg):
        self.app_config = new_cfg
        self.apply_appearance(new_cfg.get("appearance_mode", "Light"))
        self.connect_db(show_success=True)

    def connect_db(self, show_success=True):
        db_cfg = self.app_config["db"]

        def work():
            new_db = database.Database(
                host=db_cfg.get("host", "localhost"),
                port=db_cfg.get("port", "5432"),
                dbname=db_cfg.get("dbname", "college_db"),
                user=db_cfg.get("user", "postgres"),
                password=db_cfg.get("password", ""),
            )
            new_db.connect()
            return new_db

        def on_success(new_db):
            if self.live_db and self.live_db is not new_db:
                try:
                    self.live_db.close()
                except Exception:
                    pass
            self.live_db = new_db
            if not getattr(self, "_viewing_backup", False):
                self.db = new_db
            self.status_dot.configure(text_color="#2b8a3e")
            self.status_label.configure(text=f"Підключено: {db_cfg.get('dbname')}@{db_cfg.get('host')}")
            if show_success:
                messagebox.showinfo("Успіх", "Підключення до бази даних успішне!")
            self.refresh_all_views()

        def on_error(exc):
            self.status_dot.configure(text_color="#c92a2a")
            self.status_label.configure(text="Немає з'єднання з БД")
            if show_success:
                messagebox.showerror("Помилка БД", f"Не вдалося підключитися:\n{exc}")

        run_async(self, work, on_success, on_error)

    def require_db(self):
        if not self.db or not self.db.is_connected():
            messagebox.showwarning("Немає з'єднання", "Спочатку підключіться до бази даних через «Налаштування».")
            return False
        return True

    def require_writable(self):
        if not self.require_db():
            return False
        if getattr(self.db, "read_only", False):
            messagebox.showwarning(
                "Лише перегляд",
                "Зараз відкрита збережена копія бази. Зміни недоступні.\nЗакрийте копію, щоб повернутися до робочої бази.",
            )
            return False
        return True

    def refresh_all_views(self):
        if not self.db or not self.db.is_connected():
            return
        self.refresh_groups_dropdown()
        self.load_rating_data()
        self.load_teacher_rewards_data()
        self.refresh_db_sidebar_tables()

    # -- обслуговування БД -------------------------------------------------
    def clear_rewards_only(self):
        if not self.require_writable():
            return
        if not messagebox.askyesno("Підтвердження", "Очистити всі збережені накази про нагородження та нараховані бали?"):
            return
        try:
            self.db.clear_rewards_and_ratings()
            messagebox.showinfo("Успіх", "Накази та бали успішно очищено!")
            self.refresh_all_views()
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    def clear_entire_database(self):
        if not self.require_writable():
            return
        if not messagebox.askyesno("Підтвердження", "УВАГА! Це повністю видалить усіх студентів, групи, накази й бали. Продовжити?"):
            return
        try:
            self.db.clear_entire_database()
            messagebox.showinfo("Успіх", "Базу даних повністю очищено!")
            self.refresh_all_views()
            self.import_textbox.delete("0.0", "end")
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    def export_rating(self):
        if not self.require_db():
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", initialfile="Рейтинг_студентів.xlsx",
            filetypes=[("Excel файли", "*.xlsx")],
        )
        if not file_path:
            return
        try:
            rating = self.db.get_rating()
            details = self.db.get_achievement_details()
            export.export_rating_to_xlsx(rating, file_path, detail_rows=details)
            messagebox.showinfo("Успіх", f"Рейтинг збережено:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Помилка експорту", str(e))

    def save_database_backup(self):
        if not self.require_writable():
            return
        stamp = datetime.now().strftime("%Y-%m-%d")
        file_path = filedialog.asksaveasfilename(
            defaultextension=".bak",
            initialfile=f"Aktiv_plus_backup_{stamp}.bak",
            filetypes=[("Копія бази ДМТФК+", "*.bak"), ("Усі файли", "*.*")],
        )
        if not file_path:
            return
        try:
            self.db.save_backup(file_path)
            messagebox.showinfo("Копію збережено", f"Поточну базу записано у файл:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Помилка копії БД", str(e))

    def restore_database_backup(self):
        if not self.require_writable():
            return
        file_path = filedialog.askopenfilename(
            filetypes=[("Копія бази ДМТФК+", "*.bak"), ("Усі файли", "*.*")],
        )
        if not file_path:
            return
        if not messagebox.askyesno(
            "Відновити базу?",
            "Поточні групи, студенти, накази й бали будуть замінені даними з копії. Продовжити?",
        ):
            return
        try:
            self.db.restore_backup(file_path)
            self.refresh_all_views()
            messagebox.showinfo("Відновлено", "Базу даних відновлено з копії.")
        except Exception as e:
            messagebox.showerror("Помилка відновлення", str(e))

    def open_backup_view(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Копія бази ДМТФК+", "*.bak"), ("Усі файли", "*.*")],
        )
        if not file_path:
            return
        try:
            snapshot = database.load_backup_snapshot(file_path)
        except Exception as e:
            messagebox.showerror("Не вдалося відкрити копію", str(e))
            return
        self.db = snapshot
        self._viewing_backup = True
        self.backup_banner_label.configure(text=f"Перегляд копії: {os.path.basename(file_path)}  (лише читання, робоча база не змінюється)")
        self.backup_banner.grid()
        self.status_dot.configure(text_color="#e67700")
        self.status_label.configure(text=f"Копія: {os.path.basename(file_path)}")
        self.refresh_all_views()
        self.show_page("rating")

    def close_backup_view(self):
        self._viewing_backup = False
        self.db = self.live_db
        self.backup_banner.grid_remove()
        if self.live_db and self.live_db.is_connected():
            db_cfg = self.app_config["db"]
            self.status_dot.configure(text_color="#2b8a3e")
            self.status_label.configure(text=f"Підключено: {db_cfg.get('dbname')}@{db_cfg.get('host')}")
            self.refresh_all_views()
        else:
            self.status_dot.configure(text_color="#c92a2a")
            self.status_label.configure(text="Немає з'єднання з БД")

    # -- вкладка «База даних» --------------------------------------------
    def setup_db_tab(self):
        self.tab_db.grid_columnconfigure(0, weight=1)
        self.tab_db.grid_rowconfigure(1, weight=1)

        ctrl_sb = ctk.CTkFrame(self.tab_db, fg_color="transparent")
        ctrl_sb.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(ctrl_sb, text="Таблиця:").pack(side="left", padx=2)
        self.db_table_dropdown = ctk.CTkOptionMenu(
            ctrl_sb, values=["(Немає таблиць)"], width=180, command=self._on_db_table_selected
        )
        self.db_table_dropdown.pack(side="left", padx=5)

        self.db_group_filter_label = ctk.CTkLabel(ctrl_sb, text="Група:")
        self.db_group_filter = ctk.CTkOptionMenu(
            ctrl_sb, values=["Усі групи"], width=160, command=lambda _: self.load_db_table_data(self.selected_db_table)
        )
        self._hide_students_filter()

        self.db_open_file_btn = ctk.CTkButton(
            ctrl_sb, text="Відкрити файл наказу", width=170, command=self.open_selected_order_file
        )
        ctk.CTkButton(
            ctrl_sb, text="Зберегти зміну", fg_color="#2b8a3e", width=140, command=self._commit_inline_edit
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            ctrl_sb, text="Скасувати", width=110, command=self._cancel_inline_edit
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            ctrl_sb, text="Додати рядок", fg_color="#1864ab", width=130, command=self.add_new_db_row
        ).pack(side="right", padx=8)
        ctk.CTkButton(
            ctrl_sb, text="Видалити рядок", fg_color="#c92a2a", width=130, command=self.delete_selected_db_row
        ).pack(side="right", padx=8)

        table_frame_sb = ctk.CTkFrame(self.tab_db)
        table_frame_sb.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        table_frame_sb.grid_columnconfigure(0, weight=1)
        table_frame_sb.grid_rowconfigure(0, weight=1)

        self.db_tree = ttk.Treeview(table_frame_sb, show="headings", selectmode="browse", style="App.Treeview")
        sb_scroll_y = ttk.Scrollbar(table_frame_sb, orient="vertical", command=self.db_tree.yview)
        sb_scroll_x = ttk.Scrollbar(table_frame_sb, orient="horizontal", command=self.db_tree.xview)
        self.db_tree.configure(yscrollcommand=sb_scroll_y.set, xscrollcommand=sb_scroll_x.set)
        self.db_tree.grid(row=0, column=0, sticky="nsew")
        sb_scroll_y.grid(row=0, column=1, sticky="ns")
        sb_scroll_x.grid(row=1, column=0, sticky="ew")
        self.db_tree.bind("<Double-1>", self.on_db_table_cell_double_click)
        self.db_tree.bind("<MouseWheel>", lambda _e: self._cancel_inline_edit())
        self._treeviews.append(self.db_tree)

        self.db_hint = ctk.CTkLabel(
            self.tab_db,
            text="Двічі клацніть клітинку, щоб редагувати. У таблиці наказів двічі клацніть «Файл наказу», щоб відкрити документ. «Додати рядок» створює нового студента, викладача або групу.",
            text_color="gray",
            wraplength=1200,
            justify="left",
        )
        self.db_hint.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.bind("<Escape>", lambda _e: self._cancel_inline_edit())

    def _on_db_table_selected(self, table_name):
        self._cancel_inline_edit()
        if hasattr(self, "db_group_filter"):
            self.db_group_filter.set("Усі групи")
        self.load_db_table_data(table_name)

    def _show_students_filter(self):
        self.db_group_filter_label.pack(side="left", padx=(18, 2))
        self.db_group_filter.pack(side="left", padx=5)

    def _hide_students_filter(self):
        self.db_group_filter_label.pack_forget()
        self.db_group_filter.pack_forget()

    def _refresh_students_group_filter(self):
        groups = ["Усі групи"]
        try:
            groups.extend([g[1] for g in self.db.get_groups()])
        except Exception:
            logger.exception("_refresh_students_group_filter")
        current = self.db_group_filter.get() if self.db_group_filter.get() in groups else "Усі групи"
        self.db_group_filter.configure(values=groups)
        self.db_group_filter.set(current)

    def refresh_db_sidebar_tables(self):
        try:
            tables = self.db.get_all_db_tables()
            display = [TABLE_LABELS.get(t, t) for t in tables]
            self._db_table_by_label = dict(zip(display, tables))
            self.db_table_dropdown.configure(values=display)
            if self.selected_db_table not in tables:
                self.selected_db_table = tables[0]
            label = TABLE_LABELS.get(self.selected_db_table, self.selected_db_table)
            self.db_table_dropdown.set(label)
            self.load_db_table_data(self.selected_db_table)
        except Exception:
            logger.exception("refresh_db_sidebar_tables")

    def load_db_table_data(self, table_name):
        self._cancel_inline_edit()
        if not table_name or "(" in table_name:
            return
        table_name = self._db_table_by_label.get(table_name, table_name) if hasattr(self, "_db_table_by_label") else table_name
        if table_name not in database.ALLOWED_TABLES:
            return
        self.selected_db_table = table_name
        if table_name == "students":
            self._refresh_students_group_filter()
            self._show_students_filter()
        else:
            self._hide_students_filter()
        if table_name == "orders":
            self.db_open_file_btn.pack(side="left", padx=10)
        else:
            self.db_open_file_btn.pack_forget()
        try:
            group_id = None
            if table_name == "students":
                current_filter = self.db_group_filter.get()
                if current_filter != "Усі групи":
                    match = next((g for g in self.db.get_groups() if g[1] == current_filter), None)
                    group_id = match[0] if match else None
            columns, rows = self.db.get_table_data(table_name, group_id=group_id)
            self._db_columns = list(columns)
            self.db_tree.configure(columns=columns)
            for col in columns:
                self.db_tree.heading(col, text=COLUMN_LABELS.get(col, col))
                self.db_tree.column(col, width=220 if col == "source_filename" else (140 if col != "id" else 60), anchor="w")
            for row in self.db_tree.get_children():
                self.db_tree.delete(row)
            for idx, r in enumerate(rows):
                tag = "odd" if idx % 2 else "even"
                self.db_tree.insert("", "end", values=r, tags=(tag,))
        except Exception as e:
            messagebox.showerror("Помилка БД", str(e))

    def add_new_db_row(self):
        self._cancel_inline_edit()
        if not self.require_writable():
            return
        if not self.selected_db_table:
            return

        if self.selected_db_table == "students":
            self._add_new_student()
        elif self.selected_db_table == "teachers":
            self._add_new_teacher()
        elif self.selected_db_table == "groups":
            self._add_new_group()
        else:
            messagebox.showinfo("Інформація", f"Додавання нових рядків для таблиці «{TABLE_LABELS.get(self.selected_db_table, self.selected_db_table)}» не підтримується через цей інтерфейс. Використовуйте імпорт з Word документів.")

    def _add_new_student(self):
        # Створюємо діалог для додавання нового студента
        dialog = ctk.CTkToplevel(self)
        dialog.title("Додати студента")
        dialog.geometry("500x400")
        dialog.grab_set()

        # Отримуємо список груп
        groups = []
        try:
            groups = self.db.get_groups()
        except Exception:
            pass

        group_names = [g[1] for g in groups] if groups else []
        group_ids = {g[1]: g[0] for g in groups} if groups else {}

        # Форма
        ctk.CTkLabel(dialog, text="ПІБ студента:", font=("Segoe UI", 12)).pack(padx=20, pady=(20, 5), anchor="w")
        name_entry = ctk.CTkEntry(dialog, width=400)
        name_entry.pack(padx=20, pady=5)

        ctk.CTkLabel(dialog, text="Група:", font=("Segoe UI", 12)).pack(padx=20, pady=(10, 5), anchor="w")
        group_dropdown = ctk.CTkOptionMenu(dialog, values=group_names or ["Немає груп"], width=400)
        group_dropdown.pack(padx=20, pady=5)
        if group_names:
            group_dropdown.set(group_names[0])

        ctk.CTkLabel(dialog, text="Фінансування:", font=("Segoe UI", 12)).pack(padx=20, pady=(10, 5), anchor="w")
        funding_entry = ctk.CTkEntry(dialog, width=400, placeholder_text="К - контракт, ДЗ - державне замовлення")
        funding_entry.pack(padx=20, pady=5)
        funding_entry.insert(0, "К")

        ctk.CTkLabel(dialog, text="Примітка:", font=("Segoe UI", 12)).pack(padx=20, pady=(10, 5), anchor="w")
        note_entry = ctk.CTkEntry(dialog, width=400, placeholder_text="Додаткова інформація")
        note_entry.pack(padx=20, pady=5)
        note_entry.insert(0, "—")

        def save_student():
            name = name_entry.get().strip()
            group_name = group_dropdown.get()
            funding = funding_entry.get().strip()
            note = note_entry.get().strip()

            if not name:
                messagebox.showerror("Помилка", "Введіть ПІБ студента")
                return
            if not group_name or group_name == "Немає груп":
                messagebox.showerror("Помилка", "Оберіть групу")
                return
            if group_name not in group_ids:
                messagebox.showerror("Помилка", "Невірна група")
                return

            try:
                group_id = group_ids[group_name]
                self.db.upsert_student(name, group_id, funding or "К", note or "—")
                self.load_db_table_data(self.selected_db_table)
                self.refresh_all_views()
                dialog.destroy()
                messagebox.showinfo("Успіх", "Студента успішно додано")
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалося додати студента: {e}")

        ctk.CTkButton(dialog, text="Зберегти", fg_color="#2b8a3e", command=save_student).pack(pady=20)
        ctk.CTkButton(dialog, text="Скасувати", command=dialog.destroy).pack(pady=5)

    def _add_new_teacher(self):
        # Створюємо діалог для додавання нового викладача
        dialog = ctk.CTkToplevel(self)
        dialog.title("Додати викладача")
        dialog.geometry("400x250")
        dialog.grab_set()

        # Форма
        ctk.CTkLabel(dialog, text="ПІБ викладача:", font=("Segoe UI", 12)).pack(padx=20, pady=(20, 5), anchor="w")
        name_entry = ctk.CTkEntry(dialog, width=350)
        name_entry.pack(padx=20, pady=5)

        def save_teacher():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Помилка", "Введіть ПІБ викладача")
                return

            try:
                self.db.upsert_teacher(name)
                self.load_db_table_data(self.selected_db_table)
                self.refresh_all_views()
                dialog.destroy()
                messagebox.showinfo("Успіх", "Викладача успішно додано")
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалося додати викладача: {e}")

        ctk.CTkButton(dialog, text="Зберегти", fg_color="#2b8a3e", command=save_teacher).pack(pady=20)
        ctk.CTkButton(dialog, text="Скасувати", command=dialog.destroy).pack(pady=5)

    def _add_new_group(self):
        # Створюємо діалог для додавання нової групи
        dialog = ctk.CTkToplevel(self)
        dialog.title("Додати групу")
        dialog.geometry("400x350")
        dialog.grab_set()

        # Форма
        ctk.CTkLabel(dialog, text="Назва групи:", font=("Segoe UI", 12)).pack(padx=20, pady=(20, 5), anchor="w")
        name_entry = ctk.CTkEntry(dialog, width=350, placeholder_text="Наприклад: ЕК-11")
        name_entry.pack(padx=20, pady=5)

        ctk.CTkLabel(dialog, text="Навчальний рік:", font=("Segoe UI", 12)).pack(padx=20, pady=(10, 5), anchor="w")
        year_entry = ctk.CTkEntry(dialog, width=350, placeholder_text="Наприклад: 2025/2026")
        year_entry.pack(padx=20, pady=5)

        ctk.CTkLabel(dialog, text="Куратор:", font=("Segoe UI", 12)).pack(padx=20, pady=(10, 5), anchor="w")
        curator_entry = ctk.CTkEntry(dialog, width=350, placeholder_text="ПІБ куратора")
        curator_entry.pack(padx=20, pady=5)
        curator_entry.insert(0, "Не вказано")

        def save_group():
            name = name_entry.get().strip()
            year = year_entry.get().strip()
            curator = curator_entry.get().strip()

            if not name:
                messagebox.showerror("Помилка", "Введіть назву групи")
                return
            if not year:
                messagebox.showerror("Помилка", "Введіть навчальний рік")
                return

            try:
                self.db.upsert_group(name, year, curator or "Не вказано")
                self.load_db_table_data(self.selected_db_table)
                self.refresh_all_views()
                dialog.destroy()
                messagebox.showinfo("Успіх", "Групу успішно додано")
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалося додати групу: {e}")

        ctk.CTkButton(dialog, text="Зберегти", fg_color="#2b8a3e", command=save_group).pack(pady=20)
        ctk.CTkButton(dialog, text="Скасувати", command=dialog.destroy).pack(pady=5)

    def delete_selected_db_row(self):
        self._cancel_inline_edit()
        if not self.require_writable():
            return
        selected_item = self.db_tree.selection()
        if not selected_item or not self.selected_db_table:
            return
        row_id = self.db_tree.item(selected_item)["values"][0]
        if not messagebox.askyesno("Підтвердження", f"Видалити рядок (ID = {row_id}) з таблиці «{TABLE_LABELS.get(self.selected_db_table, self.selected_db_table)}»?"):
            return
        try:
            self.db.delete_table_row(self.selected_db_table, row_id)
            self.load_db_table_data(self.selected_db_table)
            self.refresh_all_views()
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    def open_selected_order_file(self):
        if self.selected_db_table != "orders":
            messagebox.showinfo("Файл наказу", "Спочатку відкрийте таблицю «Накази».")
            return
        selected_item = self.db_tree.selection()
        if not selected_item:
            messagebox.showinfo("Файл наказу", "Оберіть рядок наказу.")
            return
        self.open_order_attachment(self.db_tree.item(selected_item)["values"][0])

    def open_order_attachment(self, order_id):
        if not self.require_db():
            return
        try:
            filename, blob = self.db.get_order_attachment(order_id)
            open_attachment_bytes(filename, blob)
        except Exception as e:
            messagebox.showerror("Файл наказу", str(e))

    def on_db_table_cell_double_click(self, event):
        self._cancel_inline_edit()
        item = self.db_tree.identify_row(event.y)
        column_id = self.db_tree.identify_column(event.x)
        if not item or not column_id:
            return
        columns = list(self.db_tree["columns"])
        col_index = int(column_id.replace("#", "")) - 1
        if col_index < 0 or col_index >= len(columns):
            return
        col_name = columns[col_index]
        values = list(self.db_tree.item(item)["values"])
        if col_name == "source_filename":
            self.open_order_attachment(values[0])
            return
        if col_name not in database.ALLOWED_TABLES.get(self.selected_db_table, []):
            return
        if not self.require_writable():
            return
        bbox = self.db_tree.bbox(item, column_id)
        if not bbox:
            return
        current_val = "" if values[col_index] is None else str(values[col_index])
        row_id = values[0]

        entry = ttk.Entry(self.db_tree, font=("Segoe UI", 10))
        entry.insert(0, current_val)
        entry.select_range(0, "end")
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        entry.focus_set()
        self._edit_entry = entry
        self._edit_meta = {
            "item": item,
            "col_index": col_index,
            "col_name": col_name,
            "row_id": row_id,
            "old": current_val,
        }
        entry.bind("<Return>", lambda _e: self._commit_inline_edit())
        entry.bind("<Escape>", lambda _e: self._cancel_inline_edit())
        self.db_tree.selection_set(item)

    def _cancel_inline_edit(self, event=None):
        if self._edit_entry is not None:
            try:
                self._edit_entry.destroy()
            except tk.TclError:
                pass
        self._edit_entry = None
        self._edit_meta = None

    def _commit_inline_edit(self):
        if not self._edit_entry or not self._edit_meta:
            return
        if not self.require_writable():
            self._cancel_inline_edit()
            return
        new_val = self._edit_entry.get().strip()
        old_val = self._edit_meta["old"]
        if new_val == old_val:
            self._cancel_inline_edit()
            return
        label = COLUMN_LABELS.get(self._edit_meta["col_name"], self._edit_meta["col_name"])
        if not messagebox.askyesno(
            "Підтвердити зміну",
            f"Змінити поле «{label}»?\n\nБуло: {old_val}\nСтане: {new_val}",
        ):
            self._edit_entry.focus_set()
            return
        try:
            self.db.update_table_cell(
                self.selected_db_table, self._edit_meta["col_name"], new_val, self._edit_meta["row_id"]
            )
            self._cancel_inline_edit()
            self.load_db_table_data(self.selected_db_table)
            self.refresh_all_views()
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    # -- ВКЛАДКА 1: ІМПОРТ З WORD -------------------------------------------
    def setup_import_tab(self):
        self.tab_import.grid_columnconfigure(0, weight=1)
        self.tab_import.grid_rowconfigure(1, weight=1)

        top_panel = ctk.CTkFrame(self.tab_import, fg_color="transparent")
        top_panel.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkButton(top_panel, text="Відкрити списки груп", command=self.browse_student_files).pack(side="left", padx=5)
        ctk.CTkButton(top_panel, text="Відкрити списки викладачів", command=self.browse_teacher_files).pack(side="left", padx=5)
        self.lbl_import_status = ctk.CTkLabel(top_panel, text="Оберіть один або кілька файлів Word зі списками")
        self.lbl_import_status.pack(side="left", padx=15)
        self.save_import_btn = ctk.CTkButton(top_panel, text="Зберегти в БД", fg_color="#1864ab", state="disabled", command=self.save_import_to_db)
        self.save_import_btn.pack(side="right", padx=5)

        # Збільшуємо простір для текстового поля - менше відступів
        self.import_textbox = ctk.CTkTextbox(self.tab_import, font=("Consolas", 12))
        self.import_textbox.grid(row=1, column=0, padx=10, pady=(5, 5), sticky="nsew")

    @staticmethod
    def _merge_parsed_groups(all_results):
        """Об'єднує результати парсингу кількох файлів в один словник груп,
        щоб можна було закинути одразу декілька списків за один прохід
        замість того, щоб імпортувати файли по одному."""
        merged = {}
        for data in all_results:
            for grp_name, info in data.items():
                if grp_name not in merged:
                    merged[grp_name] = {
                        "study_year": info["study_year"],
                        "curator": info["curator"],
                        "students": list(info["students"]),
                    }
                else:
                    target = merged[grp_name]
                    if target["study_year"] == "Не вказано" and info["study_year"] != "Не вказано":
                        target["study_year"] = info["study_year"]
                    if target["curator"] == "Не вказано" and info["curator"] != "Не вказано":
                        target["curator"] = info["curator"]
                    existing_names = {s["full_name"].lower() for s in target["students"]}
                    for s in info["students"]:
                        if s["full_name"].lower() not in existing_names:
                            target["students"].append(s)
                            existing_names.add(s["full_name"].lower())
        return merged

    def browse_student_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Word Documents", "*.docx;*.doc"), ("All Files", "*.*")])
        if not paths:
            return
        self.lbl_import_status.configure(text=f"Розпізнавання {len(paths)} файл(ів)...")
        self.save_import_btn.configure(state="disabled")
        self.import_type = "students"

        def work():
            results = []
            errors = []
            for path in paths:
                try:
                    results.append(parse_students_tables(path, stop_phrases=self.app_config.get("stop_phrases")))
                except Exception as e:  # не переривати весь пакет через один поганий файл
                    errors.append(f"{os.path.basename(path)}: {e}")
            merged = self._merge_parsed_groups(results)
            return merged, errors

        def on_success(result):
            data, errors = result
            self.loaded_data = data
            self.lbl_import_status.configure(text=f"Оброблено файлів: {len(paths)}")
            self.import_textbox.delete("0.0", "end")

            total_students = sum(len(g["students"]) for g in data.values())
            summary = f"Файлів оброблено: {len(paths)} | Знайдено груп: {len(data)} | Всього студентів: {total_students}\n" + "=" * 80 + "\n\n"
            for grp, info in data.items():
                summary += f"ГРУПА: {grp} | Навч. рік: {info['study_year']} | Куратор: {info['curator']}\n"
                summary += f"{'№':<4} | {'ПІБ':<35} | {'Фінанс.':<8} | {'Примітка'}\n" + "-" * 75 + "\n"
                for idx, s in enumerate(info["students"], 1):
                    summary += f"{idx:<4} | {s['full_name']:<35} | {s['funding']:<8} | {s['note']}\n"
                summary += "\n"
            self.import_textbox.insert("end", summary)
            self.save_import_btn.configure(state="normal" if data else "disabled")

            if errors:
                messagebox.showwarning("Деякі файли не оброблено", "Помилки:\n" + "\n".join(errors))
            if not data and not errors:
                messagebox.showwarning("Нічого не знайдено", "У документах не вдалося розпізнати жодної групи чи студента.")

        def on_error(exc):
            self.lbl_import_status.configure(text="Помилка розпізнавання")
            messagebox.showerror("Помилка парсингу", str(exc))

        run_async(self, work, on_success, on_error)

    def browse_teacher_files(self):
        path = filedialog.askopenfilename(filetypes=[("Word Documents", "*.docx;*.doc"), ("All Files", "*.*")])
        if not path:
            return
        self.lbl_import_status.configure(text=f"Розпізнавання: {os.path.basename(path)}...")
        self.save_import_btn.configure(state="disabled")
        self.import_type = "teachers"

        def work():
            from parsers.teachers_parser import parse_teachers_list
            teachers = parse_teachers_list(path)
            return teachers

        def on_success(teachers):
            self.loaded_teachers_data = teachers
            self.lbl_import_status.configure(text=f"Файл: {os.path.basename(path)}")
            self.import_textbox.delete("0.0", "end")

            summary = f"Знайдено викладачів: {len(teachers)}\n" + "=" * 80 + "\n\n"
            for idx, t in enumerate(teachers, 1):
                summary += f"{idx:<4} | {t['full_name']}\n"
            self.import_textbox.insert("end", summary)
            self.save_import_btn.configure(state="normal" if teachers else "disabled")

            if not teachers:
                messagebox.showwarning("Нічого не знайдено", "У документі не вдалося розпізнати жодного викладача.")

        def on_error(exc):
            self.lbl_import_status.configure(text="Помилка розпізнавання")
            messagebox.showerror("Помилка парсингу", str(exc))

        run_async(self, work, on_success, on_error)

    def save_import_to_db(self):
        if not self.require_writable():
            return

        if getattr(self, "import_type", "students") == "students":
            if not self.loaded_data:
                return

            def work():
                for grp_name, data in self.loaded_data.items():
                    group_id = self.db.upsert_group(grp_name, data["study_year"], data["curator"])
                    for s in data["students"]:
                        self.db.upsert_student(s["full_name"], group_id, s["funding"], s["note"])

            def on_success(_):
                messagebox.showinfo("Успіх", "Усі групи та списки студентів успішно збережені в базі даних!")
                self.refresh_all_views()
                self.show_page("students")

            def on_error(exc):
                messagebox.showerror("Помилка запису в БД", str(exc))

            run_async(self, work, on_success, on_error)
        else:  # teachers
            if not self.loaded_teachers_data:
                return

            def work():
                for t in self.loaded_teachers_data:
                    self.db.upsert_teacher(t["full_name"])

            def on_success(_):
                messagebox.showinfo("Успіх", "Усі викладачі успішно збережені в базі даних!")
                self.refresh_all_views()
                self.show_page("teacher_rewards")

            def on_error(exc):
                messagebox.showerror("Помилка запису в БД", str(exc))

            run_async(self, work, on_success, on_error)

    # -- ВКЛАДКА 2: СПИСКИ СТУДЕНТІВ -----------------------------------------
    def setup_view_students_tab(self):
        self.tab_view_students.grid_columnconfigure(0, weight=1)
        self.tab_view_students.grid_rowconfigure(2, weight=1)

        ctrl_frame = ctk.CTkFrame(self.tab_view_students, fg_color="transparent")
        ctrl_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(ctrl_frame, text="Оберіть групу:").pack(side="left", padx=5)
        self.group_dropdown = ctk.CTkOptionMenu(ctrl_frame, values=["(Немає груп)"], command=self.load_group_students)
        self.group_dropdown.pack(side="left", padx=5)

        self.lbl_group_info = ctk.CTkLabel(self.tab_view_students, text="Куратор: — | Навчальний рік: —", font=("Segoe UI", 13, "bold"))
        self.lbl_group_info.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        table_frame = ctk.CTkFrame(self.tab_view_students)
        table_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        columns = ("num", "id", "full_name", "funding", "note")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse", style="App.Treeview")
        for col, text, w in [("num", "№ в групі", 70), ("id", "ID", 50), ("full_name", "ПІБ Студента", 300), ("funding", "Фінансування", 110), ("note", "Примітки / Контакти / УБД", 350)]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="center" if col in ("num", "id", "funding") else "w")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._treeviews.append(self.tree)

        self._groups_cache = {}

    def refresh_groups_dropdown(self):
        try:
            groups = self.db.get_groups()  # (id, name, study_year, curator)
            self._groups_cache = {f"{g[1]} ({g[2]})": g for g in groups}
            if groups:
                values = list(self._groups_cache.keys())
                self.group_dropdown.configure(values=values)
                self.group_dropdown.set(values[0])
                self.rating_group_dropdown.configure(values=["Усі групи"] + [g[1] for g in groups])
                self.load_group_students(values[0])
            else:
                self.group_dropdown.configure(values=["(Немає груп)"])
                self.group_dropdown.set("(Немає груп)")
                for row in self.tree.get_children():
                    self.tree.delete(row)
        except Exception:
            logger.exception("refresh_groups_dropdown")

    def load_group_students(self, selection):
        if not selection or "Немає" in selection:
            return
        group = self._groups_cache.get(selection)
        if not group:
            return
        group_id, name, study_year, curator = group
        self.selected_group_id = group_id
        self.lbl_group_info.configure(text=f"Навчальний рік: {study_year} | Куратор: {curator}")
        try:
            students = self.db.get_students_by_group(group_id)
            for row in self.tree.get_children():
                self.tree.delete(row)
            for idx, s in enumerate(students, 1):
                tag = "odd" if idx % 2 == 0 else "even"
                self.tree.insert("", "end", values=(idx, s[0], s[1], s[2], s[3]), tags=(tag,))
        except Exception as e:
            messagebox.showerror("Помилка читання", str(e))

    def export_current_group(self):
        if not self.selected_group_id or not self.require_db():
            return
        selection = self.group_dropdown.get()
        group = self._groups_cache.get(selection)
        if not group:
            return
        group_id, name, study_year, curator = group
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile=f"{name}.xlsx", filetypes=[("Excel файли", "*.xlsx")])
        if not file_path:
            return
        try:
            students = self.db.get_students_by_group(group_id)
            export.export_group_to_xlsx(name, study_year, curator, students, file_path)
            messagebox.showinfo("Успіх", f"Список групи збережено:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Помилка експорту", str(e))

    # -- ВКЛАДКА 3: НАГОРОДЖЕННЯ (НАКАЗИ) -------------------------------------
    def setup_rewards_tab(self):
        self.tab_rewards.grid_columnconfigure(0, weight=1)
        self.tab_rewards.grid_rowconfigure(2, weight=1)
        self.tab_rewards.grid_rowconfigure(3, weight=1)

        top_p = ctk.CTkFrame(self.tab_rewards, fg_color="transparent")
        top_p.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(top_p, text="Відкрити наказ", command=self.browse_reward_file, fg_color="#1864ab").pack(side="left", padx=5)
        self.lbl_rew_status = ctk.CTkLabel(top_p, text="Файл не вибрано", font=("Segoe UI", 11))
        self.lbl_rew_status.pack(side="left", padx=15)
        self.save_rew_btn = ctk.CTkButton(top_p, text="Зберегти наказ та оновити бали в БД", fg_color="#2b8a3e", state="disabled", command=self.save_reward_to_db)
        self.save_rew_btn.pack(side="right", padx=5)
        self.confirm_all_btn = ctk.CTkButton(top_p, text="✅ Підтвердити всіх", fg_color="#1864ab", state="disabled", command=self.confirm_all_matches)
        self.confirm_all_btn.pack(side="right", padx=5)

        self.order_info_frame = ctk.CTkFrame(self.tab_rewards, fg_color="#e7f5ff", corner_radius=8)
        self.order_info_frame.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.order_info_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        self.lbl_ord_kind = ctk.CTkLabel(self.order_info_frame, text="Тип: —", font=("Segoe UI", 11))
        self.lbl_ord_kind.grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.lbl_ord_num = ctk.CTkLabel(self.order_info_frame, text="Номер: —", font=("Segoe UI", 11))
        self.lbl_ord_num.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.lbl_ord_date = ctk.CTkLabel(self.order_info_frame, text="Дата: —", font=("Segoe UI", 11))
        self.lbl_ord_date.grid(row=0, column=2, padx=12, pady=10, sticky="w")
        self.lbl_ord_level = ctk.CTkLabel(self.order_info_frame, text="Рівень: —", font=("Segoe UI", 11))
        self.lbl_ord_level.grid(row=0, column=3, padx=12, pady=10, sticky="w")
        self.lbl_ord_pts = ctk.CTkLabel(self.order_info_frame, text="Бали: —", font=("Segoe UI", 11))
        self.lbl_ord_pts.grid(row=0, column=4, padx=12, pady=10, sticky="w")

        # Студенти
        student_section = ctk.CTkFrame(self.tab_rewards, fg_color="#f8f9fa", corner_radius=8)
        student_section.grid(row=2, column=0, padx=10, pady=(10, 5), sticky="nsew")
        student_section.grid_columnconfigure(0, weight=1)
        student_section.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(student_section, text="Студенти", font=("Segoe UI", 13, "bold"), text_color="#1864ab").grid(row=0, column=0, padx=10, pady=(8, 4), sticky="w")
        
        rew_frame = ctk.CTkFrame(student_section, fg_color="transparent")
        rew_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        rew_frame.grid_columnconfigure(0, weight=1)
        rew_frame.grid_rowconfigure(0, weight=1)

        columns = ("num", "name", "grp", "commendation_type", "pts", "status", "action")
        self.rew_tree = ttk.Treeview(rew_frame, columns=columns, show="headings", selectmode="browse", style="App.Treeview")
        for col, text, w in [("num", "№", 40), ("name", "ПІБ Студента з наказу", 220), ("grp", "Група", 80),
                              ("commendation_type", "Тип подяки", 120), ("pts", "Бали", 55), 
                              ("status", "Найімовірніший варіант | Статус", 280), ("action", "Дія", 90)]:
            self.rew_tree.heading(col, text=text)
            self.rew_tree.column(col, width=w, anchor="center" if col in ("num", "pts", "action") else "w")

        rew_scroll = ttk.Scrollbar(rew_frame, orient="vertical", command=self.rew_tree.yview)
        self.rew_tree.configure(yscrollcommand=rew_scroll.set)
        self.rew_tree.grid(row=0, column=0, sticky="nsew")
        rew_scroll.grid(row=0, column=1, sticky="ns")
        self.rew_tree.bind("<Double-1>", self.on_reward_row_double_click)
        self._treeviews.append(self.rew_tree)

        # Викладачі
        teacher_section = ctk.CTkFrame(self.tab_rewards, fg_color="#f8f9fa", corner_radius=8)
        teacher_section.grid(row=3, column=0, padx=10, pady=(5, 10), sticky="nsew")
        teacher_section.grid_columnconfigure(0, weight=1)
        teacher_section.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(teacher_section, text="Викладачі", font=("Segoe UI", 13, "bold"), text_color="#1864ab").grid(row=0, column=0, padx=10, pady=(8, 4), sticky="w")
        
        teacher_frame = ctk.CTkFrame(teacher_section, fg_color="transparent")
        teacher_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        teacher_frame.grid_columnconfigure(0, weight=1)
        teacher_frame.grid_rowconfigure(0, weight=1)

        teacher_columns = ("t_num", "t_name", "t_status", "t_action")
        self.teacher_rew_tree = ttk.Treeview(teacher_frame, columns=teacher_columns, show="headings", selectmode="browse", style="App.Treeview")
        for col, text, w in [("t_num", "№", 40), ("t_name", "ПІБ Викладача з наказу", 300), ("t_status", "Статус", 340), ("t_action", "Дія", 90)]:
            self.teacher_rew_tree.heading(col, text=text)
            self.teacher_rew_tree.column(col, width=w, anchor="center" if col in ("t_num", "t_action") else "w")

        teacher_scroll = ttk.Scrollbar(teacher_frame, orient="vertical", command=self.teacher_rew_tree.yview)
        self.teacher_rew_tree.configure(yscrollcommand=teacher_scroll.set)
        self.teacher_rew_tree.grid(row=0, column=0, sticky="nsew")
        teacher_scroll.grid(row=0, column=1, sticky="ns")
        self.teacher_rew_tree.bind("<Double-1>", self.on_teacher_reward_row_double_click)
        self._treeviews.append(self.teacher_rew_tree)

        ctk.CTkLabel(self.tab_rewards, text="Двічі клацніть статус, щоб обрати студента або викладача вручну, або «Видалити», щоб прибрати рядок. «Підтвердити всіх» приймає найімовірніший варіант — його потім можна змінити.", text_color="gray", wraplength=1200, justify="left").grid(row=4, column=0, padx=10, pady=5, sticky="w")

    def browse_reward_file(self):
        path = filedialog.askopenfilename(filetypes=[("Word Documents", "*.docx;*.doc"), ("All Files", "*.*")])
        if not path or not self.require_db():
            return
        self.lbl_rew_status.configure(text=f"Розпізнавання: {os.path.basename(path)}...")
        self.save_rew_btn.configure(state="disabled")

        def work():
            reward_data = parse_reward_order(
                path,
                points_levels=self.app_config.get("points_levels"),
                reprimand_levels=self.app_config.get("reprimand_levels"),
            )
            db_students = self.db.get_all_students_flat()
            db_teachers = self.db.get_all_teachers()
            threshold = self.app_config.get("match_threshold", 0.72)
            reward_data["source_path"] = path

            for st in reward_data["students"]:
                match, score, candidates = matching.find_best_match(st["full_name"], st["group_name"], db_students, threshold)
                st["matched_id"] = match["id"] if match else None
                st["matched_group_id"] = match["group_id"] if match else None
                st["group_name"] = match["group_name"] if match else (st["group_name"] or "Не визначено")
                st["match_score"] = score
                st["candidates"] = candidates
                st["applied_points"] = applied_points(reward_data.get("order_kind"), reward_data["points"])
            
            # Якщо наказ є доганою - не обробляємо викладачів
            if reward_data.get("order_kind") != "reprimand":
                for teacher in reward_data.get("teachers", []):
                    # Використовуємо той самий поріг, що і для студентів
                    match, score, candidates = matching.find_best_teacher_match(teacher["full_name"], db_teachers, threshold)
                    teacher["matched_id"] = match["id"] if match else None
                    teacher["match_score"] = score
                    teacher["candidates"] = candidates
            else:
                # Очищаємо список викладачів для доган
                reward_data["teachers"] = []
            
            return reward_data

        def on_success(reward_data):
            self.loaded_reward_data = reward_data
            self.lbl_rew_status.configure(text=f"Файл: {os.path.basename(path)}")
            kind_label = "Догана" if reward_data.get("order_kind") == "reprimand" else "Подяка"
            pts_prefix = "−" if reward_data.get("order_kind") == "reprimand" else "+"
            
            # Визначаємо, чи є змішані типи подяок
            commendation_types = set()
            for st in reward_data["students"]:
                if "commendation_types" in st:
                    commendation_types.update(st["commendation_types"])
            
            if len(commendation_types) > 1:
                level_display = "змішаний"
                # Показуємо тільки одне значення балів (максимальне)
                all_points = []
                for st in reward_data["students"]:
                    if "commendation_points" in st:
                        all_points.extend(st["commendation_points"])
                if all_points:
                    pts_display = f"{pts_prefix}{format_points(max(all_points))}"
                else:
                    pts_display = f"{pts_prefix}{format_points(reward_data['points'])}"
            else:
                level_display = reward_data.get("level_type", "—")
                pts_display = f"{pts_prefix}{format_points(reward_data['points'])}"
            
            self.lbl_ord_kind.configure(text=f"Тип: {kind_label}")
            self.lbl_ord_num.configure(text=f"Номер: {reward_data['order_number']}")
            self.lbl_ord_date.configure(text=f"Дата: {reward_data['order_date']}")
            self.lbl_ord_level.configure(text=f"Рівень: {level_display}")
            self.lbl_ord_pts.configure(text=f"Бали: {pts_display}")
            self._refresh_reward_tree()
            self.save_rew_btn.configure(state="normal")
            self.confirm_all_btn.configure(state="normal")

        def on_error(exc):
            self.lbl_rew_status.configure(text="Помилка розпізнавання")
            messagebox.showerror("Помилка розпізнавання наказу", str(exc))

        run_async(self, work, on_success, on_error)

    @staticmethod
    def _status_text_for(st):
        """Формує текст статусу у форматі "Найімовірніший варіант (Група) | Статус",
        щоб користувач одразу бачив, кого саме розпізнав парсер, а не лише
        абстрактне "потрібне підтвердження"."""
        candidates = st.get("candidates") or []
        if not candidates:
            return "❌ Не знайдено жодного варіанта в базі"

        if st.get("matched_id"):
            confirmed = next((c for c in candidates if c["id"] == st["matched_id"]), None)
            label = f"{confirmed['full_name']} ({confirmed['group_name']})" if confirmed else st["full_name"]
            return f"{label} | ✅ Знайдено ({st['match_score']:.0%})"

        guess = candidates[0]
        return f"{guess['full_name']} ({guess['group_name']}) | ⚠ Потрібне підтвердження"

    def _refresh_reward_tree(self):
        for row in self.rew_tree.get_children():
            self.rew_tree.delete(row)
        if not self.loaded_reward_data:
            return
        
        is_reprimand = self.loaded_reward_data.get("order_kind") == "reprimand"
        
        # Якщо це догана, приховуємо колонку "Тип подяки"
        if is_reprimand:
            self.rew_tree.configure(columns=("num", "name", "grp", "pts", "status", "action"))
            self.rew_tree.heading("commendation_type", text="")
            self.rew_tree.column("commendation_type", width=0, stretch=False)
        else:
            self.rew_tree.configure(columns=("num", "name", "grp", "commendation_type", "pts", "status", "action"))
            self.rew_tree.heading("commendation_type", text="Тип подяки")
            self.rew_tree.column("commendation_type", width=120, anchor="center")
        
        for idx, st in enumerate(self.loaded_reward_data["students"], 1):
            status = self._status_text_for(st)
            
            if is_reprimand:
                # Для доган не показуємо тип подяки
                pts = st.get("applied_points", self.loaded_reward_data["points"])
                tag = "odd" if idx % 2 == 0 else "even"
                self.rew_tree.insert("", "end", values=(idx, st["full_name"], st["group_name"], format_points(pts), status, "Видалити"), tags=(tag,))
            else:
                # Визначаємо тип подяки та бали
                commendation_types = st.get("commendation_types", [])
                commendation_points = st.get("commendation_points", [])
                
                if len(commendation_types) > 1:
                    commendation_display = "змішані"
                    pts = sum(commendation_points) if commendation_points else st.get("applied_points", self.loaded_reward_data["points"])
                elif len(commendation_types) == 1:
                    commendation_display = commendation_types[0]
                    pts = commendation_points[0] if commendation_points else st.get("applied_points", self.loaded_reward_data["points"])
                else:
                    commendation_display = self.loaded_reward_data.get("level_type", "—")
                    pts = st.get("applied_points", self.loaded_reward_data["points"])
                
                tag = "odd" if idx % 2 == 0 else "even"
                self.rew_tree.insert("", "end", values=(idx, st["full_name"], st["group_name"], commendation_display, format_points(pts), status, "Видалити"), tags=(tag,))
        
        # Оновлюємо дерево викладачів
        self._refresh_teacher_reward_tree()

    def _refresh_teacher_reward_tree(self):
        for row in self.teacher_rew_tree.get_children():
            self.teacher_rew_tree.delete(row)
        if not self.loaded_reward_data:
            return
        teachers = self.loaded_reward_data.get("teachers", [])
        for idx, teacher in enumerate(teachers, 1):
            status = self._teacher_status_text_for(teacher)
            tag = "odd" if idx % 2 == 0 else "even"
            self.teacher_rew_tree.insert("", "end", values=(idx, teacher["full_name"], status, "Видалити"), tags=(tag,))

    @staticmethod
    def _teacher_status_text_for(teacher):
        """Формує текст статусу для викладача аналогічно до студентів.
        Формат: "Найімовірніший варіант з БД | Статус (%)" """
        candidates = teacher.get("candidates") or []
        if not candidates:
            return "❌ Не знайдено жодного варіанта в базі"

        if teacher.get("matched_id"):
            confirmed = next((c for c in candidates if c["id"] == teacher["matched_id"]), None)
            label = confirmed['full_name'] if confirmed else teacher["full_name"]
            score = teacher.get("match_score", 0.0)
            return f"{label} | ✅ Знайдено ({score:.0%})"

        guess = candidates[0]
        score = teacher.get("match_score", 0.0)
        return f"{guess['full_name']} | ⚠ Потрібне підтвердження ({score:.0%})"

    def _recompute_applied_points(self):
        data = self.loaded_reward_data
        if not data:
            return
        for st in data["students"]:
            # Якщо є індивідуальні типи подяок з різними балами - сумуємо їх
            commendation_points = st.get("commendation_points", [])
            if commendation_points:
                st["applied_points"] = sum(commendation_points)
            else:
                st["applied_points"] = applied_points(data.get("order_kind"), data["points"])

    def confirm_all_matches(self):
        """Приймає найімовірніший варіант для всіх ще непідтверджених рядків.
        Кожен рядок і надалі можна змінити вручну через подвійний клік."""
        if not self.loaded_reward_data:
            return
        confirmed_students = 0
        for st in self.loaded_reward_data["students"]:
            if not st.get("matched_id") and st.get("candidates"):
                best_guess = st["candidates"][0]
                st["matched_id"] = best_guess["id"]
                st["matched_group_id"] = best_guess["group_id"]
                st["group_name"] = best_guess["group_name"]
                confirmed_students += 1
        
        confirmed_teachers = 0
        for teacher in self.loaded_reward_data.get("teachers", []):
            if not teacher.get("matched_id") and teacher.get("candidates"):
                best_guess = teacher["candidates"][0]
                teacher["matched_id"] = best_guess["id"]
                confirmed_teachers += 1
        
        self._recompute_applied_points()
        self._refresh_reward_tree()
        
        message_parts = []
        if confirmed_students:
            message_parts.append(f"{confirmed_students} студент(ів)")
        if confirmed_teachers:
            message_parts.append(f"{confirmed_teachers} викладач(ів)")
        
        if message_parts:
            messagebox.showinfo("Підтверджено", f"Прийнято найімовірніший варіант для {', '.join(message_parts)}. Перевірте таблицю і за потреби виправте вручну.")
        else:
            messagebox.showinfo("Немає що підтверджувати", "Усі рядки вже підтверджено або не мають жодного варіанта.")

    def on_reward_row_double_click(self, event):
        selected_item = self.rew_tree.selection()
        if not selected_item or not self.loaded_reward_data:
            return
        values = self.rew_tree.item(selected_item)["values"]
        row_idx = int(values[0]) - 1
        column = self.rew_tree.identify_column(event.x)
        
        is_reprimand = self.loaded_reward_data.get("order_kind") == "reprimand"
        
        if is_reprimand:
            # Для доган: колонки без "Тип подяки"
            action_col = "#6"
            status_col = "#5"
        else:
            # Для подяок: колонки з "Тип подяки"
            action_col = "#7"
            status_col = "#6"

        if column == action_col:  # Дія / Видалити
            self.loaded_reward_data["students"].pop(row_idx)
            self._refresh_reward_tree()
            return

        if column == status_col:  # Статус / ручне підтвердження
            st = self.loaded_reward_data["students"][row_idx]
            candidates = st.get("candidates") or []

            def resolved(chosen):
                if chosen:
                    st["matched_id"] = chosen["id"]
                    st["matched_group_id"] = chosen["group_id"]
                    st["group_name"] = chosen["group_name"]
                    st["match_score"] = 1.0
                self._recompute_applied_points()
                self._refresh_reward_tree()

            MatchResolutionDialog(self, st["full_name"], candidates, resolved)

    def on_teacher_reward_row_double_click(self, event):
        selected_item = self.teacher_rew_tree.selection()
        if not selected_item or not self.loaded_reward_data:
            return
        values = self.teacher_rew_tree.item(selected_item)["values"]
        row_idx = int(values[0]) - 1
        column = self.teacher_rew_tree.identify_column(event.x)

        if column == "#4":  # Дія / Видалити
            teachers = self.loaded_reward_data.get("teachers", [])
            if 0 <= row_idx < len(teachers):
                teachers.pop(row_idx)
            self._refresh_teacher_reward_tree()
            return

        if column == "#3":  # Статус / ручне підтвердження
            teachers = self.loaded_reward_data.get("teachers", [])
            if 0 <= row_idx < len(teachers):
                teacher = teachers[row_idx]
                candidates = teacher.get("candidates") or []

                def resolved(chosen):
                    if chosen:
                        teacher["matched_id"] = chosen["id"]
                        teacher["match_score"] = 1.0
                    self._refresh_teacher_reward_tree()

                TeacherMatchResolutionDialog(self, teacher["full_name"], candidates, resolved)

    def save_reward_to_db(self):
        if not self.loaded_reward_data or not self.loaded_reward_data["students"] and not self.loaded_reward_data.get("teachers") or not self.require_writable():
            return
        unmatched = [s for s in self.loaded_reward_data["students"] if not s.get("matched_id")]
        if unmatched:
            names = ", ".join(s["full_name"] for s in unmatched[:5])
            if not messagebox.askyesno(
                "Є непідтверджені студенти",
                f"{len(unmatched)} студент(ів) не підтверджено і НЕ отримають зміни балів ({names}...). Продовжити збереження решти?",
            ):
                return

        data = self.loaded_reward_data

        def work():
            source_path = data.get("source_path")
            source_name = os.path.basename(source_path) if source_path else None
            source_bytes = None
            if source_path and os.path.isfile(source_path):
                with open(source_path, "rb") as fh:
                    source_bytes = fh.read()
            
            # Визначаємо рівень та бали для наказу
            commendation_types = set()
            for st in data["students"]:
                if "commendation_types" in st:
                    commendation_types.update(st["commendation_types"])
            
            if len(commendation_types) > 1:
                order_level = "змішаний"
                # Визначаємо діапазон балів
                all_points = []
                for st in data["students"]:
                    if "commendation_points" in st:
                        all_points.extend(st["commendation_points"])
                if all_points:
                    order_points = max(all_points)  # Зберігаємо максимальне значення
                else:
                    order_points = data["points"]
            else:
                order_level = data.get("level_type", "—")
                order_points = data["points"]
            
            order_id = self.db.upsert_order(
                data["order_number"], data["order_date"], "—",
                order_level, order_points,
                source_filename=source_name, source_file=source_bytes,
            )
            
            # Перевіряємо, чи існують вже записи для цього наказу
            # Якщо існують - це перезавантаження, видаляємо старі записи
            if self.db.has_achievements_for_order(order_id):
                self.db.delete_achievements_for_order(order_id)
            
            count = 0
            for st in data["students"]:
                if st.get("matched_id"):
                    # Обробляємо індивідуальні типи подяок
                    commendation_types = st.get("commendation_types", [])
                    commendation_points = st.get("commendation_points", [])
                    
                    if len(commendation_types) > 1:
                        # Якщо кілька типів - додаємо окремі записи для кожного типу
                        for comm_type, comm_pts in zip(commendation_types, commendation_points):
                            pts = comm_pts if comm_pts else applied_points(data.get("order_kind"), data["points"])
                            self.db.add_achievement(st["matched_id"], order_id, pts, comm_type)
                            count += 1
                    elif len(commendation_types) == 1:
                        # Один тип - зберігаємо з конкретним типом
                        pts = commendation_points[0] if commendation_points else applied_points(data.get("order_kind"), data["points"])
                        self.db.add_achievement(st["matched_id"], order_id, pts, commendation_types[0])
                        count += 1
                    else:
                        # Без типу - використовуємо загальний рівень наказу
                        pts = applied_points(data.get("order_kind"), data["points"])
                        self.db.add_achievement(st["matched_id"], order_id, pts, data.get("level_type"))
                        count += 1
            teacher_count = 0
            for teacher in data.get("teachers", []):
                if teacher.get("matched_id"):
                    self.db.add_teacher_reward(teacher["matched_id"], order_id)
                    teacher_count += 1
                # Якщо викладач не знайдений в базі - пропускаємо (не створюємо нового)
            return count, teacher_count

        def on_success(result):
            student_count, teacher_count = result
            msg = f"Наказ збережено. Оновлено бали для {student_count} студентів."
            if teacher_count > 0:
                msg += f" Додано подяки для {teacher_count} викладачів."
            messagebox.showinfo("Успіх", msg)
            self.load_rating_data()
            self.load_teacher_rewards_data()
            self.refresh_db_sidebar_tables()
            self.show_page("rating")

        def on_error(exc):
            messagebox.showerror("Помилка збереження в БД", str(exc))

        run_async(self, work, on_success, on_error)

    # -- ВКЛАДКА 5: ПОДЯКИ ВИКЛАДАЧІВ -----------------------------------------
    def setup_teacher_rewards_tab(self):
        self.tab_teacher_rewards.grid_columnconfigure(0, weight=1)
        self.tab_teacher_rewards.grid_rowconfigure(1, weight=1)

        rt_top = ctk.CTkFrame(self.tab_teacher_rewards, fg_color="transparent")
        rt_top.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(rt_top, text="Експорт у Excel", width=140, command=self.export_teacher_rewards).pack(side="left", padx=4)

        rt_frame = ctk.CTkFrame(self.tab_teacher_rewards)
        rt_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        rt_frame.grid_columnconfigure(0, weight=1)
        rt_frame.grid_rowconfigure(0, weight=1)

        columns = ("num", "name", "count", "orders")
        self.teacher_rewards_tree = ttk.Treeview(rt_frame, columns=columns, show="headings", selectmode="browse", style="App.Treeview")
        for col, text, w in [
            ("num", "№", 40), ("name", "ПІБ викладача", 360),
            ("count", "Кількість подяк", 100), ("orders", "Накази", 420),
        ]:
            self.teacher_rewards_tree.heading(col, text=text)
            self.teacher_rewards_tree.column(col, width=w, anchor="center" if col in ("num", "count") else "w")

        rt_scroll = ttk.Scrollbar(rt_frame, orient="vertical", command=self.teacher_rewards_tree.yview)
        self.teacher_rewards_tree.configure(yscrollcommand=rt_scroll.set)
        self.teacher_rewards_tree.grid(row=0, column=0, sticky="nsew")
        rt_scroll.grid(row=0, column=1, sticky="ns")
        self.teacher_rewards_tree.bind("<Double-1>", self.on_teacher_reward_open)
        self._treeviews.append(self.teacher_rewards_tree)

        ctk.CTkLabel(self.tab_teacher_rewards, text="Двічі клацніть викладача, щоб побачити подяки та відкрити файл документа.", text_color="gray").grid(row=2, column=0, padx=10, pady=5, sticky="w")

    def load_teacher_rewards_data(self):
        if not self.db or not self.db.is_connected():
            return
        try:
            stats = self.db.get_teacher_stats()
            details = self.db.get_teacher_rewards()
            by_id = {}
            for item in details:
                by_id.setdefault(item["teacher_id"], []).append(item)
            for row in self.teacher_rewards_tree.get_children():
                self.teacher_rewards_tree.delete(row)
            for idx, r in enumerate(stats, 1):
                tag = "odd" if idx % 2 else "even"
                teacher_details = by_id.get(r["teacher_id"], [])
                summary = "; ".join(f"№{item['order_number']} від {item['order_date']}" for item in teacher_details) or "—"
                self.teacher_rewards_tree.insert(
                    "", "end", iid=str(r["teacher_id"]),
                    values=(idx, r["full_name"], r["reward_count"], summary),
                    tags=(tag,),
                )
        except Exception:
            logger.exception("load_teacher_rewards_data")

    def on_teacher_reward_open(self, _event=None):
        selected = self.teacher_rewards_tree.selection()
        if not selected or not self.require_db():
            return
        teacher_id = int(selected[0])
        values = self.teacher_rewards_tree.item(selected)["values"]
        history = self.db.get_teacher_history(teacher_id)
        TeacherHistoryDialog(
            self,
            teacher_name=values[1],
            reward_count=values[2],
            history=history,
            open_file_fn=self.open_order_attachment,
        )

    def export_teacher_rewards(self):
        if not self.require_db():
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", initialfile="Подяки_викладачів.xlsx",
            filetypes=[("Excel файли", "*.xlsx")],
        )
        if not file_path:
            return
        try:
            stats = self.db.get_teacher_stats()
            details = self.db.get_teacher_rewards()
            export.export_teacher_rewards_to_xlsx(stats, file_path, detail_rows=details)
            messagebox.showinfo("Успіх", f"Подяки викладачів збережено:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Помилка експорту", str(e))

    # -- ВКЛАДКА 6: РЕЙТИНГ СТУДЕНТІВ ----------------------------------------
    def setup_rating_tab(self):
        self.tab_rating.grid_columnconfigure(0, weight=1)
        self.tab_rating.grid_rowconfigure(1, weight=1)

        rt_top = ctk.CTkFrame(self.tab_rating, fg_color="transparent")
        rt_top.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkLabel(rt_top, text="Фільтр за групою:").pack(side="left", padx=5)
        self.rating_group_dropdown = ctk.CTkOptionMenu(rt_top, values=["Усі групи"], command=lambda _: self.load_rating_data())
        self.rating_group_dropdown.pack(side="left", padx=5)

        rt_frame = ctk.CTkFrame(self.tab_rating)
        rt_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        rt_frame.grid_columnconfigure(0, weight=1)
        rt_frame.grid_rowconfigure(0, weight=1)

        columns = ("place", "name", "grp", "total_pts", "orders")
        self.rating_tree = ttk.Treeview(rt_frame, columns=columns, show="headings", selectmode="browse", style="App.Treeview")
        for col, text, w in [
            ("place", "Місце", 70), ("name", "ПІБ студента", 260), ("grp", "Група", 90),
            ("total_pts", "Бали", 80), ("orders", "Накази", 420),
        ]:
            self.rating_tree.heading(col, text=text)
            self.rating_tree.column(col, width=w, anchor="center" if col in ("place", "grp", "total_pts") else "w")

        rt_scroll = ttk.Scrollbar(rt_frame, orient="vertical", command=self.rating_tree.yview)
        self.rating_tree.configure(yscrollcommand=rt_scroll.set)
        self.rating_tree.grid(row=0, column=0, sticky="nsew")
        rt_scroll.grid(row=0, column=1, sticky="ns")
        self.rating_tree.bind("<Double-1>", self.on_rating_student_open)
        self._treeviews.append(self.rating_tree)

        ctk.CTkLabel(self.tab_rating, text="Двічі клацніть студента, щоб побачити накази, бали та відкрити файл документа.", text_color="gray").grid(row=2, column=0, padx=10, pady=5, sticky="w")

    def load_rating_data(self):
        if not self.db or not self.db.is_connected():
            return
        try:
            current_filter = self.rating_group_dropdown.get()
            group_id = None
            if current_filter != "Усі групи":
                match = next((g for g in self._groups_cache.values() if g[1] == current_filter), None)
                group_id = match[0] if match else None

            rows = self.db.get_rating(group_id)
            details = self.db.get_achievement_details()
            by_id = {}
            for item in details:
                by_id.setdefault(item["student_id"], []).append(item)
            for row in self.rating_tree.get_children():
                self.rating_tree.delete(row)
            for idx, r in enumerate(rows, 1):
                tag = "odd" if idx % 2 == 0 else "even"
                
                # Формуємо опис наказів з урахуванням змішаних типів
                summaries = []
                for item in by_id.get(r["student_id"], []):
                    if "commendation_types" in item and len(item["commendation_types"]) > 1:
                        # Для змішаних типів показуємо просто "змішані"
                        summary = f"№{item['order_number']} від {item['order_date']} (змішані, {format_points(item['points'])})"
                    else:
                        summary = format_achievement_line(item)
                    summaries.append(summary)
                
                summary_text = "; ".join(summaries) if summaries else "—"
                self.rating_tree.insert(
                    "", "end", iid=str(r["student_id"]),
                    values=(idx, r["full_name"], r["group_name"], format_points(r["total"]), summary_text),
                    tags=(tag,),
                )
        except Exception:
            logger.exception("load_rating_data")

    def on_rating_student_open(self, _event=None):
        selected = self.rating_tree.selection()
        if not selected or not self.require_db():
            return
        student_id = int(selected[0])
        values = self.rating_tree.item(selected)["values"]
        history = self.db.get_student_history(student_id)
        StudentHistoryDialog(
            self,
            student_name=values[1],
            group_name=values[2],
            total_points=values[3],
            history=history,
            open_file_fn=self.open_order_attachment,
        )


if __name__ == "__main__":
    app = StudentManagementApp()
    app.mainloop()
