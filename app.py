import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import customtkinter as ctk
import psycopg2

import database
from table_parser import parse_students_tables

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class StudentManagementApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Автоматизація документообігу — Керування групами та студентами")
        self.geometry("1150x750")
        self.minsize(950, 650)

        self.loaded_data = None
        self.selected_group_table = None

        self.create_widgets()

    def create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Панель підключення до PostgreSQL та Очищення БД (як на скріншоті)
        db_frame = ctk.CTkFrame(self)
        db_frame.grid(row=0, column=0, padx=15, pady=10, sticky="ew")

        ctk.CTkLabel(db_frame, text="Хост:").grid(row=0, column=0, padx=4, pady=8)
        self.host_entry = ctk.CTkEntry(db_frame, width=80)
        self.host_entry.insert(0, "localhost")
        self.host_entry.grid(row=0, column=1, padx=4, pady=8)

        ctk.CTkLabel(db_frame, text="Порт:").grid(row=0, column=2, padx=4, pady=8)
        self.port_entry = ctk.CTkEntry(db_frame, width=50)
        self.port_entry.insert(0, "5432")
        self.port_entry.grid(row=0, column=3, padx=4, pady=8)

        ctk.CTkLabel(db_frame, text="БД:").grid(row=0, column=4, padx=4, pady=8)
        self.dbname_entry = ctk.CTkEntry(db_frame, width=80)
        self.dbname_entry.insert(0, "college_db")
        self.dbname_entry.grid(row=0, column=5, padx=4, pady=8)

        ctk.CTkLabel(db_frame, text="Користувач:").grid(row=0, column=6, padx=4, pady=8)
        self.user_entry = ctk.CTkEntry(db_frame, width=80)
        self.user_entry.insert(0, "postgres")
        self.user_entry.grid(row=0, column=7, padx=4, pady=8)

        ctk.CTkLabel(db_frame, text="Пароль:").grid(row=0, column=8, padx=4, pady=8)
        self.pass_entry = ctk.CTkEntry(db_frame, width=80, show="*")
        self.pass_entry.grid(row=0, column=9, padx=4, pady=8)

        connect_btn = ctk.CTkButton(db_frame, text="Підключитися", fg_color="#2b8a3e", width=100, command=self.test_connection)
        connect_btn.grid(row=0, column=10, padx=6, pady=8)

        # Кнопка очищення бази даних на верхній панелі
        clear_db_btn = ctk.CTkButton(db_frame, text="Очистити БД", fg_color="#c92a2a", hover_color="#a61e1e", width=95, command=self.clear_entire_database)
        clear_db_btn.grid(row=0, column=11, padx=6, pady=8)

        # Вкладки
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")

        self.tab_import = self.tabview.add("Імпорт списків з Word")
        self.tab_crud = self.tabview.add("Керування студентами (CRUD)")

        self.setup_import_tab()
        self.setup_crud_tab()

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
            self.refresh_groups_dropdown()
        except Exception as e:
            messagebox.showerror("Помилка БД", f"Не вдалося підключитися:\n{e}")

    def clear_entire_database(self):
        if not messagebox.askyesno("Підтвердження", "УВАГА! Ви дійсно хочете повністю очистити базу даних (видалити всі групи та студентів)?"):
            return
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            database.clear_entire_database(cursor)
            conn.commit()
            cursor.close()
            conn.close()
            messagebox.showinfo("Успіх", "Базу даних повністю очищено!")
            self.refresh_groups_dropdown()
            self.import_textbox.delete("0.0", "end")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося очистити БД:\n{e}")

    # --- ВКЛАДКА 1: ІМПОРТ З WORD ---
    def setup_import_tab(self):
        self.tab_import.grid_columnconfigure(0, weight=1)
        self.tab_import.grid_rowconfigure(1, weight=1)

        top_panel = ctk.CTkFrame(self.tab_import, fg_color="transparent")
        top_panel.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        select_btn = ctk.CTkButton(top_panel, text="Вибрати файл зі списками (.doc / .docx)", command=self.browse_student_file)
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
            self.refresh_groups_dropdown()
            self.tabview.set("Керування студентами (CRUD)")
        except Exception as e:
            messagebox.showerror("Помилка запису в БД", str(e))

    # --- ВКЛАДКА 2: CRUD ОПЕРАЦІЇ З РЕАЛЬНОЮ ТАБЛИЦЕЮ ---
    def setup_crud_tab(self):
        self.tab_crud.grid_columnconfigure(0, weight=1)
        self.tab_crud.grid_rowconfigure(2, weight=1)

        ctrl_frame = ctk.CTkFrame(self.tab_crud, fg_color="transparent")
        ctrl_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(ctrl_frame, text="Оберіть групу:").pack(side="left", padx=5)
        self.group_dropdown = ctk.CTkOptionMenu(ctrl_frame, values=["(Немає груп)"], command=self.load_group_students)
        self.group_dropdown.pack(side="left", padx=5)

        refresh_btn = ctk.CTkButton(ctrl_frame, text="Оновити список", width=110, command=self.refresh_groups_dropdown)
        refresh_btn.pack(side="left", padx=10)

        btn_add = ctk.CTkButton(ctrl_frame, text="+ Додати студента", fg_color="#2b8a3e", width=130, command=self.add_student_dialog)
        btn_add.pack(side="left", padx=5)

        self.lbl_group_info = ctk.CTkLabel(self.tab_crud, text="Куратор: — | Навчальний рік: —", font=("Arial", 13, "bold"))
        self.lbl_group_info.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        # Контейнер для реальної таблиці (Treeview) та смуги прокрутки
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

        # Подвійний клік на клітинку відкриває вікно редагування
        self.tree.bind("<Double-1>", self.on_cell_double_click)

        hint_lbl = ctk.CTkLabel(self.tab_crud, text="💡 Підказка: Двічі клікніть на рядок студента у таблиці, щоб змінити його дані.", text_color="gray")
        hint_lbl.grid(row=3, column=0, padx=10, pady=5, sticky="w")

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

            # Очищаємо таблицю перед заповненням
            for row in self.tree.get_children():
                self.tree.delete(row)

            for s in students:
                # Вставляємо дані у Treeview. У колонку action записуємо текст "Видалити"
                self.tree.insert("", "end", values=(s[0], s[1], s[2], s[3], "🗑 Видалити"))

        except Exception as e:
            messagebox.showerror("Помилка читання", str(e))

    def on_cell_double_click(self, event):
        """Обробник подвійного кліку для редагування або видалення при натисканні на кнопку."""
        selected_item = self.tree.selection()
        if not selected_item:
            return

        item_data = self.tree.item(selected_item)
        values = item_data['values']
        student_id, current_name, current_funding, current_note = values[0], values[1], values[2], values[3]

        # Перевіряємо, чи клікнули на крайню колонку "Дія"
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        if region == "cell" and column == "#5":
            self.delete_student_confirmed(student_id, current_name)
            return

        # Модальне вікно редагування даних студента з підтвердженням
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
        """Підтвердження та видалення студента."""
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

if __name__ == "__main__":
    app = StudentManagementApp()
    app.mainloop()