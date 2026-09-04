import psycopg2
import re

def sanitize_table_name(group_name):
    clean = re.sub(r'[^a-zA-Z0-9А-Яа-яіІїЇєЄ]', '_', group_name.lower())
    return f"group_{clean}"

def init_core_registry(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups_registry (
            id SERIAL PRIMARY KEY,
            group_name VARCHAR(50) UNIQUE NOT NULL,
            table_name VARCHAR(60) UNIQUE NOT NULL,
            study_year VARCHAR(50) NOT NULL,
            curator VARCHAR(150) NOT NULL
        );
    """)

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

def get_all_students_flat(cursor):
    init_core_registry(cursor)
    cursor.execute("SELECT table_name, group_name FROM groups_registry;")
    groups = cursor.fetchall()
    
    all_students = []
    for tbl, grp in groups:
        cursor.execute(f"SELECT id, full_name, group_name FROM {tbl};")
        rows = cursor.fetchall()
        for r in rows:
            all_students.append({"table": tbl, "id": r[0], "full_name": r[1], "group_name": r[2]})
    return all_students

def get_all_db_tables(cursor):
    """Отримує список усіх користувацьких таблиць у базі даних."""
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    return [row[0] for row in cursor.fetchall()]

def get_table_data(cursor, table_name):
    """Отримує колонки та всі рядки довільної таблиці."""
    cursor.execute(f"SELECT * FROM {table_name};")
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return columns, rows

def update_table_cell(cursor, table_name, column_name, new_value, row_id):
    """Оновлює конкретне поле в довільній таблиці за її ID."""
    cursor.execute(f"""
        UPDATE {table_name}
        SET {column_name} = %s
        WHERE id = %s;
    """, (new_value, row_id))

def delete_table_row(cursor, table_name, row_id):
    """Видаляє рядок з довільної таблиці за ID."""
    cursor.execute(f"DELETE FROM {table_name} WHERE id = %s;", (row_id,))

def drop_entire_table(cursor, table_name):
    """Повністю видаляє таблицю з бази даних (із каскадним видаленням залежностей)."""
    # Якщо видаляється таблиця групи, також видаляємо її з реєстру груп
    cursor.execute("DELETE FROM groups_registry WHERE table_name = %s;", (table_name,))
    cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")

def clear_rewards_and_ratings(cursor):
    init_core_registry(cursor)
    cursor.execute("TRUNCATE TABLE student_achievements, rewards_orders RESTART IDENTITY CASCADE;")

def clear_entire_database(cursor):
    init_core_registry(cursor)
    cursor.execute("SELECT table_name FROM groups_registry;")
    tables = cursor.fetchall()
    for t in tables:
        cursor.execute(f"DROP TABLE IF EXISTS {t[0]} CASCADE;")
    cursor.execute("TRUNCATE TABLE groups_registry, rewards_orders, student_achievements RESTART IDENTITY CASCADE;")