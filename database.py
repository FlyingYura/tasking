"""
Шар доступу до бази даних PostgreSQL.

Головна відмінність від початкової версії: замість того, щоб створювати
окрему SQL-таблицю на кожну академічну групу (group_ek11, group_or21, ...),
використовується класична нормалізована схема з чотирьох таблиць:

    groups        — довідник груп
    students      — усі студенти, з посиланням на групу (group_id)
    orders        — накази/заходи
    achievements  — нарахування балів (студент x наказ)

Це усуває потребу в динамічному DDL (CREATE TABLE на кожну групу),
дозволяє робити нормальні JOIN/GROUP BY одним запитом замість циклу
по всіх групових таблицях, і не "ламається" при перейменуванні групи.

Для операцій перегляду/редагування довільної таблиці в бічній панелі
("Середовище БД") дозволені лише таблиці й колонки з явного білого списку —
це прибирає ризик підстановки довільних імен колонок/таблиць у SQL.
"""

import logging
from contextlib import contextmanager

import psycopg2

logger = logging.getLogger("app.database")

# Білий список таблиць і їх редагованих колонок — використовується панеллю
# "Середовище БД", щоб не підставляти довільні рядки від користувача
# напряму в SQL-ідентифікатори.
ALLOWED_TABLES = {
    "groups": ["name", "study_year", "curator"],
    "students": ["full_name", "funding", "note"],
    "orders": ["order_number", "order_date", "event_title", "level_type", "default_points"],
    "achievements": ["points_awarded"],
}


class DatabaseError(Exception):
    pass


class Database:
    def __init__(self, host, port, dbname, user, password):
        self.conn_params = dict(host=host, port=port, dbname=dbname, user=user, password=password)
        self._conn = None

    # -- підключення -----------------------------------------------------
    def connect(self):
        self._conn = psycopg2.connect(connect_timeout=6, **self.conn_params)
        self._conn.autocommit = False
        self.init_schema()
        return self

    def is_connected(self):
        return self._conn is not None and not self._conn.closed

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    @contextmanager
    def cursor(self):
        if not self.is_connected():
            raise DatabaseError("Немає активного з'єднання з базою даних.")
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            logger.exception("Помилка виконання запиту до БД")
            raise
        finally:
            cur.close()

    # -- схема -------------------------------------------------------------
    def init_schema(self):
        with self.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(20) UNIQUE NOT NULL,
                    study_year VARCHAR(20) NOT NULL,
                    curator VARCHAR(150) NOT NULL DEFAULT 'Не вказано'
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    id SERIAL PRIMARY KEY,
                    full_name VARCHAR(200) NOT NULL,
                    group_id INT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                    funding VARCHAR(10) NOT NULL DEFAULT 'К',
                    note TEXT DEFAULT '—',
                    UNIQUE(full_name, group_id)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    order_number VARCHAR(50) NOT NULL,
                    order_date VARCHAR(50) NOT NULL,
                    event_title TEXT NOT NULL,
                    level_type VARCHAR(50) NOT NULL,
                    default_points NUMERIC(8,2) NOT NULL,
                    UNIQUE(order_number, order_date)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id SERIAL PRIMARY KEY,
                    student_id INT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    points_awarded NUMERIC(8,2) NOT NULL,
                    UNIQUE(student_id, order_id)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_students_group ON students(group_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_achievements_student ON achievements(student_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_achievements_order ON achievements(order_id);")
            # Існуючі бази створювались з INT; дробові бали доган (0.5) потребують NUMERIC.
            cur.execute("ALTER TABLE orders ALTER COLUMN default_points TYPE NUMERIC(8,2);")
            cur.execute("ALTER TABLE achievements ALTER COLUMN points_awarded TYPE NUMERIC(8,2);")

    # -- групи / студенти ---------------------------------------------------
    def upsert_group(self, name, study_year, curator):
        with self.cursor() as cur:
            cur.execute("""
                INSERT INTO groups (name, study_year, curator)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE
                SET study_year = EXCLUDED.study_year,
                    curator = COALESCE(NULLIF(EXCLUDED.curator, 'Не вказано'), groups.curator)
                RETURNING id;
            """, (name, study_year, curator))
            return cur.fetchone()[0]

    def upsert_student(self, full_name, group_id, funding, note):
        with self.cursor() as cur:
            cur.execute("""
                INSERT INTO students (full_name, group_id, funding, note)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (full_name, group_id) DO UPDATE
                SET funding = EXCLUDED.funding, note = EXCLUDED.note
                RETURNING id;
            """, (full_name, group_id, funding, note))
            return cur.fetchone()[0]

    def get_groups(self):
        with self.cursor() as cur:
            cur.execute("SELECT id, name, study_year, curator FROM groups ORDER BY name;")
            return cur.fetchall()

    def get_students_by_group(self, group_id):
        with self.cursor() as cur:
            cur.execute("""
                SELECT id, full_name, funding, note FROM students
                WHERE group_id = %s ORDER BY full_name;
            """, (group_id,))
            return cur.fetchall()

    def get_all_students_flat(self):
        """Повертає всіх студентів разом із назвою групи — для співставлення з наказами."""
        with self.cursor() as cur:
            cur.execute("""
                SELECT s.id, s.full_name, g.name, g.id
                FROM students s
                JOIN groups g ON g.id = s.group_id
                ORDER BY s.full_name;
            """)
            return [
                {"id": r[0], "full_name": r[1], "group_name": r[2], "group_id": r[3]}
                for r in cur.fetchall()
            ]

    # -- накази / нарахування балів -----------------------------------------
    def upsert_order(self, order_number, order_date, event_title, level_type, points):
        with self.cursor() as cur:
            cur.execute("""
                INSERT INTO orders (order_number, order_date, event_title, level_type, default_points)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (order_number, order_date) DO UPDATE
                SET event_title = EXCLUDED.event_title,
                    level_type = EXCLUDED.level_type,
                    default_points = EXCLUDED.default_points
                RETURNING id;
            """, (order_number, order_date, event_title, level_type, points))
            return cur.fetchone()[0]

    def add_achievement(self, student_id, order_id, points):
        with self.cursor() as cur:
            cur.execute("""
                INSERT INTO achievements (student_id, order_id, points_awarded)
                VALUES (%s, %s, %s)
                ON CONFLICT (student_id, order_id) DO UPDATE SET points_awarded = EXCLUDED.points_awarded;
            """, (student_id, order_id, points))

    def get_rating(self, group_id=None):
        """Один запит з JOIN + GROUP BY замість циклу по кожній таблиці групи."""
        with self.cursor() as cur:
            if group_id:
                cur.execute("""
                    SELECT s.full_name, g.name, COALESCE(SUM(a.points_awarded), 0) AS total
                    FROM students s
                    JOIN groups g ON g.id = s.group_id
                    LEFT JOIN achievements a ON a.student_id = s.id
                    WHERE g.id = %s
                    GROUP BY s.id, s.full_name, g.name
                    ORDER BY total DESC, s.full_name ASC;
                """, (group_id,))
            else:
                cur.execute("""
                    SELECT s.full_name, g.name, COALESCE(SUM(a.points_awarded), 0) AS total
                    FROM students s
                    JOIN groups g ON g.id = s.group_id
                    LEFT JOIN achievements a ON a.student_id = s.id
                    GROUP BY s.id, s.full_name, g.name
                    ORDER BY total DESC, s.full_name ASC;
                """)
            return [
                {"full_name": r[0], "group_name": r[1], "total": float(r[2] or 0)}
                for r in cur.fetchall()
            ]

    def get_student_totals(self):
        """Поточний рейтинг кожного студента: {student_id: total}."""
        with self.cursor() as cur:
            cur.execute("""
                SELECT student_id, COALESCE(SUM(points_awarded), 0)
                FROM achievements
                GROUP BY student_id;
            """)
            return {r[0]: float(r[1] or 0) for r in cur.fetchall()}

    def get_student_history(self, student_id):
        with self.cursor() as cur:
            cur.execute("""
                SELECT o.order_number, o.order_date, o.event_title, a.points_awarded
                FROM achievements a
                JOIN orders o ON o.id = a.order_id
                WHERE a.student_id = %s
                ORDER BY o.order_date DESC;
            """, (student_id,))
            return cur.fetchall()

    # -- обслуговування бази -------------------------------------------------
    def clear_rewards_and_ratings(self):
        with self.cursor() as cur:
            cur.execute("TRUNCATE TABLE achievements, orders RESTART IDENTITY CASCADE;")

    def clear_entire_database(self):
        with self.cursor() as cur:
            cur.execute("TRUNCATE TABLE achievements, orders, students, groups RESTART IDENTITY CASCADE;")

    def get_all_db_tables(self):
        return list(ALLOWED_TABLES.keys())

    def get_table_data(self, table_name, group_id=None):
        if table_name not in ALLOWED_TABLES:
            raise DatabaseError(f"Таблиця '{table_name}' недоступна для перегляду.")
        with self.cursor() as cur:
            if table_name == "students":
                sql = """
                    SELECT s.id, s.full_name, g.name AS group_name, s.funding, s.note
                    FROM students s
                    JOIN groups g ON g.id = s.group_id
                """
                if group_id:
                    cur.execute(sql + " WHERE s.group_id = %s ORDER BY s.full_name;", (group_id,))
                else:
                    cur.execute(sql + " ORDER BY g.name, s.full_name;")
            else:
                cur.execute(f"SELECT * FROM {table_name} ORDER BY id;")  # nosec: table_name whitelisted above
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return columns, rows

    def update_table_cell(self, table_name, column_name, new_value, row_id):
        if table_name not in ALLOWED_TABLES or column_name not in ALLOWED_TABLES[table_name]:
            raise DatabaseError("Редагування цього поля заборонено.")
        with self.cursor() as cur:
            cur.execute(
                f"UPDATE {table_name} SET {column_name} = %s WHERE id = %s;",  # nosec: whitelisted above
                (new_value, row_id),
            )

    def delete_table_row(self, table_name, row_id):
        if table_name not in ALLOWED_TABLES:
            raise DatabaseError(f"Таблиця '{table_name}' недоступна.")
        with self.cursor() as cur:
            cur.execute(f"DELETE FROM {table_name} WHERE id = %s;", (row_id,))  # nosec: whitelisted above
