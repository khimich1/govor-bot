import os
from aiogram import Router, Bot, types
from aiogram.enums import ParseMode
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command, CommandStart

from .utils import (
    ALL_TOPICS, clean_html, user_topics, LEARNING_TOPICS,
    user_learning_state, TEXTBOOK_CONTENT, latex_to_codeblock
)
from .gpt_service import (
    classify_topic, analyze_answer, transcribe_audio,
    teach_material, answer_student_question
)
from .spreadsheet import save_answer, fetch_user_records
from .pdf_generator import make_report
from .test_sql import (
    get_all_tests_types, get_questions_by_type, get_question_by_id
)

router = Router()
user_test_state = {}

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📄 Получить отчёт")],
        [KeyboardButton(text="❓ Как работает бот?"), KeyboardButton(text="🧪 Темы")],
        [KeyboardButton(text="🌱 Курс по органике"), KeyboardButton(text="▶️ Продолжить")],
        [KeyboardButton(text="📝 Тесты")]
    ],
    resize_keyboard=True
)

topics_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text=ALL_TOPICS[i]),
            KeyboardButton(text=ALL_TOPICS[i+1] if i+1 < len(ALL_TOPICS) else "")
        ]
        for i in range(0, len(ALL_TOPICS), 2)
    ] + [[KeyboardButton(text="⬅️ В меню")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

after_topic_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⬅️ К темам"), KeyboardButton(text="⬅️ В меню")]
    ],
    resize_keyboard=True
)

choose_chapter_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⬅️ В меню")]
    ],
    resize_keyboard=True,
)

def get_tests_types_kb():
    types = get_all_tests_types()
    keyboard = [
        [InlineKeyboardButton(text=f"Тест {t}", callback_data=f"choose_test_{t}")]
        for t in types if t not in (None, '')
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.message(CommandStart())
async def cmd_start(m: types.Message):
    await m.answer(
        "Привет! Я бот-химик 🎓\n"
        "• Отправь текст/голос — я расшифрую и прокомментирую.\n"
        "• 🧪 Темы — тестовые вопросы.\n"
        "• 🌱 Курс по органике — по главам из учебника.\n"
        "• ▶️ Продолжить — возобновить курс.\n"
        "• 📄 Получить отчёт — PDF с прогрессом.\n"
        "• 📝 Тесты — пройти готовые тесты.",
        reply_markup=main_kb
    )

@router.message(lambda m: m.text == "⬅️ В меню")
async def back_to_menu(m: types.Message):
    await m.answer("Главное меню:", reply_markup=main_kb)

@router.message(Command("menu"))
async def show_menu_cmd(m: types.Message):
    await m.answer("Главное меню:", reply_markup=main_kb)

@router.message(lambda m: m.text == "🧪 Темы")
async def show_topics(m: types.Message):
    await m.answer("Выберите тему по органической химии:", reply_markup=topics_kb)

@router.message(lambda m: m.text in ALL_TOPICS)
async def ask_questions(m: types.Message):
    user_topics[m.from_user.id] = m.text
    questions = (
        f"1. Общая характеристика класса {m.text}\n"
        f"2. Способы получения {m.text}\n"
        f"3. Химические свойства {m.text}"
    )
    await m.answer(questions, reply_markup=after_topic_kb)
    await m.answer("Запишите голосовой ответ на эти вопросы:")

@router.message(lambda m: m.text == "⬅️ К темам")
async def back_to_topics(m: types.Message):
    await m.answer("Выберите тему по органической химии:", reply_markup=topics_kb)

# ========== Тесты ==========

@router.message(lambda m: m.text == "📝 Тесты")
async def show_tests_types_menu(m: types.Message):
    await m.answer("Выбери номер теста:", reply_markup=get_tests_types_kb())

@router.message(Command("tests"))
async def show_tests_menu_cmd(m: types.Message):
    await show_tests_types_menu(m)

@router.callback_query(lambda c: c.data.startswith("choose_test_"))
async def start_test(cb: CallbackQuery):
    try:
        test_type = int(cb.data.split("_")[-1])
    except ValueError:
        await cb.answer("Ошибка: неверный номер теста.")
        return
    questions = get_questions_by_type(test_type)
    if not questions:
        await cb.message.answer("Нет вопросов для этого теста.", reply_markup=main_kb)
        await cb.answer()
        return
    user_test_state[cb.from_user.id] = {
        "type": test_type,
        "idx": 0,
        "q_ids": [q["id"] for q in questions]
    }
    await send_next_test_question(cb.from_user.id, cb.message, is_callback=True)
    await cb.answer()

async def send_next_test_question(user_id, message_obj, is_callback=False):
    state = user_test_state.get(user_id)
    if not state:
        return
    idx = state["idx"]
    q_ids = state["q_ids"]
    if idx >= len(q_ids):
        user_test_state.pop(user_id, None)
        await message_obj.answer("Тест завершён! Возвращаюсь в меню.", reply_markup=main_kb)
        return
    q = get_question_by_id(q_ids[idx])
    options = q['options'].split('\n')
    msg = (
        f"Вопрос {idx+1} из {len(q_ids)} (Тест {state['type']})\n\n"
        f"{q['question']}\n\n" +
        "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)]) +
        "\n\nВведите номер(а) ответа (например: 2 или 13):"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💡 Подсказка", callback_data=f"hint_{q['id']}")]
        ]
    )
    await message_obj.answer(msg, reply_markup=kb)

@router.callback_query(lambda c: c.data.startswith("hint_"))
async def show_hint(cb: CallbackQuery):
    q_id = int(cb.data.split("_")[-1])
    q = get_question_by_id(q_id)
    hint = q.get('hint', '')
    if hint and hint.strip():
        await cb.message.answer(f"💡 Подсказка:\n{hint}")
    else:
        await cb.message.answer("Для этого задания нет подсказки.")
    await cb.answer()

@router.message(lambda m: m.from_user.id in user_test_state)
async def check_test_answer(m: types.Message):
    state = user_test_state.get(m.from_user.id)
    idx = state["idx"]
    q_ids = state["q_ids"]
    q = get_question_by_id(q_ids[idx])
    user_answer = ''.join(filter(str.isdigit, m.text))
    correct = ''.join(filter(str.isdigit, str(q.get("correct_answer", ""))))
    if user_answer == correct:
        resp = "✅ Верно!"
    else:
        resp = f"❌ Неверно. Правильный ответ: {correct}"
    # Вот здесь! Показываем либо explanation, либо detailed_explanation, если есть.
    explanation = q.get("explanation", "") or q.get("detailed_explanation", "")
    if explanation and explanation.strip():
        resp += f"\n\n{explanation}"

    await m.answer(resp)
    user_test_state[m.from_user.id]["idx"] += 1
    await send_next_test_question(m.from_user.id, m)

# ========== Обычные команды меню ==========

@router.message(Command("resume"))
async def resume_cmd(m: types.Message, bot: Bot):
    await cmd_resume(m, bot)

@router.message(Command("report"))
async def report_cmd(m: types.Message):
    await btn_report(m)

@router.message(Command("help"))
async def help_cmd(m: types.Message):
    await how_it_works(m)

@router.message(lambda m: m.text == "❓ Как работает бот?")
async def how_it_works(m: types.Message):
    await m.answer(
        "Я принимаю текст или голос, определяю тему, даю комментарий через GPT, "
        "сохраняю результат в Google Sheets и формирую PDF-отчёт.",
        reply_markup=main_kb
    )

@router.message(lambda m: m.text == "📄 Получить отчёт")
async def btn_report(m: types.Message):
    records = fetch_user_records(m.from_user.id)
    if not records:
        return await m.answer("Ты ещё не сдал ни одной темы.", reply_markup=main_kb)
    pdf_path = make_report(m.from_user.id, m.from_user.full_name, records)
    await m.answer_document(FSInputFile(pdf_path), reply_markup=main_kb)

@router.message(lambda m: m.text == "▶️ Продолжить")
async def cmd_resume(m: types.Message, bot: Bot):
    st = user_learning_state.get(m.from_user.id)
    if not st:
        return await m.answer("Нет активного курса. Нажми 🌱 Курс по органике, чтобы начать.", reply_markup=main_kb)
    if st.get("awaiting_question"):
        return await m.answer("Вы в режиме вопроса. Задайте ваш вопрос.", reply_markup=ReplyKeyboardRemove())
    await m.answer(f"Возобновляем курс: {st['topic']}", reply_markup=ReplyKeyboardRemove())
    await send_next_chunk(m.from_user.id, bot)

# ========== Курс по органике ==========

@router.message(lambda m: m.text == "🌱 Курс по органике")
async def on_learning_start(m: types.Message):
    buttons = [
        [InlineKeyboardButton(text=topic, callback_data=f"learn_topic_{i}")]
        for i, topic in enumerate(LEARNING_TOPICS)
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await m.answer(
        "Выберите главу для курса по органике:",
        reply_markup=kb
    )
    await m.answer(
        "Можешь в любой момент вернуться в меню:",
        reply_markup=choose_chapter_kb
    )

@router.callback_query(lambda c: c.data.startswith("learn_topic_"))
async def on_topic_chosen(cb: CallbackQuery, bot: Bot):
    idx = int(cb.data.split("learn_topic_")[-1])
    topic = LEARNING_TOPICS[idx]
    user_learning_state[cb.from_user.id] = {"topic": topic, "index": 0, "awaiting_question": False}
    await send_next_chunk(cb.from_user.id, bot)

async def send_next_chunk(user_id: int, bot: Bot):
    st = user_learning_state.get(user_id)
    if not st:
        return
    topic = st["topic"]
    idx = st["index"]
    chunks = TEXTBOOK_CONTENT.get(topic, [])
    total = len(chunks)
    chap_num = LEARNING_TOPICS.index(topic) + 1
    chap_total = len(LEARNING_TOPICS)

    if idx >= total:
        await bot.send_message(
            user_id,
            f"Глава {topic} пройдена! 🎉\nВозвращаю меню.",
            reply_markup=main_kb
        )
        user_learning_state.pop(user_id, None)
        return

    header = f"Глава {chap_num}/{chap_total}, порция {idx+1}/{total}\n\n"
    raw = await teach_material(chunks[idx])
    formatted = latex_to_codeblock(raw)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="learn_back"),
            InlineKeyboardButton(text="👍 Понятно", callback_data="learn_ok")
        ],
        [
            InlineKeyboardButton(text="❓ Есть вопрос", callback_data="learn_ask"),
            InlineKeyboardButton(text="■ Стоп", callback_data="learn_stop"),
            InlineKeyboardButton(text="🏠 К главам", callback_data="learn_to_chapters")
        ]
    ])

    await bot.send_message(
        user_id,
        header + formatted,
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data == "learn_ok")
async def on_learning_ok(cb: CallbackQuery, bot: Bot):
    st = user_learning_state.get(cb.from_user.id)
    if not st:
        return
    st["index"] += 1
    await send_next_chunk(cb.from_user.id, bot)

@router.callback_query(lambda c: c.data == "learn_back")
async def on_learning_back(cb: CallbackQuery, bot: Bot):
    st = user_learning_state.get(cb.from_user.id)
    if not st:
        return
    if st["index"] == 0:
        await cb.answer("Вы на первой порции.", show_alert=True)
    else:
        st["index"] -= 1
        await send_next_chunk(cb.from_user.id, bot)

@router.callback_query(lambda c: c.data == "learn_ask")
async def on_learning_ask(cb: CallbackQuery, bot: Bot):
    st = user_learning_state.get(cb.from_user.id)
    if not st:
        return
    st["awaiting_question"] = True
    await bot.send_message(cb.from_user.id, "Задайте ваш вопрос по этому материалу:", reply_markup=ReplyKeyboardRemove())

@router.callback_query(lambda c: c.data == "learn_stop")
async def on_learning_stop(cb: CallbackQuery, bot: Bot):
    user_learning_state.pop(cb.from_user.id, None)
    await bot.send_message(
        cb.from_user.id,
        "Курс остановлен. Чтобы возобновить, нажми ▶️ Продолжить или выбери 🌱 Курс по органике.",
        reply_markup=main_kb
    )

@router.callback_query(lambda c: c.data == "learn_to_chapters")
async def to_chapters(cb: CallbackQuery, bot: Bot):
    user_learning_state.pop(cb.from_user.id, None)
    buttons = [
        [InlineKeyboardButton(text=topic, callback_data=f"learn_topic_{i}")]
        for i, topic in enumerate(LEARNING_TOPICS)
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await bot.send_message(cb.from_user.id, "Выберите главу для курса по органике:", reply_markup=kb)
    await bot.send_message(cb.from_user.id, "Можешь в любой момент вернуться в меню:", reply_markup=choose_chapter_kb)

# ========== Универсальный обработчик текста ==========

@router.message(lambda m: m.text and not m.text.startswith("/"))
async def on_text(m: types.Message, bot: Bot):
    st = user_learning_state.get(m.from_user.id)
    if st and st.get("awaiting_question"):
        await on_student_question(m, bot)
    else:
        await process_answer(m, m.text.strip())

@router.message(lambda m: m.voice is not None)
async def on_voice(m: types.Message, bot: Bot):
    file = await bot.get_file(m.voice.file_id)
    path = f"audio_{m.from_user.id}.ogg"
    await bot.download_file(file.file_path, path)
    try:
        txt = await transcribe_audio(path)
        st = user_learning_state.get(m.from_user.id)
        if st and st.get("awaiting_question"):
            answer = await answer_student_question(st["topic"], txt.strip())
            st["awaiting_question"] = False
            st["index"] += 1
            await m.answer(answer, reply_markup=main_kb)
            await send_next_chunk(m.from_user.id, bot)
        else:
            await process_answer(m, txt.strip())
    finally:
        os.remove(path)

async def process_answer(m: types.Message, transcript: str):
    uid = m.from_user.id
    topic = user_topics.pop(uid, None) or await classify_topic(transcript)
    ctx = "\n\n".join(TEXTBOOK_CONTENT.get(topic, [])[:3])
    feedback = await analyze_answer(transcript, topic, ctx)
    clean = clean_html(feedback)
    save_answer(uid, m.from_user.full_name, topic, transcript, clean)

    await m.answer(
        f"📘 Тема: <b>{topic}</b>\n"
        f"📝 Ответ: {transcript}\n\n"
        f"💬 Комментарий:\n{clean}",
        reply_markup=main_kb
    )

@router.message(lambda m: m.text and m.from_user.id in user_learning_state and user_learning_state[m.from_user.id].get("awaiting_question"))
async def on_student_question(m: types.Message, bot: Bot):
    st = user_learning_state[m.from_user.id]
    topic = st["topic"]
    answer = await answer_student_question(topic, m.text.strip())
    st["awaiting_question"] = False
    st["index"] += 1
    await m.answer(answer, reply_markup=main_kb)
    await send_next_chunk(m.from_user.id, bot)
