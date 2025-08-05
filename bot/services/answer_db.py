import sqlite3
from datetime import datetime

DB_FILE = "test_answers.db"  # Имя файла с базой данных

# 1. Создаём таблицу ответов (вызывается один раз при запуске)
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS test_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                answer_time TEXT,
                test_type INTEGER,
                question_id INTEGER,
                question_text TEXT,
                user_answer TEXT,
                correct_answer TEXT,
                is_correct INTEGER
            )
        ''')
        conn.commit()
    # --- Инициализация таблицы активности вопросов ---
    init_activity_table()

# 2. Запись одного ответа в таблицу test_answers
def save_test_answer(user_id, username, test_type, question_id, question_text, user_answer, correct_answer, is_correct):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO test_answers
            (user_id, username, answer_time, test_type, question_id, question_text, user_answer, correct_answer, is_correct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            username,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            test_type,
            question_id,
            question_text,
            user_answer,
            correct_answer,
            int(is_correct)
        ))
        conn.commit()

# 3. Сохраняем прогресс теста (таблица test_progress)
def save_test_progress(user_id, test_type, idx, q_ids):
    """
    Сохраняет прогресс теста: пользователя, номер теста, текущий вопрос и список id вопросов.
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS test_progress (
                user_id INTEGER,
                test_type INTEGER,
                idx INTEGER,
                q_ids TEXT,
                PRIMARY KEY (user_id, test_type)
            )
        ''')
        q_ids_str = ",".join(map(str, q_ids))
        c.execute('''
            INSERT OR REPLACE INTO test_progress (user_id, test_type, idx, q_ids)
            VALUES (?, ?, ?, ?)
        ''', (user_id, test_type, idx, q_ids_str))
        conn.commit()

def load_test_progress(user_id, test_type):
    """
    Возвращает (idx, q_ids) — номер текущего вопроса и список id вопросов, если пользователь уже проходил этот тест.
    Если не найдено — возвращает (None, None).
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('SELECT idx, q_ids FROM test_progress WHERE user_id=? AND test_type=?', (user_id, test_type))
        row = c.fetchone()
        if row:
            idx, q_ids_str = row
            q_ids = [int(qid) for qid in q_ids_str.split(',')]
            return idx, q_ids
        return None, None

def clear_test_progress(user_id, test_type):
    """
    Очищает прогресс прохождения теста (когда пользователь начинает заново).
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('DELETE FROM test_progress WHERE user_id=? AND test_type=?', (user_id, test_type))
        conn.commit()

def init_progress_table():
    """
    Создаёт таблицу для хранения прогресса тестов, если она ещё не создана.
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS test_progress (
                user_id INTEGER,
                test_type INTEGER,
                idx INTEGER,
                q_ids TEXT,
                PRIMARY KEY (user_id, test_type)
            )
        ''')
        conn.commit()

# ========================
#   РАБОТА НАД ОШИБКАМИ
# ========================

def get_mistake_questions(user_id):
    """
    Возвращает список кортежей (test_type, question_id, question_text, user_answer, correct_answer)
    для всех ошибочных заданий пользователя (is_correct=0).
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT test_type, question_id, question_text, user_answer, correct_answer
            FROM test_answers
            WHERE user_id=? AND is_correct=0
        """, (user_id,))
        return c.fetchall()

def set_answer_correct(user_id, question_id):
    """
    Помечает ошибку как исправленную (is_correct=1) для user_id и question_id.
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE test_answers SET is_correct=1 WHERE user_id=? AND question_id=?
        """, (user_id, question_id))
        conn.commit()

# ========================
#   ЛОГИРОВАНИЕ ВРЕМЕНИ НАЧАЛА ВОПРОСА И ОТВЕТА (НОВЫЙ ФУНКЦИОНАЛ)
# ========================

def init_activity_table():
    """
    Создаёт таблицу для логирования активности по вопросам: кто когда начал решать, когда ответил и с каким результатом.
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS test_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                test_type INTEGER,
                question_id INTEGER,
                started_at TEXT,
                answered_at TEXT,
                user_answer TEXT,
                is_correct INTEGER
            )
        ''')
        conn.commit()

def log_question_started(user_id, test_type, question_id):
    """
    Логируем начало показа вопроса пользователю: user_id, test_type, question_id, started_at=now.
    Остальные поля NULL (ответа пока нет).
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO test_activity
            (user_id, test_type, question_id, started_at)
            VALUES (?, ?, ?, ?)
        ''', (
            user_id,
            test_type,
            question_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

def log_question_answered(user_id, question_id, user_answer, is_correct):
    """
    Когда пользователь ответил — обновляем запись: answered_at, user_answer, is_correct
    (ищем по user_id, question_id и answered_at IS NULL).
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE test_activity
            SET answered_at=?, user_answer=?, is_correct=?
            WHERE user_id=? AND question_id=? AND answered_at IS NULL
        ''', (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_answer,
            int(is_correct),
            user_id,
            question_id
        ))
        conn.commit()
