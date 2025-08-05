from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- 1. Регистрируем шрифт для поддержки кириллицы ---
import os
FONT_PATH = os.path.join(os.path.dirname(__file__), "PTSans-Regular.ttf")
pdfmetrics.registerFont(TTFont("PTSans", FONT_PATH))

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

import sqlite3
from .test_sql import get_questions_by_type
from bot.utils import ALL_TOPICS   # Если нужен для блока "прогресс по темам"

DB_FILE = "test_answers.db"  # Имя файла базы данных

# --- 2. (Необязательная) Функция для статистики по теме (если понадобится) ---
def get_test_stats_for_user_by_topic(user_id, topic_name):
    """
    Возвращает (total, done, correct, wrong):
    - total   — всего вопросов по теме,
    - done    — сколько решено учеником,
    - correct — сколько верно,
    - wrong   — сколько ошибок
    """
    try:
        test_type = ALL_TOPICS.index(topic_name) + 1  # test_type = номер темы
    except ValueError:
        return 0, 0, 0, 0
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM test_answers WHERE user_id=? AND test_type=?", (user_id, test_type))
        done = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM test_answers WHERE user_id=? AND test_type=? AND is_correct=1", (user_id, test_type))
        correct = c.fetchone()[0]
        wrong = done - correct
        total = len(get_questions_by_type(test_type))
        return total, done, correct, wrong

# --- 3. Главная функция: генерация PDF-отчёта по ученику ---
def make_report(user_id, username, records, filename="report.pdf"):
    """
    Генерирует PDF-отчёт по обучению ученика:
    user_id — Telegram ID,
    username — ФИО/ник,
    records — список словарей: [{"Тема": ..., "Дата и время": ..., "Комментарий GPT": ...}, ...]
    filename — имя итогового PDF-файла
    """

    # --- Стили оформления (fontName="PTSans" обязательно!) ---
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Header", fontName="PTSans", fontSize=18, alignment=TA_CENTER, textColor=colors.HexColor("#3B82F6")))
    styles.add(ParagraphStyle(name="TopicTitle", fontName="PTSans", fontSize=14, spaceAfter=6, textColor=colors.HexColor("#8B5CF6")))
    styles.add(ParagraphStyle(name="NormalText", fontName="PTSans", fontSize=11, leading=14))
    styles.add(ParagraphStyle(name="GPTBlock", fontName="PTSans", fontSize=10, leading=14, textColor=colors.HexColor("#16A34A")))

    doc = SimpleDocTemplate(filename, pagesize=A4)
    story = []

    # --- Заголовок, имя, Telegram ID ---
    story.append(Paragraph("🧑‍🔬 Индивидуальный отчёт по химии", styles["Header"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"ФИО/ник: <b>{username}</b>", styles["NormalText"]))
    story.append(Paragraph(f"Telegram ID: <b>{user_id}</b>", styles["NormalText"]))
    story.append(Spacer(1, 12))

    # --- Прогресс по темам (✓ если есть хоть одно задание, – если нет) ---
    done = {r["Тема"] for r in records}
    story.append(Paragraph("Прогресс по темам:", styles["TopicTitle"]))
    for topic in ALL_TOPICS:
        mark = "✓" if topic in done else "–"
        story.append(Paragraph(f"{mark} {topic}", styles["NormalText"]))

    # --- Горизонтальная линия перед статистикой тестов ---
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#8B5CF6")))
    story.append(Paragraph("Статистика по выполнению заданий:", styles["TopicTitle"]))

    # --- 4. Улучшенная таблица по каждому тесту: цвет, маркер, линия ---
    NUM_TESTS = 28  # Если тестов больше — поменяй число!

    for test_num in range(1, NUM_TESTS + 1):
        total = len(get_questions_by_type(test_num))
        done_tasks, correct, wrong = 0, 0, 0
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM test_answers WHERE user_id=? AND test_type=?", (user_id, test_num))
            done_tasks = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM test_answers WHERE user_id=? AND test_type=? AND is_correct=1", (user_id, test_num))
            correct = c.fetchone()[0]
            wrong = done_tasks - correct

        # --- Новый критерий цвета и иконки ---
        if correct >= 15 and done_tasks == total and total != 0:
            icon = "✔️"
            color = "#22C55E"  # Зелёный
        elif 8 <= correct < 15:
            icon = "⚠️"
            color = "#F59E42"  # Жёлтый
        elif correct < 8 and done_tasks > 0:
            icon = "❌"
            color = "#EF4444"  # Красный
        else:
            icon = "❌"
            color = "#B0B0B0"  # Серый если не приступал

        stats_text = (
            f"{icon} <b>Тест {test_num}</b>: <b>{done_tasks}</b> из <b>{total}</b>, "
            f"верных <b>{correct}</b>, ошибок <b>{wrong}</b>"
        )

        story.append(Paragraph(stats_text, ParagraphStyle(
            name=f"TestStats_{test_num}",
            fontName="PTSans",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor(color)
        )))
    # Разделитель после статистики:
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#8B5CF6")))
    story.append(Spacer(1, 12))

    # --- Подробные комментарии GPT по каждой теме ---
    for r in records:
        story.append(Paragraph(f"Тема: {r['Тема']}", styles["TopicTitle"]))
        story.append(Paragraph(f"Время: {r['Дата и время']}", styles["NormalText"]))
        comment = r["Комментарий GPT"].replace("\n", "<br/>")
        story.append(Paragraph(f"GPT:<br/>{comment}", styles["GPTBlock"]))
        story.append(Spacer(1, 12))

    # --- Сохраняем PDF ---
    doc.build(story)
    return filename
