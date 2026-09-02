import os
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import psycopg2

from database import init_database
from parser import parse_order_file

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class OrderAutomationApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Автоматизація роботи з документацією заступника директора")
        self.geometry("950x720")
        self.minsize(850, 600)

        self.file_path = None
        self.parsed_data = None

        self.create_widgets()

    def create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        db_frame = ctk.CTkFrame(self)
        db_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        db_frame.grid_columnconfigure(9, weight=1)

        ctk.CTkLabel(db_frame, text="Хост:").grid(row=0, column=0, padx=5, pady=10, sticky="w")
        self.host_entry = ctk.CTkEntry(db_frame, width=80)
        self.host_entry.insert(0, "localhost")
        self.host_entry.grid(row=0, column=1, padx=5, pady=10)

        ctk.CTkLabel(db_frame, text="Порт:").grid(row=0, column=2, padx=5, pady=10, sticky="w")
        self.port_entry = ctk.CTkEntry(db_frame, width=50)
        self.port_entry.insert(0, "5432")
        self.port_entry.grid(row=0, column=3, padx=5, pady=10)

        ctk.CTkLabel(db_frame, text="БД:").grid(row=0, column=4, padx=5, pady=10, sticky="w")
        self.dbname_entry = ctk.CTkEntry(db_frame, width=80)
        self.dbname_entry.insert(0, "college_db")
        self.dbname_entry.grid(row=0, column=5, padx=5, pady=10)

        ctk.CTkLabel(db_frame, text="Користувач:").grid(row=0, column=6, padx=5, pady=10, sticky="w")
        self.user_entry = ctk.CTkEntry(db_frame, width=80)
        self.user_entry.insert(0, "postgres")
        self.user_entry.grid(row=0, column=7, padx=5, pady=10)

        ctk.CTkLabel(db_frame, text="Пароль:").grid(row=0, column=8, padx=5, pady=10, sticky="w")
        self.pass_entry = ctk.CTkEntry(db_frame, width=80, show="*")
        self.pass_entry.grid(row=0, column=9, padx=5, pady=10)

        connect_btn = ctk.CTkButton(db_frame, text="Підключення", fg_color="#2b8a3e", hover_color="#237032", width=110, command=self.setup_db_connection)
        connect_btn.grid(row=0, column=10, padx=5, pady=10)

        clear_db_btn = ctk.CTkButton(db_frame, text="Очистити БД", fg_color="#c92a2a", hover_color="#a61e1e", width=100, command=self.clear_database)
        clear_db_btn.grid(row=0, column=11, padx=5, pady=10)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

        self.tab_upload = self.tabview.add("Обробка Наказу")
        self.tab_rating = self.tabview.add("Рейтинг студентів")

        self.setup_upload_tab()
        self.setup_rating_tab()

    def get_db_config(self):
        return {
            "host": self.host_entry.get().strip(),
            "port": self.port_entry.get().strip(),
            "database": self.dbname_entry.get().strip(),
            "user": self.user_entry.get().strip(),
            "password": self.pass_entry.get().strip()
        }

    def setup_db_connection(self):
        config = self.get_db_config()
        try:
            init_database(config)
            messagebox.showinfo("Успіх", "Підключення до PostgreSQL та ініціалізація таблиць пройшли успішно!")
            self.load_ratings()
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося підключитися до бази даних:\n{e}")

    def clear_database(self):
        if not messagebox.askyesno("Підтвердження", "Ви впевнені, що хочете видалити всі дані з бази даних?"):
            return

        config = self.get_db_config()
        try:
            conn = psycopg2.connect(**config)
            cursor = conn.cursor()
            cursor.execute("TRUNCATE TABLE achievements, orders, students RESTART IDENTITY CASCADE;")
            conn.commit()
            cursor.close()
            conn.close()
            messagebox.showinfo("Успіх", "Базу даних повністю очищено!")
            self.load_ratings()
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося очистити базу даних:\n{e}")

    def setup_upload_tab(self):
        self.tab_upload.grid_columnconfigure(0, weight=1)
        self.tab_upload.grid_rowconfigure(2, weight=1)

        file_frame = ctk.CTkFrame(self.tab_upload, fg_color="transparent")
        file_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.file_label = ctk.CTkLabel(file_frame, text="Файл наказу не вибрано", font=("Arial", 14))
        self.file_label.pack(side="left", padx=5)

        select_btn = ctk.CTkButton(file_frame, text="Вибрати файл наказу (.doc / .docx)", command=self.browse_file)
        select_btn.pack(side="right", padx=5)

        self.info_frame = ctk.CTkFrame(self.tab_upload)
        self.info_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.info_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.lbl_num = ctk.CTkLabel(self.info_frame, text="Номер наказу: —")
        self.lbl_num.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.lbl_date = ctk.CTkLabel(self.info_frame, text="Дата: —")
        self.lbl_date.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        self.lbl_level = ctk.CTkLabel(self.info_frame, text="Рівень заходу: —")
        self.lbl_level.grid(row=0, column=2, padx=10, pady=10, sticky="w")

        self.lbl_points = ctk.CTkLabel(self.info_frame, text="Бали: —")
        self.lbl_points.grid(row=0, column=3, padx=10, pady=10, sticky="w")

        table_container = ctk.CTkFrame(self.tab_upload)
        table_container.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        table_container.grid_columnconfigure(0, weight=1)
        table_container.grid_rowconfigure(0, weight=1)

        self.students_text = ctk.CTkTextbox(table_container, font=("Consolas", 13))
        self.students_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.students_text.insert("0.0", "Тут з'явиться список студентів після вибору файлу...")

        self.save_db_btn = ctk.CTkButton(self.tab_upload, text="Зберегти дані в БД та нарахувати бали", fg_color="#1864ab", hover_color="#0b5ed7", height=40, state="disabled", command=self.save_to_database)
        self.save_db_btn.grid(row=3, column=0, padx=10, pady=15, sticky="ew")

    def setup_rating_tab(self):
        self.tab_rating.grid_columnconfigure(0, weight=1)
        self.tab_rating.grid_rowconfigure(1, weight=1)

        top_bar = ctk.CTkFrame(self.tab_rating, fg_color="transparent")
        top_bar.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        refresh_btn = ctk.CTkButton(top_bar, text="Оновити рейтинг", command=self.load_ratings)
        refresh_btn.pack(side="left")

        rating_container = ctk.CTkFrame(self.tab_rating)
        rating_container.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        rating_container.grid_columnconfigure(0, weight=1)
        rating_container.grid_rowconfigure(0, weight=1)

        self.rating_text = ctk.CTkTextbox(rating_container, font=("Consolas", 13))
        self.rating_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    def browse_file(self):
        file_types = [("Word документи", "*.docx;*.doc"), ("Усі файли", "*.*")]
        path = filedialog.askopenfilename(filetypes=file_types)
        if path:
            self.file_path = path
            self.file_label.configure(text=f"Файл: {os.path.basename(path)}")
            try:
                self.parsed_data = parse_order_file(path)
                self.display_parsed_info()
                self.save_db_btn.configure(state="normal")
            except Exception as e:
                messagebox.showerror("Помилка парсингу", f"Не вдалося опрацювати файл:\n{e}")

    def display_parsed_info(self):
        if not self.parsed_data:
            return

        self.lbl_num.configure(text=f"Номер: {self.parsed_data['order_number']}")
        self.lbl_date.configure(text=f"Дата: {self.parsed_data['order_date']}")
        self.lbl_level.configure(text=f"Рівень: {self.parsed_data['level']}")
        self.lbl_points.configure(text=f"Бали за замовч.: {self.parsed_data['points']}")

        self.students_text.delete("0.0", "end")
        header = f"{'№':<4} | {'ПІБ Студента':<35} | {'Група':<15} | {'Бали':<5}\n"
        header += "-" * 65 + "\n"
        self.students_text.insert("end", header)

        for idx, student in enumerate(self.parsed_data['students'], 1):
            row = f"{idx:<4} | {student['full_name']:<35} | {student['group_name']:<15} | {student['points']:<5}\n"
            self.students_text.insert("end", row)

    def save_to_database(self):
        if not self.parsed_data or not self.parsed_data['students']:
            messagebox.showwarning("Попередження", "Немає даних для збереження!")
            return

        config = self.get_db_config()
        try:
            conn = psycopg2.connect(**config)
            cursor = conn.cursor()

            # 1. Зберігаємо або отримуємо наказ
            cursor.execute("""
                INSERT INTO orders (order_number, order_date, level)
                VALUES (%s, %s, %s)
                ON CONFLICT (order_number, order_date) DO UPDATE 
                SET level = EXCLUDED.level
                RETURNING id;
            """, (
                self.parsed_data['order_number'],
                self.parsed_data['order_date'],
                self.parsed_data['level']
            ))
            order_id = cursor.fetchone()[0]

            # 2. Додаємо/оновлюємо студентів (унікальних за ПІБ і групою) та сумуємо бали
            for student in self.parsed_data['students']:
                cursor.execute("""
                    INSERT INTO students (full_name, group_name, total_points)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (full_name, group_name) DO UPDATE 
                    SET total_points = students.total_points + EXCLUDED.total_points
                    RETURNING id;
                """, (
                    student['full_name'],
                    student['group_name'],
                    student['points']
                ))
                student_id = cursor.fetchone()[0]

                # Записуємо кожне конкретне досягнення у зв'язуючу таблицю
                cursor.execute("""
                    INSERT INTO achievements (student_id, order_id, points_awarded)
                    VALUES (%s, %s, %s);
                """, (student_id, order_id, student['points']))

            conn.commit()
            cursor.close()
            conn.close()

            messagebox.showinfo("Успіх", "Дані успішно збережено в БД PostgreSQL, а бали нараховано студентам!")
            self.load_ratings()
            self.tabview.set("Рейтинг студентів")

        except Exception as e:
            messagebox.showerror("Помилка БД", f"Помилка при збереженні в базу даних:\n{e}")

    def load_ratings(self):
        config = self.get_db_config()
        try:
            conn = psycopg2.connect(**config)
            cursor = conn.cursor()
            
            # Читаємо унікальних студентів із сумою їхніх балів із таблиці students
            cursor.execute("""
                SELECT full_name, group_name, total_points 
                FROM students 
                ORDER BY total_points DESC;
            """)
            rows = cursor.fetchall()
            
            cursor.close()
            conn.close()

            self.rating_text.delete("0.0", "end")
            header = f"{'Місце':<6} | {'ПІБ Студента':<35} | {'Група':<15} | {'Загалом балів':<12}\n"
            header += "-" * 75 + "\n"
            self.rating_text.insert("end", header)

            for idx, row in enumerate(rows, 1):
                line = f"{idx:<6} | {row[0]:<35} | {row[1]:<15} | {row[2]:<12}\n"
                self.rating_text.insert("end", line)

            if not rows:
                self.rating_text.insert("end", "База даних поки що порожня.")

        except Exception as e:
            self.rating_text.delete("0.0", "end")
            self.rating_text.insert("end", f"Не вдалося завантажити рейтинг (перевірте підключення до БД):\n{e}")

if __name__ == "__main__":
    app = OrderAutomationApp()
    app.mainloop()