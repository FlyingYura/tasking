import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
import psycopg2

import database
from table_parser import parse_students_tables
from reward_parser import parse_reward_order

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class StudentManagementApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Автоматизація документообігу — Коледж (Студенти, Накази, Рейтинг, СЕРЕДОВИЩЕ БД)")
        self.geometry("1450x850")
        self.minsize(1100, 700)

        self.loaded_data = None
        self.loaded_reward_data = None
        self.selected_group_table = None
        self.selected_db_table = None

        self.create_widgets()

    def create_widgets(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)  # Правий сайдбар для бази даних
        self.grid_rowconfigure(1, weight=1)

        # Верхня панель підключення та звітів
        db_frame = ctk.CTkFrame(self)
        db_frame.grid(row=0, column=0, columnspan=2, padx=15, pady=10, sticky="ew")

        ctk.CTkLabel(db_frame, text="Хост:").grid(row=0, column=0, padx=3, pady=8)
        self.host_entry = ctk.CTkEntry(db_frame, width=65)
        self.host_entry.insert(0, "localhost")
        self.host_entry.grid(row=0, column=1, padx=3, pady=8)

        ctk.CTkLabel(db_frame, text="Порт:").grid(row=0, column=2, padx=3, pady=8)
        self.port_entry = ctk.CTkEntry(db_frame, width=40)
        self.port_entry.insert(0, "5432")
        self.port_entry.grid(row=0, column=3, padx=3, pady=8)

        ctk.CTkLabel(db_frame, text="БД:").grid(row=0, column=4, padx=3, pady=8)
        self.dbname_entry = ctk.CTkEntry(db_frame, width=65)
        self.dbname_entry.insert(0, "college_db")
        self.dbname_entry.grid(row=0, column=5, padx=3, pady=8)

        ctk.CTkLabel(db_frame, text="Користувач:").grid(row=0, column=6, padx=3, pady=8)
        self.user_entry = ctk.CTkEntry(db_frame, width=65)
        self.user_entry.insert(0, "postgres")
        self.user_entry.grid(row=0, column=7, padx=3, pady=8)

        ctk.CTkLabel(db_frame, text="Пароль:").grid(row=0, column=8, padx=3, pady=8)
        self.pass_entry = ctk.CTkEntry(db_frame, width=65, show="*")
        self.pass_entry.grid(row=0, column=9, padx=3, pady=8)

        connect_btn = ctk.CTkButton(db_frame, text="Підключитися", fg_color="#2b8a3e", width=90, command=self.test_connection)
        connect_btn.grid(row=0, column=10, padx=4, pady=8)

        save_report_btn = ctk.CTkButton(db_frame, text="💾 Звітність-2026/2027", fg_color="#1864ab", width=140, command=self.save_database_backup)
        save_report_btn.grid(row=0, column=11, padx=4, pady=8)

        clear_rewards_btn = ctk.CTkButton(db_frame, text="Очистити накази/бали", fg_color="#e8590c", width=120, command=self.clear_rewards_only)
        clear_rewards_btn.grid(row=0, column=12, padx=4, pady=8)

        clear_db_btn = ctk.CTkButton(db_frame, text="Очистити всю БД", fg_color="#c92a2a", width=105, command=self.clear_entire_database)
        clear_db_btn.grid(row=0, column=13, padx=4, pady=8)

        # Ліва частина — головні вкладки програми
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=(15, 5), pady=(0, 15), sticky="nsew")

        self.tab_import = self.tabview.add("Імпорт списків з Word")
        self.tab_crud = self.tabview.add("Керування студентами (CRUD)")
        self.tab_rewards = self.tabview.add("Нагородження (Накази)")
        self.tab_rating = self.tabview.add("Рейтинг студентів")

        self.setup_import_tab()
        self.setup_crud_tab()
        self.setup_rewards_tab()
        self.setup_rating_tab()

        # Права частина — окремий розділ «База даних» (середовище БД)
        self.setup_database_environment_sidebar()

    def get_db_connection(self):
        return psycopg2.connect(
            host=self.host_entry.get().strip(),
            port=self.port_entry.get().strip(),
            database=self.dbname_entry.get().strip(),
            user=self.user_entry.get().strip(),
            password=self.pass_entry.get().strip()
        )

    def test_connection(self):
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            database.init_core_registry(cursor)
            conn.commit()
            cursor.close()
            conn.close()
            messagebox.showinfo("Успіх", "Підключення до БД успішне!")
            self.refresh_all_views()
        except Exception as e:
            messagebox.showerror("Помилка БД", f"Не вдалося підключитися:\n{e}")

    def save_database_backup(self):
        """Зберігає поточну версію бази даних як звіт/резервну копію (дамп)."""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".sql",
            initialfile="Звітність-2026_2027.sql",
            filetypes=[("SQL Dump Files", "*.sql"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        try:
            db_name = self.dbname_entry.get().strip()
            user = self.user_entry.get().strip()
            host = self.host_entry.get().strip()
            port = self.port_entry.get().strip()
            password = self.pass_entry.get().strip()

            # Використовуємо системну утиліту pg_dump для створення бэкапу
            env = os.environ.copy()
            if password:
                env["PGPASSWORD"] = password

            import subprocess
            pg_dump_path = "pg_dump"  # Має бути в PATH або прописаний шлях
            cmd = [pg_dump_path, "-h", host, "-p", port, "-U", user, "-d", db_name, "-F", "p", "-f", file_path]
            
            process = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if process.returncode == 0:
                messagebox.showinfo("Успіх", f"Поточну версію бази даних успішно збережено як звіт:\n{file_path}")
            else:
                # Альтернативний ручний експорт таблиць у текстовий звіт, якщо pg_dump недоступний
                self.export_manual_report(file_path)
        except Exception as e:
            try:
                self.export_manual_report(file_path)
            except Exception as ex:
                messagebox.showerror("Помилка збереження", f"Не вдалося створити звіт:\n{ex}")

    def export_manual_report(self, file_path):
        """Резервний метод ручного експорту таблиць у файл звіту."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        tables = database.get_all_db_tables(cursor)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("=== ЗВІТНІСТЬ БАЗИ ДАНИХ КОЛЕДЖУ (2026/2027) ===\n\n")
            for tbl in tables:
                f.write(f"--- ТАБЛИЦЯ: {tbl} ---\n")
                cols, rows = database.get_table_data(cursor, tbl)
                f.write(" | ".join(cols) + "\n")
                f.write("-" * 50 + "\n")
                for r in rows:
                    f.write(" | ".join([str(val) for val in r]) + "\n")
                f.write("\n\n")
        cursor.close()
        conn.close()
        messagebox.showinfo("Успіх", f"Звітність успішно сформована та збережена у файлі:\n{file_path}")

    def clear_rewards_only(self):
        if not messagebox.askyesno("Підтвердження", "Очистити всі збережені накази про нагородження та нараховані бали?"):
            return
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            database.clear_rewards_and_ratings(cursor)
            conn.commit()
            cursor.close()
            conn.close()
            messagebox.showinfo("Успіх", "Накази та бали успішно очищено!")
            self.refresh_all_views()
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    def clear_entire_database(self):
        if not messagebox.askyesno("Підтвердження", "УВАГА! Повністю очистити всю базу даних?"):
            return
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            database.clear_entire_database(cursor)
            conn.commit()
            cursor.close()
            conn.close()
            messagebox.showinfo("Успіх", "Базу даних повністю очищено!")
            self.refresh_all_views()
            self.import_textbox.delete("0.0", "end")
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    def refresh_all_views(self):
        self.refresh_groups_dropdown()
        self.load_rating_data()
        self.refresh_db_sidebar_tables()

    # --- ПРАВИЙ САЙДБАР: СЕРЕДОВИЩЕ БАЗИ ДАНИХ ---
    def setup_database_environment_sidebar(self):
        db_sidebar = ctk.CTkFrame(self, fg_color=("#f1f3f5", "#212529"))
        db_sidebar.grid(row=1, column=1, padx=(5, 15), pady=(0, 15), sticky="nsew")
        db_sidebar.grid_columnconfigure(0, weight=1)
        db_sidebar.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(db_sidebar, text="🗄️ Середовище БД", font=("Arial", 15, "bold")).grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")

        # Панель вибору таблиці та керування
        ctrl_sb = ctk.CTkFrame(db_sidebar, fg_color="transparent")
        ctrl_sb.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(ctrl_sb, text="Таблиця:").pack(side="left", padx=2)
        self.db_table_dropdown = ctk.CTkOptionMenu(ctrl_sb, values=["(Немає таблиць)"], width=150, command=self.load_db_table_data)
        self.db_table_dropdown.pack(side="left", padx=5)

        drop_tbl_btn = ctk.CTkButton(ctrl_sb, text="🗑 Видалити таблицю", fg_color="#c92a2a", hover_color="#a61e1e", width=120, command=self.drop_selected_db_table)
        drop_tbl_btn.pack(side="right", padx=2)

        # Таблиця (Treeview) для перегляду довільної таблиці БД
        table_frame_sb = ctk.CTkFrame(db_sidebar)
        table_frame_sb.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        table_frame_sb.grid_columnconfigure(0, weight=1)
        table_frame_sb.grid_rowconfigure(0, weight=1)

        self.db_tree = ttk.Treeview(table_frame_sb, show="headings", selectmode="browse")
        
        sb_scroll_y = ttk.Scrollbar(table_frame_sb, orient="vertical", command=self.db_tree.yview)
        sb_scroll_x = ttk.Scrollbar(table_frame_sb, orient="horizontal", command=self.db_tree.xview)
        self.db_tree.configure(yscrollcommand=sb_scroll_y.set, xscrollcommand=sb_scroll_x.set)

        self.db_tree.grid(row=0, column=0, sticky="nsew")
        sb_scroll_y.grid(row=0, column=1, sticky="ns")
        sb_scroll_x.grid(row=1, column=0, sticky="ew")

        self.db_tree.bind("<Double-1>", self.on_db_table_cell_double_click)

        hint_db = ctk.CTkLabel(db_sidebar, text="💡 Двічі клікніть на рядок таблиці БД для редагування клітинки або видалення рядка.", text_color="gray", font=("Arial", 11))
        hint_db.grid(row=3, column=0, padx=10, pady=5, sticky="w")

    def refresh_db_sidebar_tables(self):
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            tables = database.get_all_db_tables(cursor)
            cursor.close()
            conn.close()

            if tables:
                self.db_table_dropdown.configure(values=tables)
                if self.selected_db_table not in tables:
                    self.selected_db_table = tables[0]
                self.db_table_dropdown.set(self.selected_db_table)
                self.load_db_table_data(self.selected_db_table)
            else:
                self.db_table_dropdown.configure(values=["(Немає таблиць)"])
                self.db_table_dropdown.set("(Немає таблиць)")
                for row in self.db_tree.get_children():
                    self.db_tree.delete(row)
        except Exception:
            pass

    def load_db_table_data(self, table_name):
        if not table_name or "(" in table_name:
            return
        self.selected_db_table = table_name

        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            columns, rows = database.get_table_data(cursor, table_name)
            cursor.close()
            conn.close()

            # Налаштовуємо колонки Treeview динамічно під будь-яку таблицю БД
            self.db_tree.configure(columns=columns)
            for col in columns:
                self.db_tree.heading(col, text=col)
                self.db_tree.column(col, width=120, anchor="w")

            for row in self.db_tree.get_children():
                self.db_tree.delete(row)

            for r in rows:
                self.db_tree.insert("", "end", values=r)

        except Exception as e:
            messagebox.showerror("Помилка БД", str(e))

    def drop_selected_db_table(self):
        if not self.selected_db_table:
            return
        if not messagebox.askyesno("Підтвердження", f"Ви дійсно хочете повністю видалити таблицю '{self.selected_db_table}' з бази даних?"):
            return
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            database.drop_entire_table(cursor, self.selected_db_table)
            conn.commit()
            cursor.close()
            conn.close()
            messagebox.showinfo("Успіх", f"Таблицю '{self.selected_db_table}' видалено!")
            self.refresh_all_views()
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    def on_db_table_cell_double_click(self, event):
        """Редагування клітинки або видалення рядка у середовищі БД."""
        selected_item = self.db_tree.selection()
        if not selected_item:
            return

        item_data = self.db_tree.item(selected_item)
        values = item_data['values']
        columns = self.db_tree["columns"]
        row_id = values[0]  # Припускаємо, що перша колонка — це ID

        region = self.db_tree.identify("region", event.x, event.y)
        column_id = self.db_tree.identify_column(event.x)
        col_index = int(column_id.replace("#", "")) - 1
        col_name = columns[col_index]
        current_val = values[col_index]

        # Вікно керування рядком/клітинкою у середовищі БД
        edit_db_win = ctk.CTkToplevel(self)
        edit_db_win.title(f"Керування таблицею: {self.selected_db_table}")
        edit_db_win.geometry("400x300")
        edit_db_win.grab_set()

        ctk.CTkLabel(edit_db_win, text=f"Редагування поля [{col_name}] для ID = {row_id}", font=("Arial", 12, "bold")).pack(padx=20, pady=(15, 5))
        
        val_entry = ctk.CTkEntry(edit_db_win, width=350)
        val_entry.insert(0, str(current_val))
        val_entry.pack(padx=20, pady=10)

        def save_cell_edit():
            if not messagebox.askyesno("Підтвердження", "Зберегти зміни в базі даних?"):
                return
            new_val = val_entry.get().strip()
            try:
                conn = self.get_db_connection()
                cursor = conn.cursor()
                database.update_table_cell(cursor, self.selected_db_table, col_name, new_val, row_id)
                conn.commit()
                cursor.close()
                conn.close()
                messagebox.showinfo("Успіх", "Дані оновлено!")
                edit_db_win.destroy()
                self.load_db_table_data(self.selected_db_table)
            except Exception as e:
                messagebox.showerror("Помилка", str(e))

        def delete_entire_row():
            if not messagebox.askyesno("Підтвердження", f"Видалити весь рядок (ID = {row_id})?"):
                return
            try:
                conn = self.get_db_connection()
                cursor = conn.cursor()
                database.delete_table_row(cursor, self.selected_db_table, row_id)
                conn.commit()
                cursor.close()
                conn.close()
                messagebox.showinfo("Успіх", "Рядок видалено!")
                edit_db_win.destroy()
                self.load_db_table_data(self.selected_db_table)
            except Exception as e:
                messagebox.showerror("Помилка", str(e))

        ctk.CTkButton(edit_db_win, text="Зберегти зміну поля", fg_color="#2b8a3e", command=save_cell_edit).pack(padx=20, pady=10)
        ctk.CTkButton(edit_db_win, text="🗑 Видалити весь рядок", fg_color="#c92a2a", command=delete_entire_row).pack(padx=20, pady=5)

    # --- ВКЛАДКА 1: ІМПОРТ З WORD ---
    def setup_import_tab(self):
        self.tab_import.grid_columnconfigure(0, weight=1)
        self.tab_import.grid_rowconfigure(1, weight=1)

        top_panel = ctk.CTkFrame(self.tab_import, fg_color="transparent")
        top_panel.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        select_btn = ctk.CTkButton(top_panel, text="Вибрати файл зі списками груп (.doc / .docx)", command=self.browse_student_file)
        select_btn.pack(side="left", padx=5)

        self.lbl_import_status = ctk.CTkLabel(top_panel, text="Оберіть файл для розпізнавання груп")
        self.lbl_import_status.pack(side="left", padx=15)

        self.save_import_btn = ctk.CTkButton(top_panel, text="Створити таблиці та зберегти в БД", fg_color="#1864ab", state="disabled", command=self.save_parsed_to_db)
        self.save_import_btn.pack(side="right", padx=5)

        self.import_textbox = ctk.CTkTextbox(self.tab_import, font=("Consolas", 12))
        self.import_textbox.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

    def browse_student_file(self):
        path = filedialog.askopenfilename(filetypes=[("Word Documents", "*.docx;*.doc"), ("All Files", "*.*")])
        if not path:
            return

        self.lbl_import_status.configure(text=f"Файл: {os.path.basename(path)}")
        try:
            self.loaded_data = parse_students_tables(path)
            self.import_textbox.delete("0.0", "end")

            total_students = sum(len(g["students"]) for g in self.loaded_data.values())
            summary = f"Знайдено груп: {len(self.loaded_data)} | Всього студентів: {total_students}\n"
            summary += "=" * 80 + "\n\n"

            for grp, info in self.loaded_data.items():
                summary += f"ГРУПА: {grp} | Навч. рік: {info['study_year']} | Куратор: {info['curator']}\n"
                summary += f"{'ID':<4} | {'ПІБ':<35} | {'Фінанс.':<8} | {'Примітка'}\n"
                summary += "-" * 75 + "\n"
                for idx, s in enumerate(info["students"], 1):
                    summary += f"{idx:<4} | {s['full_name']:<35} | {s['funding']:<8} | {s['note']}\n"
                summary += "\n"

            self.import_textbox.insert("end", summary)
            self.save_import_btn.configure(state="normal")
        except Exception as e:
            messagebox.showerror("Помилка парсингу", str(e))

    def save_parsed_to_db(self):
        if not self.loaded_data:
            return

        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            for grp_name, data in self.loaded_data.items():
                tbl_name = database.create_group_table(cursor, grp_name, data["study_year"], data["curator"])
                cursor.execute(f"TRUNCATE TABLE {tbl_name} RESTART IDENTITY;")

                for s in data["students"]:
                    database.insert_student(cursor, tbl_name, s["full_name"], grp_name, s["funding"], data["curator"], s["note"])

            conn.commit()
            cursor.close()
            conn.close()

            messagebox.showinfo("Успіх", "Усі групи та списки студентів успішно збережені в базі даних!")
            self.refresh_all_views()
            self.tabview.set("Керування студентами (CRUD)")
        except Exception as e:
            messagebox.showerror("Помилка запису в БД", str(e))

    # --- ВКЛАДКА 2: CRUD СТУДЕНТІВ ---
    def setup_crud_tab(self):
        self.tab_crud.grid_columnconfigure(0, weight=1)
        self.tab_crud.grid_rowconfigure(2, weight=1)

        ctrl_frame = ctk.CTkFrame(self.tab_crud, fg_color="transparent")
        ctrl_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(ctrl_frame, text="Оберіть групу:").pack(side="left", padx=5)
        self.group_dropdown = ctk.CTkOptionMenu(ctrl_frame, values=["(Немає груп)"], command=self.load_group_students)
        self.group_dropdown.pack(side="left", padx=5)

        refresh_btn = ctk.CTkButton(ctrl_frame, text="Оновити список", width=110, command=self.refresh_all_views)
        refresh_btn.pack(side="left", padx=10)

        btn_add = ctk.CTkButton(ctrl_frame, text="+ Додати студента", fg_color="#2b8a3e", width=130, command=self.add_student_dialog)
        btn_add.pack(side="left", padx=5)

        self.lbl_group_info = ctk.CTkLabel(self.tab_crud, text="Куратор: — | Навчальний рік: —", font=("Arial", 13, "bold"))
        self.lbl_group_info.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        table_frame = ctk.CTkFrame(self.tab_crud)
        table_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        columns = ("id", "full_name", "funding", "note", "action")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        
        self.tree.heading("id", text="ID")
        self.tree.heading("full_name", text="ПІБ Студента")
        self.tree.heading("funding", text="Фінансування")
        self.tree.heading("note", text="Примітки / Контакти / УБД")
        self.tree.heading("action", text="Дія")

        self.tree.column("id", width=50, anchor="center")
        self.tree.column("full_name", width=250, anchor="w")
        self.tree.column("funding", width=90, anchor="center")
        self.tree.column("note", width=250, anchor="w")
        self.tree.column("action", width=90, anchor="center")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<Double-1>", self.on_cell_double_click)

    def refresh_groups_dropdown(self):
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            groups = database.get_all_registered_groups(cursor)
            cursor.close()
            conn.close()

            if groups:
                values = [f"{g[0]} ({g[1]})" for g in groups]
                self.group_dropdown.configure(values=values)
                self.group_dropdown.set(values[0])
                self.load_group_students(values[0])
            else:
                self.group_dropdown.configure(values=["(Немає груп)"])
                self.group_dropdown.set("(Немає груп)")
                for row in self.tree.get_children():
                    self.tree.delete(row)
        except Exception:
            pass

    def load_group_students(self, selection):
        if not selection or "(Немає" in selection:
            return

        table_name = selection.split("(")[1].replace(")", "").strip()
        self.selected_group_table = table_name

        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT study_year, curator FROM groups_registry WHERE table_name = %s;", (table_name,))
            reg_info = cursor.fetchone()
            if reg_info:
                self.lbl_group_info.configure(text=f"Навчальний рік: {reg_info[0]} | Куратор: {reg_info[1]}")

            students = database.get_students_from_group(cursor, table_name)
            cursor.close()
            conn.close()

            for row in self.tree.get_children():
                self.tree.delete(row)

            for s in students:
                self.tree.insert("", "end", values=(s[0], s[1], s[2], s[3], "🗑 Видалити"))

        except Exception as e:
            messagebox.showerror("Помилка читання", str(e))

    def on_cell_double_click(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            return

        item_data = self.tree.item(selected_item)
        values = item_data['values']
        student_id, current_name, current_funding, current_note = values[0], values[1], values[2], values[3]

        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        if region == "cell" and column == "#5":
            self.delete_student_confirmed(student_id, current_name)
            return

        edit_window = ctk.CTkToplevel(self)
        edit_window.title("Редагування студента")
        edit_window.geometry("400x320")
        edit_window.grab_set()

        ctk.CTkLabel(edit_window, text="ПІБ Студента:").pack(anchor="w", padx=20, pady=(15, 0))
        name_entry = ctk.CTkEntry(edit_window, width=350)
        name_entry.insert(0, current_name)
        name_entry.pack(padx=20, pady=5)

        ctk.CTkLabel(edit_window, text="Форма фінансування (ДЗ / К):").pack(anchor="w", padx=20, pady=(10, 0))
        funding_entry = ctk.CTkEntry(edit_window, width=350)
        funding_entry.insert(0, current_funding)
        funding_entry.pack(padx=20, pady=5)

        ctk.CTkLabel(edit_window, text="Примітки / Контакти:").pack(anchor="w", padx=20, pady=(10, 0))
        note_entry = ctk.CTkEntry(edit_window, width=350)
        note_entry.insert(0, current_note)
        note_entry.pack(padx=20, pady=5)

        def save_changes():
            if not messagebox.askyesno("Підтвердження", "Зберегти внесені зміни до бази даних?"):
                return
            new_name = name_entry.get().strip()
            new_funding = funding_entry.get().strip().upper()
            new_note = note_entry.get().strip()

            try:
                conn = self.get_db_connection()
                cursor = conn.cursor()
                database.update_student(cursor, self.selected_group_table, student_id, new_name, new_funding, new_note if new_note else "—")
                conn.commit()
                cursor.close()
                conn.close()

                messagebox.showinfo("Успіх", "Дані студента оновлено!")
                edit_window.destroy()
                self.load_group_students(self.group_dropdown.get())
                self.refresh_db_sidebar_tables()
            except Exception as e:
                messagebox.showerror("Помилка", str(e))

        save_btn = ctk.CTkButton(edit_window, text="Зберегти зміни", fg_color="#2b8a3e", command=save_changes)
        save_btn.pack(padx=20, pady=20)

    def delete_student_confirmed(self, student_id, student_name):
        if messagebox.askyesno("Підтвердження видалення", f"Ви дійсно хочете видалити студента:\n{student_name}?"):
            try:
                conn = self.get_db_connection()
                cursor = conn.cursor()
                database.delete_student(cursor, self.selected_group_table, student_id)
                conn.commit()
                cursor.close()
                conn.close()

                messagebox.showinfo("Успіх", "Студента успішно видалено!")
                self.load_group_students(self.group_dropdown.get())
                self.refresh_db_sidebar_tables()
            except Exception as e:
                messagebox.showerror("Помилка", str(e))

    def add_student_dialog(self):
        if not self.selected_group_table:
            messagebox.showwarning("Увага", "Спочатку оберіть групу з випадаючого списку!")
            return

        add_window = ctk.CTkToplevel(self)
        add_window.title("Додавання студента")
        add_window.geometry("400x320")
        add_window.grab_set()

        ctk.CTkLabel(add_window, text="ПІБ Студента:").pack(anchor="w", padx=20, pady=(15, 0))
        name_entry = ctk.CTkEntry(add_window, width=350)
        name_entry.pack(padx=20, pady=5)

        ctk.CTkLabel(add_window, text="Форма фінансування (ДЗ / К):").pack(anchor="w", padx=20, pady=(10, 0))
        funding_entry = ctk.CTkEntry(add_window, width=350)
        funding_entry.insert(0, "ДЗ")
        funding_entry.pack(padx=20, pady=5)

        ctk.CTkLabel(add_window, text="Примітки / Контакти:").pack(anchor="w", padx=20, pady=(10, 0))
        note_entry = ctk.CTkEntry(add_window, width=350)
        note_entry.insert(0, "—")
        note_entry.pack(padx=20, pady=5)

        def save_new_student():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("Помилка", "ПІБ не може бути порожнім!")
                return
            if not messagebox.askyesno("Підтвердження", "Додати нового студента до бази даних?"):
                return

            funding = funding_entry.get().strip().upper()
            note = note_entry.get().strip()

            try:
                conn = self.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT group_name, curator FROM groups_registry WHERE table_name = %s;", (self.selected_group_table,))
                grp_info = cursor.fetchone()
                database.insert_student(cursor, self.selected_group_table, name, grp_info[0], funding, grp_info[1], note if note else "—")
                conn.commit()
                cursor.close()
                conn.close()

                messagebox.showinfo("Успіх", "Студента успішно додано!")
                add_window.destroy()
                self.load_group_students(self.group_dropdown.get())
                self.refresh_db_sidebar_tables()
            except Exception as e:
                messagebox.showerror("Помилка", str(e))

        save_btn = ctk.CTkButton(add_window, text="Додати в БД", fg_color="#2b8a3e", command=save_new_student)
        save_btn.pack(padx=20, pady=20)

    # --- ВКЛАДКА 3: НАГОРОДЖЕННЯ (НАКАЗИ) ---
    def setup_rewards_tab(self):
        self.tab_rewards.grid_columnconfigure(0, weight=1)
        self.tab_rewards.grid_rowconfigure(2, weight=1)

        top_p = ctk.CTkFrame(self.tab_rewards, fg_color="transparent")
        top_p.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        select_rew_btn = ctk.CTkButton(top_p, text="Вибрати файл наказу про подяки (.doc / .docx)", command=self.browse_reward_file)
        select_rew_btn.pack(side="left", padx=5)

        self.lbl_rew_status = ctk.CTkLabel(top_p, text="Файл не вибрано")
        self.lbl_rew_status.pack(side="left", padx=15)

        self.save_rew_btn = ctk.CTkButton(top_p, text="Зберегти наказ та нарахувати бали в БД", fg_color="#1864ab", state="disabled", command=self.save_reward_to_db)
        self.save_rew_btn.pack(side="right", padx=5)

        self.order_info_frame = ctk.CTkFrame(self.tab_rewards)
        self.order_info_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.order_info_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.lbl_ord_num = ctk.CTkLabel(self.order_info_frame, text="Номер: —")
        self.lbl_ord_num.grid(row=0, column=0, padx=10, pady=8, sticky="w")

        self.lbl_ord_date = ctk.CTkLabel(self.order_info_frame, text="Дата: —")
        self.lbl_ord_date.grid(row=0, column=1, padx=10, pady=8, sticky="w")

        self.lbl_ord_level = ctk.CTkLabel(self.order_info_frame, text="Рівень: —")
        self.lbl_ord_level.grid(row=0, column=2, padx=10, pady=8, sticky="w")

        self.lbl_ord_pts = ctk.CTkLabel(self.order_info_frame, text="Бали: —")
        self.lbl_ord_pts.grid(row=0, column=3, padx=10, pady=8, sticky="w")

        rew_frame = ctk.CTkFrame(self.tab_rewards)
        rew_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        rew_frame.grid_columnconfigure(0, weight=1)
        rew_frame.grid_rowconfigure(0, weight=1)

        columns = ("num", "name", "grp", "pts", "action")
        self.rew_tree = ttk.Treeview(rew_frame, columns=columns, show="headings", selectmode="browse")
        self.rew_tree.heading("num", text="№")
        self.rew_tree.heading("name", text="ПІБ Студента з наказу")
        self.rew_tree.heading("grp", text="Знайдена група в БД")
        self.rew_tree.heading("pts", text="Бали")
        self.rew_tree.heading("action", text="Дія")

        self.rew_tree.column("num", width=50, anchor="center")
        self.rew_tree.column("name", width=250, anchor="w")
        self.rew_tree.column("grp", width=120, anchor="center")
        self.rew_tree.column("pts", width=70, anchor="center")
        self.rew_tree.column("action", width=90, anchor="center")

        rew_scroll = ttk.Scrollbar(rew_frame, orient="vertical", command=self.rew_tree.yview)
        self.rew_tree.configure(yscrollcommand=rew_scroll.set)

        self.rew_tree.grid(row=0, column=0, sticky="nsew")
        rew_scroll.grid(row=0, column=1, sticky="ns")

        self.rew_tree.bind("<Double-1>", self.on_reward_row_double_click)

    def browse_reward_file(self):
        path = filedialog.askopenfilename(filetypes=[("Word Documents", "*.docx;*.doc"), ("All Files", "*.*")])
        if not path:
            return

        self.lbl_rew_status.configure(text=f"Файл: {os.path.basename(path)}")
        try:
            self.loaded_reward_data = parse_reward_order(path)
            
            self.lbl_ord_num.configure(text=f"Номер: {self.loaded_reward_data['order_number']}")
            self.lbl_ord_date.configure(text=f"Дата: {self.loaded_reward_data['order_date']}")
            self.lbl_ord_level.configure(text=f"Рівень: {self.loaded_reward_data['level_type']}")
            self.lbl_ord_pts.configure(text=f"Бали: {self.loaded_reward_data['points']}")

            for row in self.rew_tree.get_children():
                self.rew_tree.delete(row)

            conn = self.get_db_connection()
            cursor = conn.cursor()
            db_students = database.get_all_students_flat(cursor)
            cursor.close()
            conn.close()

            cleaned_students = []
            for st in self.loaded_reward_data["students"]:
                if "юрчак" in st["full_name"].lower():
                    continue
                cleaned_students.append(st)
            self.loaded_reward_data["students"] = cleaned_students

            matched_count = 0
            for st in self.loaded_reward_data["students"]:
                matched_id = None
                matched_table = None
                matched_grp = st["group_name"]

                st_surname = st["full_name"].split()[0].strip().lower()
                surname_stem = st_surname[:min(len(st_surname), 4)]

                for dbs in db_students:
                    db_name_lower = dbs["full_name"].lower()
                    if surname_stem in db_name_lower:
                        if not matched_grp or matched_grp.upper() == dbs["group_name"].upper():
                            matched_grp = dbs["group_name"]
                            matched_id = dbs["id"]
                            matched_table = dbs["table"]
                            matched_count += 1
                            break

                st["matched_id"] = matched_id
                st["matched_table"] = matched_table
                st["group_name"] = matched_grp or "Не визначено"

            for idx, st in enumerate(self.loaded_reward_data["students"], 1):
                self.rew_tree.insert("", "end", values=(idx, st["full_name"], st["group_name"], self.loaded_reward_data["points"], "🗑 Видалити"))

            self.save_rew_btn.configure(state="normal")
        except Exception as e:
            messagebox.showerror("Помилка розпізнавання наказу", str(e))

    def on_reward_row_double_click(self, event):
        selected_item = self.rew_tree.selection()
        if not selected_item or not self.loaded_reward_data:
            return

        item_data = self.rew_tree.item(selected_item)
        values = item_data['values']
        row_idx = int(values[0]) - 1

        region = self.rew_tree.identify("region", event.x, event.y)
        column = self.rew_tree.identify_column(event.x)
        if region == "cell" and column == "#5":
            self.loaded_reward_data["students"].pop(row_idx)
            self.rew_tree.delete(selected_item)
            return

        st_obj = self.loaded_reward_data["students"][row_idx]
        edit_rew_st = ctk.CTkToplevel(self)
        edit_rew_st.title("Редагування студента в наказі")
        edit_rew_st.geometry("400x260")
        edit_rew_st.grab_set()

        ctk.CTkLabel(edit_rew_st, text="ПІБ Студента:").pack(anchor="w", padx=20, pady=(15, 0))
        name_e = ctk.CTkEntry(edit_rew_st, width=350)
        name_e.insert(0, st_obj["full_name"])
        name_e.pack(padx=20, pady=5)

        ctk.CTkLabel(edit_rew_st, text="Група:").pack(anchor="w", padx=20, pady=(10, 0))
        grp_e = ctk.CTkEntry(edit_rew_st, width=350)
        grp_e.insert(0, st_obj["group_name"])
        grp_e.pack(padx=20, pady=5)

        def save_rew_st_edit():
            if not messagebox.askyesno("Підтвердження", "Зберегти зміни?"):
                return
            st_obj["full_name"] = name_e.get().strip()
            st_obj["group_name"] = grp_e.get().strip().upper()
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            db_students = database.get_all_students_flat(cursor)
            cursor.close()
            conn.close()

            st_surname = st_obj["full_name"].split()[0].strip().lower()
            stem = st_surname[:min(len(st_surname), 4)]
            for dbs in db_students:
                if stem in dbs["full_name"].lower():
                    if st_obj["group_name"] == "НЕ ВИЗНАЧЕНО" or st_obj["group_name"] == dbs["group_name"]:
                        st_obj["matched_id"] = dbs["id"]
                        st_obj["matched_table"] = dbs["table"]
                        st_obj["group_name"] = dbs["group_name"]
                        break

            edit_rew_st.destroy()
            for row in self.rew_tree.get_children():
                self.rew_tree.delete(row)
            for idx, s in enumerate(self.loaded_reward_data["students"], 1):
                self.rew_tree.insert("", "end", values=(idx, s["full_name"], s["group_name"], self.loaded_reward_data["points"], "🗑 Видалити"))

        save_btn = ctk.CTkButton(edit_rew_st, text="Зберегти зміни", fg_color="#2b8a3e", command=save_rew_st_edit)
        save_btn.pack(padx=20, pady=15)

    def save_reward_to_db(self):
        if not self.loaded_reward_data or not self.loaded_reward_data["students"]:
            return

        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO rewards_orders (order_number, order_date, event_title, level_type, default_points)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (order_number, order_date) DO UPDATE 
                SET event_title = EXCLUDED.event_title, level_type = EXCLUDED.level_type, default_points = EXCLUDED.default_points
                RETURNING id;
            """, (
                self.loaded_reward_data["order_number"],
                self.loaded_reward_data["order_date"],
                self.loaded_reward_data["event_title"],
                self.loaded_reward_data["level_type"],
                self.loaded_reward_data["points"]
            ))
            order_id = cursor.fetchone()[0]

            success_count = 0
            for st in self.loaded_reward_data["students"]:
                if st.get("matched_id") and st.get("matched_table"):
                    cursor.execute("""
                        INSERT INTO student_achievements (group_table_name, student_id, order_id, points_awarded)
                        VALUES (%s, %s, %s, %s);
                    """, (st["matched_table"], st["matched_id"], order_id, self.loaded_reward_data["points"]))
                    success_count += 1

            conn.commit()
            cursor.close()
            conn.close()

            messagebox.showinfo("Успіх", f"Наказ успішно збережено в БД! Нараховано бали для {success_count} студентів.")
            self.load_rating_data()
            self.refresh_db_sidebar_tables()
            self.tabview.set("Рейтинг студентів")
        except Exception as e:
            messagebox.showerror("Помилка збереження в БД", str(e))

    # --- ВКЛАДКА 4: РЕЙТИНГ СТУДЕНТІВ (ТІЛЬКИ ПЕРЕГЛЯД, БЕЗ РЕДАГУВАННЯ) ---
    def setup_rating_tab(self):
        self.tab_rating.grid_columnconfigure(0, weight=1)
        self.tab_rating.grid_rowconfigure(1, weight=1)

        rt_top = ctk.CTkFrame(self.tab_rating, fg_color="transparent")
        rt_top.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(rt_top, text="Фільтр за групою:").pack(side="left", padx=5)
        self.rating_group_dropdown = ctk.CTkOptionMenu(rt_top, values=["Усі групи"], command=lambda _: self.load_rating_data())
        self.rating_group_dropdown.pack(side="left", padx=5)

        refresh_rt_btn = ctk.CTkButton(rt_top, text="Оновити рейтинг", width=120, command=self.load_rating_data)
        refresh_rt_btn.pack(side="left", padx=15)

        rt_frame = ctk.CTkFrame(self.tab_rating)
        rt_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        rt_frame.grid_columnconfigure(0, weight=1)
        rt_frame.grid_rowconfigure(0, weight=1)

        columns = ("place", "name", "grp", "total_pts")
        self.rating_tree = ttk.Treeview(rt_frame, columns=columns, show="headings", selectmode="browse")
        
        self.rating_tree.heading("place", text="Місце")
        self.rating_tree.heading("name", text="ПІБ Студента")
        self.rating_tree.heading("grp", text="Група")
        self.rating_tree.heading("total_pts", text="Загалом балів")

        self.rating_tree.column("place", width=70, anchor="center")
        self.rating_tree.column("name", width=330, anchor="w")
        self.rating_tree.column("grp", width=120, anchor="center")
        self.rating_tree.column("total_pts", width=120, anchor="center")

        rt_scroll = ttk.Scrollbar(rt_frame, orient="vertical", command=self.rating_tree.yview)
        self.rating_tree.configure(yscrollcommand=rt_scroll.set)

        self.rating_tree.grid(row=0, column=0, sticky="nsew")
        rt_scroll.grid(row=0, column=1, sticky="ns")

        hint_rt = ctk.CTkLabel(self.tab_rating, text="💡 Рейтингова таблиця студентів за загальною сумою набраних балів.", text_color="gray")
        hint_rt.grid(row=2, column=0, padx=10, pady=5, sticky="w")

    def load_rating_data(self):
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            groups = database.get_all_registered_groups(cursor)
            group_names = ["Усі групи"] + [g[0] for g in groups]
            current_filter = self.rating_group_dropdown.get()
            self.rating_group_dropdown.configure(values=group_names)
            if current_filter not in group_names:
                self.rating_group_dropdown.set("Усі групи")
                current_filter = "Усі групи"

            cursor.execute("SELECT table_name, group_name FROM groups_registry;")
            all_groups = cursor.fetchall()

            students_rating = []
            for tbl, grp in all_groups:
                if current_filter != "Усі групи" and grp != current_filter:
                    continue

                cursor.execute(f"""
                    SELECT s.id, s.full_name, s.group_name, 
                           COALESCE(SUM(a.points_awarded), 0) as total
                    FROM {tbl} s
                    LEFT JOIN student_achievements a ON a.group_table_name = %s AND a.student_id = s.id
                    GROUP BY s.id, s.full_name, s.group_name
                    ORDER BY total DESC, s.full_name ASC;
                """, (tbl,))
                
                for row in cursor.fetchall():
                    students_rating.append({
                        "full_name": row[1],
                        "group_name": row[2],
                        "total": row[3]
                    })

            cursor.close()
            conn.close()

            students_rating.sort(key=lambda x: x["total"], reverse=True)

            for row in self.rating_tree.get_children():
                self.rating_tree.delete(row)

            for idx, r in enumerate(students_rating, 1):
                self.rating_tree.insert("", "end", values=(idx, r["full_name"], r["group_name"], r["total"]))

        except Exception as e:
            pass

if __name__ == "__main__":
    app = StudentManagementApp()
    app.mainloop()