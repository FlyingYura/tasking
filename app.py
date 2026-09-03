import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
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
        self.geometry("1100x750")
        self.minsize(950, 650)

        self.loaded_data = None
        self.selected_group_table = None

        self.create_widgets()  

    def create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Панель підключення до PostgreSQL
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
                # Очищаємо таблицю перед імпортом, якщо вона вже була
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

    # --- ВКЛАДКА 2: CRUD ОПЕРАЦІЇ ---
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

        # Кнопки дій CRUD
        btn_add = ctk.CTkButton(ctrl_frame, text="+ Додати студента", fg_color="#2b8a3e", width=130, command=self.add_student_dialog)
        btn_add.pack(side="left", padx=5)

        btn_edit = ctk.CTkButton(ctrl_frame, text="Редагувати", fg_color="#e8590c", width=100, command=self.edit_student_dialog)
        btn_edit.pack(side="left", padx=5)

        btn_del = ctk.CTkButton(ctrl_frame, text="Видалити", fg_color="#c92a2a", width=100, command=self.delete_student_dialog)
        btn_del.pack(side="left", padx=5)

        # Інфо-панель куратора та року
        self.lbl_group_info = ctk.CTkLabel(self.tab_crud, text="Куратор: — | Навчальний рік: —", font=("Arial", 13, "bold"))
        self.lbl_group_info.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        # Текстове поле таблиці студентів
        self.crud_textbox = ctk.CTkTextbox(self.tab_crud, font=("Consolas", 12))
        self.crud_textbox.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")

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

            self.crud_textbox.delete("0.0", "end")
            out = f"{'ID':<4} | {'ПІБ Студента':<35} | {'Група':<10} | {'Форма':<6} | {'Примітка'}\n"
            out += "=" * 80 + "\n"

            for s in students:
                out += f"{s[0]:<4} | {s[1]:<35} | {s[2]:<10} | {s[3]:<6} | {s[5]}\n"

            if not students:
                out += "\nТаблиця групи порожня. Скористайтеся кнопкою '+ Додати студента'."

            self.crud_textbox.insert("end", out)
        except Exception as e:
            messagebox.showerror("Помилка читання", str(e))

    def add_student_dialog(self):
        if not self.selected_group_table:
            messagebox.showwarning("Увага", "Спочатку оберіть групу!")
            return

        name = simpledialog.askstring("Додати студента", "Введіть ПІБ студента:")
        if not name:
            return
        funding = simpledialog.askstring("Форма фінансування", "Введіть джерело (ДЗ або К):", initialvalue="ДЗ")
        if not funding:
            return
        note = simpledialog.askstring("Примітка", "Введіть примітку (УБД, 25+, номер тощо):", initialvalue="—")

        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT group_name, curator FROM groups_registry WHERE table_name = %s;", (self.selected_group_table,))
            grp_info = cursor.fetchone()
            database.insert_student(cursor, self.selected_group_table, name.strip(), grp_info[0], funding.strip().upper(), grp_info[1], note.strip() if note else "—")
            conn.commit()
            cursor.close()
            conn.close()

            messagebox.showinfo("Успіх", "Студента додано!")
            self.load_group_students(self.group_dropdown.get())
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    def edit_student_dialog(self):
        if not self.selected_group_table:
            return

        student_id = simpledialog.askinteger("Редагування", "Введіть ID студента для редагування:")
        if not student_id:
            return

        new_name = simpledialog.askstring("Редагування", "Нове ПІБ студента:")
        if not new_name:
            return
        new_funding = simpledialog.askstring("Редагування", "Нове фінансування (ДЗ / К):", initialvalue="ДЗ")
        new_note = simpledialog.askstring("Редагування", "Нова примітка:", initialvalue="—")

        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            database.update_student(cursor, self.selected_group_table, student_id, new_name.strip(), new_funding.strip().upper(), new_note.strip() if new_note else "—")
            conn.commit()
            cursor.close()
            conn.close()

            messagebox.showinfo("Успіх", "Дані оновлено!")
            self.load_group_students(self.group_dropdown.get())
        except Exception as e:
            messagebox.showerror("Помилка", str(e))

    def delete_student_dialog(self):
        if not self.selected_group_table:
            return

        student_id = simpledialog.askinteger("Видалення", "Введіть ID студента для видалення:")
        if not student_id:
            return

        if messagebox.askyesno("Підтвердження", f"Видалити студента з ID {student_id}?"):
            try:
                conn = self.get_db_connection()
                cursor = conn.cursor()
                database.delete_student(cursor, self.selected_group_table, student_id)
                conn.commit()
                cursor.close()
                conn.close()

                messagebox.showinfo("Успіх", "Студента видалено!")
                self.load_group_students(self.group_dropdown.get())
            except Exception as e:
                messagebox.showerror("Помилка", str(e))

if __name__ == "__main__":
    app = StudentManagementApp()
    app.mainloop()