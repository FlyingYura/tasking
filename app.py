import os
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

        self.title("Автоматизація документообігу — Коледж (Студенти, Накази, Рейтинг)")
        self.geometry("1200x800")
        self.minsize(1000, 700)

        self.loaded_data = None
        self.loaded_reward_data = None
        self.selected_group_table = None

        self.create_widgets()

    def create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        db_frame = ctk.CTkFrame(self)
        db_frame.grid(row=0, column=0, padx=15, pady=10, sticky="ew")

        ctk.CTkLabel(db_frame, text="Хост:").grid(row=0, column=0, padx=4, pady=8)
        self.host_entry = ctk.CTkEntry(db_frame, width=70)
        self.host_entry.insert(0, "localhost")
        self.host_entry.grid(row=0, column=1, padx=4, pady=8)

        ctk.CTkLabel(db_frame, text="Порт:").grid(row=0, column=2, padx=4, pady=8)
        self.port_entry = ctk.CTkEntry(db_frame, width=45)
        self.port_entry.insert(0, "5432")
        self.port_entry.grid(row=0, column=3, padx=4, pady=8)

        ctk.CTkLabel(db_frame, text="БД:").grid(row=0, column=4, padx=4, pady=8)
        self.dbname_entry = ctk.CTkEntry(db_frame, width=70)
        self.dbname_entry.insert(0, "college_db")
        self.dbname_entry.grid(row=0, column=5, padx=4, pady=8)

        ctk.CTkLabel(db_frame, text="Користувач:").grid(row=0, column=6, padx=4, pady=8)
        self.user_entry = ctk.CTkEntry(db_frame, width=70)
        self.user_entry.insert(0, "postgres")
        self.user_entry.grid(row=0, column=7, padx=4, pady=8)

        ctk.CTkLabel(db_frame, text="Пароль:").grid(row=0, column=8, padx=4, pady=8)
        self.pass_entry = ctk.CTkEntry(db_frame, width=70, show="*")
        self.pass_entry.grid(row=0, column=9, padx=4, pady=8)

        connect_btn = ctk.CTkButton(db_frame, text="Підключитися", fg_color="#2b8a3e", width=95, command=self.test_connection)
        connect_btn.grid(row=0, column=10, padx=5, pady=8)

        clear_db_btn = ctk.CTkButton(db_frame, text="Очистити БД", fg_color="#c92a2a", hover_color="#a61e1e", width=90, command=self.clear_entire_database)
        clear_db_btn.grid(row=0, column=11, padx=5, pady=8)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")

        self.tab_import = self.tabview.add("Імпорт списків з Word")
        self.tab_crud = self.tabview.add("Керування студентами (CRUD)")
        self.tab_rewards = self.tabview.add("Нагородження (Накази)")
        self.tab_rating = self.tabview.add("Рейтинг студентів")

        self.setup_import_tab()
        self.setup_crud_tab()
        self.setup_rewards_tab()
        self.setup_rating_tab()

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

    def clear_entire_database(self):
        if not messagebox.askyesno("Підтвердження", "УВАГА! Ви дійсно хочете повністю очистити базу даних?"):
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
            messagebox.showerror("Помилка", f"Не вдалося очистити БД:\n{e}")

    def refresh_all_views(self):
        self.refresh_groups_dropdown()
        self.load_rating_data()

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

    # --- ВКЛАДКА 2: CRUD ОПЕРАЦІЇ ---
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
        self.tree.column("full_name", width=300, anchor="w")
        self.tree.column("funding", width=100, anchor="center")
        self.tree.column("note", width=350, anchor="w")
        self.tree.column("action", width=100, anchor="center")

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
            except Exception as e:
                messagebox.showerror("Помилка", str(e))

        save_btn = ctk.CTkButton(add_window, text="Додати в БД", fg_color="#2b8a3e", command=save_new_student)
        save_btn.pack(padx=20, pady=20)

    # --- ВКЛАДКА 3: НАГОРОДЖЕННЯ (НАКАЗИ) ---
    def setup_rewards_tab(self):
        self.tab_rewards.grid_columnconfigure(0, weight=1)
        self.tab_rewards.grid_rowconfigure(1, weight=1)

        top_p = ctk.CTkFrame(self.tab_rewards, fg_color="transparent")
        top_p.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        select_rew_btn = ctk.CTkButton(top_p, text="Вибрати файл наказу про подяки (.doc / .docx)", command=self.browse_reward_file)
        select_rew_btn.pack(side="left", padx=5)

        self.lbl_rew_status = ctk.CTkLabel(top_p, text="Файл не вибрано")
        self.lbl_rew_status.pack(side="left", padx=15)

        self.save_rew_btn = ctk.CTkButton(top_p, text="Зберегти наказ та нарахувати бали в БД", fg_color="#1864ab", state="disabled", command=self.save_reward_to_db)
        self.save_rew_btn.pack(side="right", padx=5)

        rew_frame = ctk.CTkFrame(self.tab_rewards)
        rew_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        rew_frame.grid_columnconfigure(0, weight=1)
        rew_frame.grid_rowconfigure(0, weight=1)

        columns = ("num", "name", "grp", "pts")
        self.rew_tree = ttk.Treeview(rew_frame, columns=columns, show="headings", selectmode="browse")
        self.rew_tree.heading("num", text="№")
        self.rew_tree.heading("name", text="ПІБ Студента з наказу")
        self.rew_tree.heading("grp", text="Знайдена група")
        self.rew_tree.heading("pts", text="Бали")

        self.rew_tree.column("num", width=50, anchor="center")
        self.rew_tree.column("name", width=350, anchor="w")
        self.rew_tree.column("grp", width=150, anchor="center")
        self.rew_tree.column("pts", width=80, anchor="center")

        rew_scroll = ttk.Scrollbar(rew_frame, orient="vertical", command=self.rew_tree.yview)
        self.rew_tree.configure(yscrollcommand=rew_scroll.set)

        self.rew_tree.grid(row=0, column=0, sticky="nsew")
        rew_scroll.grid(row=0, column=1, sticky="ns")

    def browse_reward_file(self):
        path = filedialog.askopenfilename(filetypes=[("Word Documents", "*.docx;*.doc"), ("All Files", "*.*")])
        if not path:
            return

        self.lbl_rew_status.configure(text=f"Файл: {os.path.basename(path)}")
        try:
            self.loaded_reward_data = parse_reward_order(path)
            
            for row in self.rew_tree.get_children():
                self.rew_tree.delete(row)

            # Підтягуємо існуючих студентів з бази для інтелектуального матчингу
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT table_name, group_name FROM groups_registry;")
            groups = cursor.fetchall()
            
            db_students = []
            for tbl, grp in groups:
                cursor.execute(f"SELECT id, full_name, group_name FROM {tbl};")
                for r in cursor.fetchall():
                    db_students.append({"table": tbl, "id": r[0], "full_name": r[1], "group_name": r[2]})
            
            cursor.close()
            conn.close()

            for idx, st in enumerate(self.loaded_reward_data["students"], 1):
                matched_grp = st["group_name"]
                matched_id = None
                matched_table = None

                # Нечітке зіставлення за прізвищем та (за потреби) групою
                for dbs in db_students:
                    # Витягуємо перше слово (прізвище) з бази та з наказу
                    db_surname = dbs["full_name"].split()[0].lower()
                    st_surname = st["full_name"].split()[0].lower()

                    if db_surname == st_surname:
                        if not matched_grp or matched_grp.upper() == dbs["group_name"].upper():
                            matched_grp = dbs["group_name"]
                            matched_id = dbs["id"]
                            matched_table = dbs["table"]
                            break

                st["matched_id"] = matched_id
                st["matched_table"] = matched_table
                st["group_name"] = matched_grp or "Не визначено"

                self.rew_tree.insert("", "end", values=(idx, st["full_name"], st["group_name"], self.loaded_reward_data["points"]))

            self.save_rew_btn.configure(state="normal")
            messagebox.showinfo("Аналіз завершено", f"Наказ №{self.loaded_reward_data['order_number']}\nРівень: {self.loaded_reward_data['level_type']} ({self.loaded_reward_data['points']} балів)\nЗнайдено студентів: {len(self.loaded_reward_data['students'])}")
        except Exception as e:
            messagebox.showerror("Помилка розпізнавання наказу", str(e))

    def save_reward_to_db(self):
        if not self.loaded_reward_data:
            return

        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            # 1. Зберігаємо наказ у rewards_orders
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

            # 2. Зберігаємо досягнення для кожного розпізнаного студента, що є в базі
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

            messagebox.showinfo("Успіх", f"Наказ збережено! Успішно нараховано бали для {success_count} студентів.")
            self.load_rating_data()
            self.tabview.set("Рейтинг студентів")
        except Exception as e:
            messagebox.showerror("Помилка збереження в БД", str(e))

    # --- ВКЛАДКА 4: РЕЙТИНГ СТУДЕНТІВ (З ФІЛЬТРАЦІЄЮ ПО ГРУПАХ) ---
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
        self.rating_tree.column("name", width=350, anchor="w")
        self.rating_tree.column("grp", width=120, anchor="center")
        self.rating_tree.column("total_pts", width=120, anchor="center")

        rt_scroll = ttk.Scrollbar(rt_frame, orient="vertical", command=self.rating_tree.yview)
        self.rating_tree.configure(yscrollcommand=rt_scroll.set)

        self.rating_tree.grid(row=0, column=0, sticky="nsew")
        rt_scroll.grid(row=0, column=1, sticky="ns")

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

            # Збираємо всіх студентів із таблиць груп та підраховуємо суму балів з student_achievements
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

            # Сортуємо загальний рейтинг за балами
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