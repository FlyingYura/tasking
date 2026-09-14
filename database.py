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

import json
import logging
import zipfile
from contextlib import contextmanager

import psycopg2
from psycopg2 import Binary

logger = logging.getLogger("app.database")

# Білий список таблиць і їх редагованих колонок — використовується панеллю
# "Середовище БД", щоб не підставляти довільні рядки від користувача
# напряму в SQL-ідентифікатори.
ALLOWED_TABLES = {
    "groups": ["name", "study_year", "curator"],
    "students": ["full_name", "funding", "note"],
    "orders": ["order_number", "order_date", "level_type", "default_points"],
    "achievements": ["points_awarded"],
    "teachers": ["full_name", "position"],
    "teacher_rewards": [],
}


class DatabaseError(Exception):
    pass


class Database:
    read_only = False

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
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS source_filename TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS source_file BYTEA;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teachers (
                    id SERIAL PRIMARY KEY,
                    full_name VARCHAR(200) NOT NULL UNIQUE,
                    position VARCHAR(150) DEFAULT '—'
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teacher_rewards (
                    id SERIAL PRIMARY KEY,
                    teacher_id INT NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
                    order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    UNIQUE(teacher_id, order_id)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_teacher_rewards_teacher ON teacher_rewards(teacher_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_teacher_rewards_order ON teacher_rewards(order_id);")

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
    def upsert_order(self, order_number, order_date, event_title, level_type, points, source_filename=None, source_file=None):
        file_param = Binary(source_file) if source_file else None
        with self.cursor() as cur:
            cur.execute("""
                INSERT INTO orders (order_number, order_date, event_title, level_type, default_points, source_filename, source_file)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_number, order_date) DO UPDATE
                SET event_title = EXCLUDED.event_title,
                    level_type = EXCLUDED.level_type,
                    default_points = EXCLUDED.default_points,
                    source_filename = COALESCE(EXCLUDED.source_filename, orders.source_filename),
                    source_file = COALESCE(EXCLUDED.source_file, orders.source_file)
                RETURNING id;
            """, (order_number, order_date, event_title, level_type, points, source_filename, file_param))
            return cur.fetchone()[0]

    def add_achievement(self, student_id, order_id, points):
        with self.cursor() as cur:
            cur.execute("""
                INSERT INTO achievements (student_id, order_id, points_awarded)
                VALUES (%s, %s, %s)
                ON CONFLICT (student_id, order_id) DO UPDATE SET points_awarded = EXCLUDED.points_awarded;
            """, (student_id, order_id, points))

    def get_rating(self, group_id=None):
        """Один запит з JOIN + GROUP BY. Підсумок не опускається нижче 0,
        але самі догани в нарахуваннях зберігаються зі знаком мінус."""
        with self.cursor() as cur:
            sql = """
                SELECT s.id, s.full_name, g.name,
                       GREATEST(0, COALESCE(SUM(a.points_awarded), 0)) AS total
                FROM students s
                JOIN groups g ON g.id = s.group_id
                LEFT JOIN achievements a ON a.student_id = s.id
            """
            if group_id:
                cur.execute(sql + """
                    WHERE g.id = %s
                    GROUP BY s.id, s.full_name, g.name
                    ORDER BY total DESC, s.full_name ASC;
                """, (group_id,))
            else:
                cur.execute(sql + """
                    GROUP BY s.id, s.full_name, g.name
                    ORDER BY total DESC, s.full_name ASC;
                """)
            return [
                {"student_id": r[0], "full_name": r[1], "group_name": r[2], "total": float(r[3] or 0)}
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
                SELECT o.id, o.order_number, o.order_date, o.event_title, o.level_type,
                       a.points_awarded, o.source_filename, (o.source_file IS NOT NULL)
                FROM achievements a
                JOIN orders o ON o.id = a.order_id
                WHERE a.student_id = %s
                ORDER BY o.order_date DESC, o.id DESC;
            """, (student_id,))
            return [
                {
                    "order_id": r[0],
                    "order_number": r[1],
                    "order_date": r[2],
                    "event_title": r[3],
                    "level_type": r[4],
                    "points": float(r[5] or 0),
                    "source_filename": r[6],
                    "has_file": bool(r[7]),
                }
                for r in cur.fetchall()
            ]

    def get_achievement_details(self):
        """Усі нарахування з реквізитами наказу — для Excel-експорту."""
        with self.cursor() as cur:
            cur.execute("""
                SELECT s.id, s.full_name, g.name,
                       o.order_number, o.order_date, o.event_title, o.level_type,
                       a.points_awarded, o.source_filename
                FROM achievements a
                JOIN students s ON s.id = a.student_id
                JOIN groups g ON g.id = s.group_id
                JOIN orders o ON o.id = a.order_id
                ORDER BY s.full_name, o.order_date, o.id;
            """)
            return [
                {
                    "student_id": r[0],
                    "full_name": r[1],
                    "group_name": r[2],
                    "order_number": r[3],
                    "order_date": r[4],
                    "event_title": r[5],
                    "level_type": r[6],
                    "points": float(r[7] or 0),
                    "source_filename": r[8],
                }
                for r in cur.fetchall()
            ]

    # -- викладачі / подяки викладачів ----------------------------------------
    def upsert_teacher(self, full_name, position="—"):
        with self.cursor() as cur:
            cur.execute("""
                INSERT INTO teachers (full_name, position)
                VALUES (%s, %s)
                ON CONFLICT (full_name) DO UPDATE
                SET position = COALESCE(EXCLUDED.position, teachers.position)
                RETURNING id;
            """, (full_name, position))
            return cur.fetchone()[0]

    def get_all_teachers(self):
        with self.cursor() as cur:
            cur.execute("SELECT id, full_name, position FROM teachers ORDER BY full_name;")
            return [
                {"id": r[0], "full_name": r[1], "position": r[2]}
                for r in cur.fetchall()
            ]

    def add_teacher_reward(self, teacher_id, order_id):
        with self.cursor() as cur:
            cur.execute("""
                INSERT INTO teacher_rewards (teacher_id, order_id)
                VALUES (%s, %s)
                ON CONFLICT (teacher_id, order_id) DO NOTHING;
            """, (teacher_id, order_id))

    def get_teacher_rewards(self):
        """Всі подяки викладачів з реквізитами наказу — для Excel-експорту."""
        with self.cursor() as cur:
            cur.execute("""
                SELECT t.id, t.full_name, t.position,
                       o.order_number, o.order_date, o.level_type, o.source_filename
                FROM teacher_rewards tr
                JOIN teachers t ON t.id = tr.teacher_id
                JOIN orders o ON o.id = tr.order_id
                ORDER BY t.full_name, o.order_date, o.id;
            """)
            return [
                {
                    "teacher_id": r[0],
                    "full_name": r[1],
                    "position": r[2],
                    "order_number": r[3],
                    "order_date": r[4],
                    "level_type": r[5],
                    "source_filename": r[6],
                }
                for r in cur.fetchall()
            ]

    def get_teacher_stats(self):
        """Статистика подяок викладачів: кількість подяк для кожного викладача."""
        with self.cursor() as cur:
            cur.execute("""
                SELECT t.id, t.full_name, t.position, COUNT(tr.order_id) as reward_count
                FROM teachers t
                LEFT JOIN teacher_rewards tr ON t.id = tr.teacher_id
                GROUP BY t.id, t.full_name, t.position
                ORDER BY reward_count DESC, t.full_name ASC;
            """)
            return [
                {
                    "teacher_id": r[0],
                    "full_name": r[1],
                    "position": r[2],
                    "reward_count": r[3] or 0,
                }
                for r in cur.fetchall()
            ]

    def get_teacher_history(self, teacher_id):
        with self.cursor() as cur:
            cur.execute("""
                SELECT o.id, o.order_number, o.order_date, o.level_type,
                       o.source_filename, (o.source_file IS NOT NULL)
                FROM teacher_rewards tr
                JOIN orders o ON o.id = tr.order_id
                WHERE tr.teacher_id = %s
                ORDER BY o.order_date DESC, o.id DESC;
            """, (teacher_id,))
            return [
                {
                    "order_id": r[0],
                    "order_number": r[1],
                    "order_date": r[2],
                    "level_type": r[3],
                    "source_filename": r[4],
                    "has_file": bool(r[5]),
                }
                for r in cur.fetchall()
            ]

    def get_order_attachment(self, order_id):
        with self.cursor() as cur:
            cur.execute(
                "SELECT source_filename, source_file FROM orders WHERE id = %s;",
                (order_id,),
            )
            row = cur.fetchone()
            if not row:
                return None, None
            filename, blob = row
            if blob is None:
                return filename, None
            return filename, bytes(blob)

    # -- обслуговування бази -------------------------------------------------
    def clear_rewards_and_ratings(self):
        with self.cursor() as cur:
            cur.execute("TRUNCATE TABLE achievements, orders RESTART IDENTITY CASCADE;")

    def clear_entire_database(self):
        with self.cursor() as cur:
            cur.execute("TRUNCATE TABLE teacher_rewards, teachers, achievements, orders, students, groups RESTART IDENTITY CASCADE;")

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
            elif table_name == "orders":
                cur.execute("""
                    SELECT id, order_number, order_date, level_type, default_points,
                           COALESCE(source_filename, '—') AS source_filename
                    FROM orders
                    ORDER BY id;
                """)
            elif table_name == "teachers":
                cur.execute("""
                    SELECT id, full_name, position
                    FROM teachers
                    ORDER BY full_name;
                """)
            elif table_name == "teacher_rewards":
                cur.execute("""
                    SELECT tr.id, t.full_name, o.order_number, o.order_date
                    FROM teacher_rewards tr
                    JOIN teachers t ON t.id = tr.teacher_id
                    JOIN orders o ON o.id = tr.order_id
                    ORDER BY t.full_name, o.order_date;
                """)
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

    def save_backup(self, file_path):
        """Зберігає повну копію даних (включно з файлами наказів) у .bak (ZIP)."""
        with self.cursor() as cur:
            cur.execute("SELECT id, name, study_year, curator FROM groups ORDER BY id;")
            groups = [
                {"id": r[0], "name": r[1], "study_year": r[2], "curator": r[3]}
                for r in cur.fetchall()
            ]
            cur.execute("SELECT id, full_name, group_id, funding, note FROM students ORDER BY id;")
            students = [
                {"id": r[0], "full_name": r[1], "group_id": r[2], "funding": r[3], "note": r[4]}
                for r in cur.fetchall()
            ]
            cur.execute("""
                SELECT id, order_number, order_date, event_title, level_type, default_points, source_filename
                FROM orders ORDER BY id;
            """)
            orders = [
                {
                    "id": r[0],
                    "order_number": r[1],
                    "order_date": r[2],
                    "event_title": r[3],
                    "level_type": r[4],
                    "default_points": float(r[5] or 0),
                    "source_filename": r[6],
                }
                for r in cur.fetchall()
            ]
            cur.execute("SELECT id, source_file FROM orders WHERE source_file IS NOT NULL;")
            files = {r[0]: bytes(r[1]) for r in cur.fetchall()}
            cur.execute("SELECT id, student_id, order_id, points_awarded FROM achievements ORDER BY id;")
            achievements = [
                {"id": r[0], "student_id": r[1], "order_id": r[2], "points_awarded": float(r[3] or 0)}
                for r in cur.fetchall()
            ]
            cur.execute("SELECT id, full_name, position FROM teachers ORDER BY id;")
            teachers = [
                {"id": r[0], "full_name": r[1], "position": r[2]}
                for r in cur.fetchall()
            ]
            cur.execute("SELECT id, teacher_id, order_id FROM teacher_rewards ORDER BY id;")
            teacher_rewards = [
                {"id": r[0], "teacher_id": r[1], "order_id": r[2]}
                for r in cur.fetchall()
            ]

        manifest = {
            "version": 1,
            "format": "aktiv-plus-backup",
            "groups": groups,
            "students": students,
            "orders": orders,
            "achievements": achievements,
            "teachers": teachers,
            "teacher_rewards": teacher_rewards,
        }
        with zipfile.ZipFile(file_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for order_id, blob in files.items():
                filename = next((o["source_filename"] for o in orders if o["id"] == order_id), None) or "order.bin"
                safe = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in filename)
                zf.writestr(f"files/{order_id}_{safe}", blob)

    def restore_backup(self, file_path):
        """Відновлює дані з .bak, повністю замінюючи поточний вміст таблиць."""
        manifest, file_blobs = read_backup_archive(file_path)

        with self.cursor() as cur:
            cur.execute("TRUNCATE TABLE teacher_rewards, teachers, achievements, orders, students, groups RESTART IDENTITY CASCADE;")
            for g in manifest.get("groups", []):
                cur.execute(
                    "INSERT INTO groups (id, name, study_year, curator) VALUES (%s, %s, %s, %s);",
                    (g["id"], g["name"], g["study_year"], g["curator"]),
                )
            for s in manifest.get("students", []):
                cur.execute(
                    "INSERT INTO students (id, full_name, group_id, funding, note) VALUES (%s, %s, %s, %s, %s);",
                    (s["id"], s["full_name"], s["group_id"], s.get("funding", "К"), s.get("note", "—")),
                )
            for o in manifest.get("orders", []):
                blob = file_blobs.get(o["id"])
                cur.execute(
                    """
                    INSERT INTO orders (id, order_number, order_date, event_title, level_type, default_points, source_filename, source_file)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        o["id"], o["order_number"], o["order_date"], o["event_title"],
                        o["level_type"], o["default_points"], o.get("source_filename"),
                        Binary(blob) if blob else None,
                    ),
                )
            for a in manifest.get("achievements", []):
                cur.execute(
                    "INSERT INTO achievements (id, student_id, order_id, points_awarded) VALUES (%s, %s, %s, %s);",
                    (a["id"], a["student_id"], a["order_id"], a["points_awarded"]),
                )
            for t in manifest.get("teachers", []):
                cur.execute(
                    "INSERT INTO teachers (id, full_name, position) VALUES (%s, %s, %s);",
                    (t["id"], t["full_name"], t.get("position", "—")),
                )
            for tr in manifest.get("teacher_rewards", []):
                cur.execute(
                    "INSERT INTO teacher_rewards (id, teacher_id, order_id) VALUES (%s, %s, %s);",
                    (tr["id"], tr["teacher_id"], tr["order_id"]),
                )
            for table in ("groups", "students", "orders", "achievements", "teachers", "teacher_rewards"):
                cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table};")  # nosec: whitelist
                max_id = cur.fetchone()[0]
                if max_id:
                    cur.execute(f"SELECT setval('{table}_id_seq', %s, true);", (max_id,))  # nosec: whitelist


def read_backup_archive(file_path):
    with zipfile.ZipFile(file_path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        if manifest.get("format") not in (None, "docflow-backup"):
            raise DatabaseError("Файл не є копією DocFlow.")
        file_blobs = {}
        for name in zf.namelist():
            if name.startswith("files/") and not name.endswith("/"):
                part = name.split("/", 1)[1]
                order_id_str = part.split("_", 1)[0]
                try:
                    file_blobs[int(order_id_str)] = zf.read(name)
                except ValueError:
                    continue
    return manifest, file_blobs


def load_backup_snapshot(file_path):
    manifest, files = read_backup_archive(file_path)
    return SnapshotDatabase(manifest, files, file_path)


class SnapshotDatabase:
    """Прочитана з .bak копія: ті самі методи читання, без запису в PostgreSQL."""

    read_only = True

    def __init__(self, manifest, files, source_path):
        self.source_path = source_path
        self.groups = list(manifest.get("groups") or [])
        self.students = list(manifest.get("students") or [])
        self.orders = list(manifest.get("orders") or [])
        self.achievements = list(manifest.get("achievements") or [])
        self.files = files or {}
        self._groups_by_id = {g["id"]: g for g in self.groups}
        self._students_by_id = {s["id"]: s for s in self.students}
        self._orders_by_id = {o["id"]: o for o in self.orders}

    def is_connected(self):
        return True

    def close(self):
        return None

    def _readonly(self):
        raise DatabaseError("Відкрита копія бази доступна лише для перегляду.")

    def upsert_group(self, *args, **kwargs):
        self._readonly()

    def upsert_student(self, *args, **kwargs):
        self._readonly()

    def upsert_order(self, *args, **kwargs):
        self._readonly()

    def add_achievement(self, *args, **kwargs):
        self._readonly()

    def update_table_cell(self, *args, **kwargs):
        self._readonly()

    def delete_table_row(self, *args, **kwargs):
        self._readonly()

    def clear_rewards_and_ratings(self):
        self._readonly()

    def clear_entire_database(self):
        self._readonly()

    def restore_backup(self, *args, **kwargs):
        self._readonly()

    def save_backup(self, *args, **kwargs):
        self._readonly()

    def get_groups(self):
        return [(g["id"], g["name"], g["study_year"], g["curator"]) for g in sorted(self.groups, key=lambda x: x["name"])]

    def get_students_by_group(self, group_id):
        rows = [s for s in self.students if s["group_id"] == group_id]
        rows.sort(key=lambda s: s["full_name"])
        return [(s["id"], s["full_name"], s.get("funding", "К"), s.get("note", "—")) for s in rows]

    def get_all_students_flat(self):
        result = []
        for s in self.students:
            group = self._groups_by_id.get(s["group_id"], {})
            result.append({
                "id": s["id"],
                "full_name": s["full_name"],
                "group_name": group.get("name", ""),
                "group_id": s["group_id"],
            })
        result.sort(key=lambda r: r["full_name"])
        return result

    def get_rating(self, group_id=None):
        totals = {}
        for a in self.achievements:
            totals[a["student_id"]] = totals.get(a["student_id"], 0) + float(a.get("points_awarded") or 0)
        rows = []
        for s in self.students:
            if group_id and s["group_id"] != group_id:
                continue
            group = self._groups_by_id.get(s["group_id"], {})
            rows.append({
                "student_id": s["id"],
                "full_name": s["full_name"],
                "group_name": group.get("name", ""),
                "total": max(0.0, totals.get(s["id"], 0.0)),
            })
        rows.sort(key=lambda r: (-r["total"], r["full_name"]))
        return rows

    def get_student_history(self, student_id):
        items = []
        for a in self.achievements:
            if a["student_id"] != student_id:
                continue
            order = self._orders_by_id.get(a["order_id"], {})
            items.append({
                "order_id": order.get("id", a["order_id"]),
                "order_number": order.get("order_number"),
                "order_date": order.get("order_date"),
                "event_title": order.get("event_title") or "—",
                "level_type": order.get("level_type"),
                "points": float(a.get("points_awarded") or 0),
                "source_filename": order.get("source_filename"),
                "has_file": a["order_id"] in self.files or bool(order.get("source_filename")),
            })
            items[-1]["has_file"] = a["order_id"] in self.files
        items.sort(key=lambda x: (x.get("order_date") or "", x.get("order_id") or 0), reverse=True)
        return items

    def get_achievement_details(self):
        rows = []
        for a in self.achievements:
            student = self._students_by_id.get(a["student_id"], {})
            group = self._groups_by_id.get(student.get("group_id"), {})
            order = self._orders_by_id.get(a["order_id"], {})
            rows.append({
                "student_id": a["student_id"],
                "full_name": student.get("full_name", ""),
                "group_name": group.get("name", ""),
                "order_number": order.get("order_number"),
                "order_date": order.get("order_date"),
                "event_title": order.get("event_title") or "—",
                "level_type": order.get("level_type"),
                "points": float(a.get("points_awarded") or 0),
                "source_filename": order.get("source_filename"),
            })
        rows.sort(key=lambda r: (r["full_name"], r.get("order_date") or ""))
        return rows

    def get_order_attachment(self, order_id):
        order = self._orders_by_id.get(int(order_id), {})
        blob = self.files.get(int(order_id))
        return order.get("source_filename"), blob

    def get_all_db_tables(self):
        return list(ALLOWED_TABLES.keys())

    def get_table_data(self, table_name, group_id=None):
        if table_name not in ALLOWED_TABLES:
            raise DatabaseError(f"Таблиця '{table_name}' недоступна для перегляду.")
        if table_name == "groups":
            columns = ["id", "name", "study_year", "curator"]
            rows = [(g["id"], g["name"], g["study_year"], g["curator"]) for g in self.groups]
        elif table_name == "students":
            columns = ["id", "full_name", "group_name", "funding", "note"]
            rows = []
            for s in self.students:
                if group_id and s["group_id"] != group_id:
                    continue
                group = self._groups_by_id.get(s["group_id"], {})
                rows.append((s["id"], s["full_name"], group.get("name", ""), s.get("funding", "К"), s.get("note", "—")))
        elif table_name == "orders":
            columns = ["id", "order_number", "order_date", "level_type", "default_points", "source_filename"]
            rows = [
                (o["id"], o["order_number"], o["order_date"], o["level_type"], o.get("default_points"), o.get("source_filename") or "—")
                for o in self.orders
            ]
        else:
            columns = ["id", "student_id", "order_id", "points_awarded"]
            rows = [(a["id"], a["student_id"], a["order_id"], a.get("points_awarded")) for a in self.achievements]
        return columns, rows
