import psycopg2

def init_database(db_config):
    """Підключається до бази даних та створює необхідні таблиці із суворим обмеженням унікальності студентів."""
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # Створюємо таблицю студентів із унікальністю за ПІБ та групою
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(150) NOT NULL,
                group_name VARCHAR(50) NOT NULL,
                total_points INT DEFAULT 0,
                CONSTRAINT students_full_name_group_name_key UNIQUE (full_name, group_name)
            );
        """)
        
        # Таблиця наказів
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_number VARCHAR(50) NOT NULL,
                order_date VARCHAR(50) NOT NULL,
                level VARCHAR(50) NOT NULL,
                UNIQUE(order_number, order_date)
            );
        """)
        
        # Таблиця досягнень (зв'язок студента з наказом)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id SERIAL PRIMARY KEY,
                student_id INT REFERENCES students(id) ON DELETE CASCADE,
                order_id INT REFERENCES orders(id) ON DELETE CASCADE,
                points_awarded INT NOT NULL
            );
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Таблиці успішно ініціалізовано.")
    except Exception as e:
        print(f"Помилка при ініціалізації: {e}")
        raise e