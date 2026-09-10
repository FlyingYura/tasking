import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

import config as cfg
import database
import export
import matching
from parsers.reward_parser import parse_reward_order
from parsers.students_parser import parse_students_tables
from scoring import applied_points, format_points

logging.basicConfig(
    filename=os.path.join(os.path.expanduser("~"), "doc_flow_app.log"),
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
    "event_title": "Захід / підстава",
    "level_type": "Рівень",
    "default_points": "Бали наказу",
    "student_id": "ID студента",
    "order_id": "ID наказу",
    "points_awarded": "Нараховані бали",
}

TABLE_LABELS = {
    "groups": "Групи",
    "students": "Студенти",
    "orders": "Накази",
    "achievements": "Нарахування балів",
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
    """Діалог налаштувань: параметри підключення до БД та рівні балів.
    Раніше поля host/port/dbname/user/password були завжди видимі
    у верхній панелі головного вікна — незручно й зайве для працівника
    деканату, який відкриває програму щодня. Тепер вони ховаються тут
    і підвантажуються автоматично при старті."""

    def __init__(self, master, on_saved):
        super().__init__(master)
        self.title("Налаштування")
        self.geometry("580x620")
        self.minsize(520, 520)
        self.grab_set()
        self.on_saved = on_saved
        self.cfg = cfg.load_config()

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=15, pady=15)
        tab_ui = tabs.add("Інтерфейс")
        tab_db = tabs.add("Підключення до БД")
        tab_levels = tabs.add("Подяки / бали")
        tab_reprimands = tabs.add("Догани / бали")

        ctk.CTkLabel(tab_ui, text="Тема оформлення", font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=10, pady=(16, 8)
        )
        current_theme = self.cfg.get("appearance_mode", "Light")
        theme_label = "Темна" if current_theme == "Dark" else "Світла"
        self.theme_var = ctk.StringVar(value=theme_label)
        self.theme_switch = ctk.CTkSegmentedButton(
            tab_ui,
            values=["Світла", "Темна"],
            variable=self.theme_var,
            command=self._preview_theme,
            width=240,
        )
        self.theme_switch.pack(anchor="w", padx=10)
        ctk.CTkLabel(
            tab_ui,
            text="Світла тема встановлена за замовчуванням.\nЗміну можна зробити будь-коли — вона збережеться після «Зберегти».",
            text_color="gray",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(8, 0))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        db = self.cfg["db"]
        self.entries = {}
        for row, (key, label) in enumerate([
            ("host", "Хост"), ("port", "Порт"), ("dbname", "Назва БД"),
            ("user", "Користувач"), ("password", "Пароль"),
        ]):
            ctk.CTkLabel(tab_db, text=label).grid(row=row, column=0, padx=10, pady=8, sticky="w")
            show = "*" if key == "password" else ""
            entry = ctk.CTkEntry(tab_db, width=240, show=show)
            entry.insert(0, str(db.get(key, "")))
            entry.grid(row=row, column=1, padx=10, pady=8)
            self.entries[key] = entry

        ctk.CTkLabel(
            tab_db,
            text="Пароль зберігається локально у файлі профілю користувача.\n"
                 "Для спільного/публічного комп'ютера рекомендовано\n"
                 "не зберігати пароль і вводити його щоразу.",
            text_color="gray", justify="left",
        ).grid(row=6, column=0, columnspan=2, padx=10, pady=(15, 0), sticky="w")

        ctk.CTkLabel(tab_levels, text="Ключові слова у тексті наказу → рівень і бали подяки:").pack(
            anchor="w", padx=10, pady=(10, 5)
        )
        self.level_rows = []
        levels_frame = ctk.CTkFrame(tab_levels, fg_color="transparent")
        levels_frame.pack(fill="x", padx=10)
        for level in self.cfg["points_levels"]:
            self._add_level_row(self.level_rows, levels_frame, level)

        ctk.CTkButton(
            tab_levels, text="+ Додати рівень",
            command=lambda: self._add_level_row(self.level_rows, levels_frame, {"keywords": [], "label": "", "points": 1}),
        ).pack(padx=10, pady=10, anchor="w")

        ctk.CTkLabel(
            tab_reprimands,
            text="Ключові слова у тексті наказу → рівень і бали догани\n"
                 "(віднімаються лише якщо в студента вже є бали в рейтингу):",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(10, 5))
        self.reprimand_rows = []
        reprimand_frame = ctk.CTkFrame(tab_reprimands, fg_color="transparent")
        reprimand_frame.pack(fill="x", padx=10)
        for level in self.cfg.get("reprimand_levels") or cfg.DEFAULT_CONFIG["reprimand_levels"]:
            self._add_level_row(self.reprimand_rows, reprimand_frame, level)

        ctk.CTkButton(
            tab_reprimands, text="+ Додати рівень",
            command=lambda: self._add_level_row(self.reprimand_rows, reprimand_frame, {"keywords": [], "label": "", "points": 0.5}),
        ).pack(padx=10, pady=10, anchor="w")

        save_btn = ctk.CTkButton(self, text="Зберегти", fg_color="#2b8a3e", command=self.save)
        save_btn.pack(pady=(0, 15))

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


class StudentManagementApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("DocFlow — документообіг")
        self.minsize(1100, 700)

        self.app_config = cfg.load_config()
        ctk.set_appearance_mode(self.app_config.get("appearance_mode", "Light"))
        self.db: database.Database | None = None

        self.loaded_data = None
        self.loaded_reward_data = None
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
        for tree in getattr(self, "_treeviews", []):
            try:
                tree.tag_configure("odd", background="#f8f9fa" if mode != "Dark" else "#252525")
                tree.tag_configure("even", background="#ffffff" if mode != "Dark" else "#1e1e1e")
            except tk.TclError:
                pass

    # -- каркас вікна --------------------------------------------------
    def create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_menubar()

        top_frame = ctk.CTkFrame(self, corner_radius=8)
        top_frame.grid(row=0, column=0, padx=16, pady=(12, 8), sticky="ew")
        top_frame.grid_columnconfigure(2, weight=1)

        self.status_dot = ctk.CTkLabel(top_frame, text="●", text_color="#c92a2a", font=("Segoe UI", 18))
        self.status_dot.grid(row=0, column=0, padx=(14, 0), pady=10)
        self.status_label = ctk.CTkLabel(top_frame, text="Немає з'єднання з БД", font=("Segoe UI", 13))
        self.status_label.grid(row=0, column=1, padx=8, sticky="w")

        actions = ctk.CTkFrame(top_frame, fg_color="transparent")
        actions.grid(row=0, column=3, padx=8, pady=8, sticky="e")
        ctk.CTkButton(actions, text="Оновити", width=100, command=self.refresh_all_views).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Експорт рейтингу", width=150, command=self.export_rating).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Налаштування", width=130, command=self.open_settings).pack(side="left", padx=4)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=16, pady=(0, 6), sticky="nsew")

        self.tab_import = self.tabview.add("Імпорт")
        self.tab_view_students = self.tabview.add("Студенти")
        self.tab_rewards = self.tabview.add("Накази")
        self.tab_rating = self.tabview.add("Рейтинг")
        self.tab_db = self.tabview.add("База даних")

        self.setup_import_tab()
        self.setup_view_students_tab()
        self.setup_rewards_tab()
        self.setup_rating_tab()
        self.setup_db_tab()

        self.status_bar = ctk.CTkFrame(self, height=32, corner_radius=0)
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        self.status_hint = ctk.CTkLabel(
            self.status_bar,
            text="F5 — оновити дані   ·   Накази: подяки та догани розпізнаються автоматично",
            text_color="gray",
            font=("Segoe UI", 12),
        )
        self.status_hint.pack(side="left", padx=16, pady=6)
        self.bind("<F5>", lambda _e: self.refresh_all_views())

    def _build_menubar(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Експорт рейтингу…", command=self.export_rating)
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
            if self.db:
                self.db.close()
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

    def refresh_all_views(self):
        if not self.db or not self.db.is_connected():
            return
        self.refresh_groups_dropdown()
        self.load_rating_data()
        self.refresh_db_sidebar_tables()

    # -- обслуговування БД -------------------------------------------------
    def clear_rewards_only(self):
        if not self.require_db():
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
        if not self.require_db():
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
            export.export_rating_to_xlsx(rating, file_path)
            messagebox.showinfo("Успіх", f"Рейтинг збережено:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Помилка експорту", str(e))

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

        ctk.CTkButton(
            ctrl_sb, text="Зберегти зміну", fg_color="#2b8a3e", width=140, command=self._commit_inline_edit
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            ctrl_sb, text="Скасувати", width=110, command=self._cancel_inline_edit
        ).pack(side="right", padx=4)
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
            text="Двічі клацніть клітинку, щоб редагувати її прямо в таблиці. Enter або «Зберегти зміну» — підтвердити, Esc — скасувати.",
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
                self.db_tree.column(col, width=140 if col != "id" else 60, anchor="w")
            for row in self.db_tree.get_children():
                self.db_tree.delete(row)
            for idx, r in enumerate(rows):
                tag = "odd" if idx % 2 else "even"
                self.db_tree.insert("", "end", values=r, tags=(tag,))
        except Exception as e:
            messagebox.showerror("Помилка БД", str(e))

    def delete_selected_db_row(self):
        self._cancel_inline_edit()
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
        if col_name not in database.ALLOWED_TABLES.get(self.selected_db_table, []):
            return
        bbox = self.db_tree.bbox(item, column_id)
        if not bbox:
            return
        values = list(self.db_tree.item(item)["values"])
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
        self.lbl_import_status = ctk.CTkLabel(top_panel, text="Оберіть один або кілька файлів Word зі списками груп")
        self.lbl_import_status.pack(side="left", padx=15)
        self.save_import_btn = ctk.CTkButton(top_panel, text="Створити групи та зберегти в БД", fg_color="#1864ab", state="disabled", command=self.save_parsed_to_db)
        self.save_import_btn.pack(side="right", padx=5)

        self.import_textbox = ctk.CTkTextbox(self.tab_import, font=("Consolas", 12))
        self.import_textbox.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

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

    def save_parsed_to_db(self):
        if not self.loaded_data or not self.require_db():
            return

        def work():
            for grp_name, data in self.loaded_data.items():
                group_id = self.db.upsert_group(grp_name, data["study_year"], data["curator"])
                for s in data["students"]:
                    self.db.upsert_student(s["full_name"], group_id, s["funding"], s["note"])

        def on_success(_):
            messagebox.showinfo("Успіх", "Усі групи та списки студентів успішно збережені в базі даних!")
            self.refresh_all_views()
            self.tabview.set("Студенти")

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
        ctk.CTkButton(ctrl_frame, text="Оновити", width=90, command=self.refresh_all_views).pack(side="left", padx=10)
        ctk.CTkButton(ctrl_frame, text="Експорт групи (.xlsx)", width=150, command=self.export_current_group).pack(side="left", padx=10)

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

        top_p = ctk.CTkFrame(self.tab_rewards, fg_color="transparent")
        top_p.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(top_p, text="Відкрити наказ", command=self.browse_reward_file).pack(side="left", padx=5)
        self.lbl_rew_status = ctk.CTkLabel(top_p, text="Файл не вибрано")
        self.lbl_rew_status.pack(side="left", padx=15)
        self.save_rew_btn = ctk.CTkButton(top_p, text="Зберегти наказ та оновити бали в БД", fg_color="#1864ab", state="disabled", command=self.save_reward_to_db)
        self.save_rew_btn.pack(side="right", padx=5)
        self.confirm_all_btn = ctk.CTkButton(top_p, text="✅ Підтвердити всіх", fg_color="#2b8a3e", state="disabled", command=self.confirm_all_matches)
        self.confirm_all_btn.pack(side="right", padx=5)

        self.order_info_frame = ctk.CTkFrame(self.tab_rewards)
        self.order_info_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.order_info_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        self.lbl_ord_kind = ctk.CTkLabel(self.order_info_frame, text="Тип: —")
        self.lbl_ord_kind.grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.lbl_ord_num = ctk.CTkLabel(self.order_info_frame, text="Номер: —")
        self.lbl_ord_num.grid(row=0, column=1, padx=10, pady=8, sticky="w")
        self.lbl_ord_date = ctk.CTkLabel(self.order_info_frame, text="Дата: —")
        self.lbl_ord_date.grid(row=0, column=2, padx=10, pady=8, sticky="w")
        self.lbl_ord_level = ctk.CTkLabel(self.order_info_frame, text="Рівень: —")
        self.lbl_ord_level.grid(row=0, column=3, padx=10, pady=8, sticky="w")
        self.lbl_ord_pts = ctk.CTkLabel(self.order_info_frame, text="Бали: —")
        self.lbl_ord_pts.grid(row=0, column=4, padx=10, pady=8, sticky="w")

        rew_frame = ctk.CTkFrame(self.tab_rewards)
        rew_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        rew_frame.grid_columnconfigure(0, weight=1)
        rew_frame.grid_rowconfigure(0, weight=1)

        columns = ("num", "name", "grp", "pts", "status", "action")
        self.rew_tree = ttk.Treeview(rew_frame, columns=columns, show="headings", selectmode="browse", style="App.Treeview")
        for col, text, w in [("num", "№", 40), ("name", "ПІБ Студента з наказу", 220), ("grp", "Група", 80),
                              ("pts", "Бали", 55), ("status", "Найімовірніший варіант | Статус", 340), ("action", "Дія", 90)]:
            self.rew_tree.heading(col, text=text)
            self.rew_tree.column(col, width=w, anchor="center" if col in ("num", "pts", "action") else "w")

        rew_scroll = ttk.Scrollbar(rew_frame, orient="vertical", command=self.rew_tree.yview)
        self.rew_tree.configure(yscrollcommand=rew_scroll.set)
        self.rew_tree.grid(row=0, column=0, sticky="nsew")
        rew_scroll.grid(row=0, column=1, sticky="ns")
        self.rew_tree.bind("<Double-1>", self.on_reward_row_double_click)
        self._treeviews.append(self.rew_tree)

        ctk.CTkLabel(self.tab_rewards, text="Двічі клацніть статус, щоб обрати студента вручну, або «Видалити», щоб прибрати рядок. «Підтвердити всіх» приймає найімовірніший варіант — його потім можна змінити.", text_color="gray", wraplength=1200, justify="left").grid(row=3, column=0, padx=10, pady=5, sticky="w")

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
            threshold = self.app_config.get("match_threshold", 0.72)
            totals = self.db.get_student_totals() if reward_data.get("order_kind") == "reprimand" else {}

            for st in reward_data["students"]:
                match, score, candidates = matching.find_best_match(st["full_name"], st["group_name"], db_students, threshold)
                st["matched_id"] = match["id"] if match else None
                st["matched_group_id"] = match["group_id"] if match else None
                st["group_name"] = match["group_name"] if match else (st["group_name"] or "Не визначено")
                st["match_score"] = score
                st["candidates"] = candidates
                current = totals.get(st["matched_id"], 0) if st.get("matched_id") else 0
                st["applied_points"] = applied_points(reward_data.get("order_kind"), reward_data["points"], current)
            return reward_data

        def on_success(reward_data):
            self.loaded_reward_data = reward_data
            self.lbl_rew_status.configure(text=f"Файл: {os.path.basename(path)}")
            kind_label = "Догана" if reward_data.get("order_kind") == "reprimand" else "Подяка"
            pts_prefix = "−" if reward_data.get("order_kind") == "reprimand" else "+"
            self.lbl_ord_kind.configure(text=f"Тип: {kind_label}")
            self.lbl_ord_num.configure(text=f"Номер: {reward_data['order_number']}")
            self.lbl_ord_date.configure(text=f"Дата: {reward_data['order_date']}")
            self.lbl_ord_level.configure(text=f"Рівень: {reward_data['level_type']}")
            self.lbl_ord_pts.configure(text=f"Бали: {pts_prefix}{format_points(reward_data['points'])}")
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
        for idx, st in enumerate(self.loaded_reward_data["students"], 1):
            status = self._status_text_for(st)
            pts = st.get("applied_points", self.loaded_reward_data["points"])
            tag = "odd" if idx % 2 == 0 else "even"
            self.rew_tree.insert("", "end", values=(idx, st["full_name"], st["group_name"], format_points(pts), status, "Видалити"), tags=(tag,))

    def _recompute_applied_points(self):
        data = self.loaded_reward_data
        if not data:
            return
        totals = {}
        if data.get("order_kind") == "reprimand" and self.db and self.db.is_connected():
            totals = self.db.get_student_totals()
        for st in data["students"]:
            current = totals.get(st["matched_id"], 0) if st.get("matched_id") else 0
            st["applied_points"] = applied_points(data.get("order_kind"), data["points"], current)

    def confirm_all_matches(self):
        """Приймає найімовірніший варіант для всіх ще непідтверджених рядків.
        Кожен рядок і надалі можна змінити вручну через подвійний клік."""
        if not self.loaded_reward_data:
            return
        confirmed_count = 0
        for st in self.loaded_reward_data["students"]:
            if not st.get("matched_id") and st.get("candidates"):
                best_guess = st["candidates"][0]
                st["matched_id"] = best_guess["id"]
                st["matched_group_id"] = best_guess["group_id"]
                st["group_name"] = best_guess["group_name"]
                confirmed_count += 1
        self._recompute_applied_points()
        self._refresh_reward_tree()
        if confirmed_count:
            messagebox.showinfo("Підтверджено", f"Прийнято найімовірніший варіант для {confirmed_count} студент(ів). Перевірте таблицю і за потреби виправте вручну.")
        else:
            messagebox.showinfo("Немає що підтверджувати", "Усі рядки вже підтверджено або не мають жодного варіанта.")

    def on_reward_row_double_click(self, event):
        selected_item = self.rew_tree.selection()
        if not selected_item or not self.loaded_reward_data:
            return
        values = self.rew_tree.item(selected_item)["values"]
        row_idx = int(values[0]) - 1
        column = self.rew_tree.identify_column(event.x)

        if column == "#6":  # Дія / Видалити
            self.loaded_reward_data["students"].pop(row_idx)
            self._refresh_reward_tree()
            return

        if column == "#5":  # Статус / ручне підтвердження
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

    def save_reward_to_db(self):
        if not self.loaded_reward_data or not self.loaded_reward_data["students"] or not self.require_db():
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
            order_id = self.db.upsert_order(data["order_number"], data["order_date"], data["event_title"], data["level_type"], data["points"])
            totals = self.db.get_student_totals() if data.get("order_kind") == "reprimand" else {}
            count = 0
            for st in data["students"]:
                if st.get("matched_id"):
                    current = totals.get(st["matched_id"], 0)
                    pts = applied_points(data.get("order_kind"), data["points"], current)
                    self.db.add_achievement(st["matched_id"], order_id, pts)
                    count += 1
            return count

        def on_success(count):
            messagebox.showinfo("Успіх", f"Наказ збережено. Оновлено бали для {count} студентів.")
            self.load_rating_data()
            self.refresh_db_sidebar_tables()
            self.tabview.set("Рейтинг")

        def on_error(exc):
            messagebox.showerror("Помилка збереження в БД", str(exc))

        run_async(self, work, on_success, on_error)

    # -- ВКЛАДКА 4: РЕЙТИНГ СТУДЕНТІВ ----------------------------------------
    def setup_rating_tab(self):
        self.tab_rating.grid_columnconfigure(0, weight=1)
        self.tab_rating.grid_rowconfigure(1, weight=1)

        rt_top = ctk.CTkFrame(self.tab_rating, fg_color="transparent")
        rt_top.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkLabel(rt_top, text="Фільтр за групою:").pack(side="left", padx=5)
        self.rating_group_dropdown = ctk.CTkOptionMenu(rt_top, values=["Усі групи"], command=lambda _: self.load_rating_data())
        self.rating_group_dropdown.pack(side="left", padx=5)
        ctk.CTkButton(rt_top, text="Оновити", width=110, command=self.load_rating_data).pack(side="left", padx=8)
        ctk.CTkButton(rt_top, text="Експорт у Excel", width=140, command=self.export_rating).pack(side="left", padx=4)

        rt_frame = ctk.CTkFrame(self.tab_rating)
        rt_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        rt_frame.grid_columnconfigure(0, weight=1)
        rt_frame.grid_rowconfigure(0, weight=1)

        columns = ("place", "name", "grp", "total_pts")
        self.rating_tree = ttk.Treeview(rt_frame, columns=columns, show="headings", selectmode="browse", style="App.Treeview")
        for col, text, w in [("place", "Місце", 70), ("name", "ПІБ студента", 330), ("grp", "Група", 120), ("total_pts", "Загалом балів", 120)]:
            self.rating_tree.heading(col, text=text)
            self.rating_tree.column(col, width=w, anchor="center" if col != "name" else "w")

        rt_scroll = ttk.Scrollbar(rt_frame, orient="vertical", command=self.rating_tree.yview)
        self.rating_tree.configure(yscrollcommand=rt_scroll.set)
        self.rating_tree.grid(row=0, column=0, sticky="nsew")
        rt_scroll.grid(row=0, column=1, sticky="ns")
        self._treeviews.append(self.rating_tree)

        ctk.CTkLabel(self.tab_rating, text="Загальний рейтинг або фільтр по групі. Експорт створює Excel з аркушем «Загальний рейтинг» і окремим аркушем для кожної групи.", text_color="gray").grid(row=2, column=0, padx=10, pady=5, sticky="w")

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
            for row in self.rating_tree.get_children():
                self.rating_tree.delete(row)
            for idx, r in enumerate(rows, 1):
                tag = "odd" if idx % 2 == 0 else "even"
                self.rating_tree.insert("", "end", values=(idx, r["full_name"], r["group_name"], format_points(r["total"])), tags=(tag,))
        except Exception:
            logger.exception("load_rating_data")


if __name__ == "__main__":
    app = StudentManagementApp()
    app.mainloop()
