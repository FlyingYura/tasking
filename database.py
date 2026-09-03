import psycopg2
import re

def sanitize_table_name(group_name):
    """Формує валідне ім'я таблиці для PostgreSQL, наприклад: group_ek_11."""
    clean = re.sub(r'[^a-zA-Z0-9А-Яа-яіІїЇєЄ]', '_', group_name.lower())
    return f"group_{clean}"

def init_core_registry(cursor):
    """Створює реєстр груп та базові таблиці."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups_registry (
            id SERIAL PRIMARY KEY,
            group_name VARCHAR(50) UNIQUE NOT NULL,
            table_name VARCHAR(60) UNIQUE NOT NULL,
            study_year VARCHAR(50) NOT NULL,
            curator VARCHAR(150) NOT NULL
        );
    """)

def create_group_table(cursor, group_name, study_year, curator):
    """Створює окрему таблицю для конкретної групи та реєструє її."""
    table_name = sanitize_table_name(group_name)
    
    init_core_registry(cursor)

    # Реєструємо або оновлюємо метадані групи
    cursor.execute("""
        INSERT INTO groups_registry (group_name, table_name, study_year, curator)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (group_name) DO UPDATE 
        SET study_year = EXCLUDED.study_year, curator = EXCLUDED.curator;
    """, (group_name, table_name, study_year, curator))

    # Створюємо індивідуальну таблицю групи
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(150) NOT NULL,
            group_name VARCHAR(50) NOT NULL,
            funding VARCHAR(10) NOT NULL,
            curator VARCHAR(150) NOT NULL,
            note TEXT DEFAULT '—'
        );
    """)
    return table_name

def insert_student(cursor, table_name, full_name, group_name, funding, curator, note):
    """Додає студента у таблицю відповідної групи."""
    cursor.execute(f"""
        INSERT INTO {table_name} (full_name, group_name, funding, curator, note)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
    """, (full_name, group_name, funding, curator, note))
    return cursor.fetchone()[0]

def update_student(cursor, table_name, student_id, full_name, funding, note):
    """Оновлює дані студента."""
    cursor.execute(f"""
        UPDATE {table_name}
        SET full_name = %s, funding = %s, note = %s
        WHERE id = %s;
    """, (full_name, funding, note, student_id))

def delete_student(cursor, table_name, student_id):
    """Видаляє студента за ID."""
    cursor.execute(f"DELETE FROM {table_name} WHERE id = %s;", (student_id,))

def get_all_registered_groups(cursor):
    """Повертає список зареєстрованих груп."""
    init_core_registry(cursor)
    cursor.execute("SELECT group_name, table_name, study_year, curator FROM groups_registry ORDER BY group_name;")
    return cursor.fetchall()

def get_students_from_group(cursor, table_name):
    """Отримує всіх студентів певної групи."""
    cursor.execute(f"SELECT id, full_name, group_name, funding, curator, note FROM {table_name} ORDER BY id;")
    return cursor.fetchall()