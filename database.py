import psycopg2
import re

def sanitize_table_name(group_name):
    clean = re.sub(r'[^a-zA-Z0-9А-Яа-яіІїЇєЄ]', '_', group_name.lower())
    return f"group_{clean}"

def init_core_registry(cursor):
    """Створює реєстр груп та таблиці для нагороджень."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups_registry (
            id SERIAL PRIMARY KEY,
            group_name VARCHAR(50) UNIQUE NOT NULL,
            table_name VARCHAR(60) UNIQUE NOT NULL,
            study_year VARCHAR(50) NOT NULL,
            curator VARCHAR(150) NOT NULL
        );
    """)

    # Таблиця наказів про нагородження
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rewards_orders (
            id SERIAL PRIMARY KEY,
            order_number VARCHAR(50) NOT NULL,
            order_date VARCHAR(50) NOT NULL,
            event_title TEXT NOT NULL,
            level_type VARCHAR(50) NOT NULL,
            default_points INT NOT NULL,
            UNIQUE(order_number, order_date)
        );
    """)

    # Таблиця зв'язку студента з групи з наказом про нагородження
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_achievements (
            id SERIAL PRIMARY KEY,
            group_table_name VARCHAR(60) NOT NULL,
            student_id INT NOT NULL,
            order_id INT REFERENCES rewards_orders(id) ON DELETE CASCADE,
            points_awarded INT NOT NULL
        );
    """)

def create_group_table(cursor, group_name, study_year, curator):
    table_name = sanitize_table_name(group_name)
    init_core_registry(cursor)

    cursor.execute("""
        INSERT INTO groups_registry (group_name, table_name, study_year, curator)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (group_name) DO UPDATE 
        SET study_year = EXCLUDED.study_year, curator = EXCLUDED.curator;
    """, (group_name, table_name, study_year, curator))

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
    cursor.execute(f"""
        INSERT INTO {table_name} (full_name, group_name, funding, curator, note)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
    """, (full_name, group_name, funding, curator, note))
    return cursor.fetchone()[0]

def update_student(cursor, table_name, student_id, full_name, funding, note):
    cursor.execute(f"""
        UPDATE {table_name}
        SET full_name = %s, funding = %s, note = %s
        WHERE id = %s;
    """, (full_name, funding, note, student_id))

def delete_student(cursor, table_name, student_id):
    cursor.execute(f"DELETE FROM {table_name} WHERE id = %s;", (student_id,))

def get_all_registered_groups(cursor):
    init_core_registry(cursor)
    cursor.execute("SELECT group_name, table_name, study_year, curator FROM groups_registry ORDER BY group_name;")
    return cursor.fetchall()

def get_students_from_group(cursor, table_name):
    cursor.execute(f"SELECT id, full_name, funding, note FROM {table_name} ORDER BY id;")
    return cursor.fetchall()

def clear_entire_database(cursor):
    init_core_registry(cursor)
    cursor.execute("SELECT table_name FROM groups_registry;")
    tables = cursor.fetchall()
    for t in tables:
        cursor.execute(f"DROP TABLE IF EXISTS {t[0]} CASCADE;")
    cursor.execute("TRUNCATE TABLE groups_registry, rewards_orders, student_achievements RESTART IDENTITY CASCADE;")