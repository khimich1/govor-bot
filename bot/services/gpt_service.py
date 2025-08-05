import os
import logging
import asyncio
from typing import List

import openai
import httpx
from pydub import AudioSegment
from dotenv import load_dotenv  # Для .env

# 1. Загружаем переменные из .env
load_dotenv()
# 2. Передаём ключ OpenAI библиотеке
openai.api_key = os.getenv("OPENAI_API_KEY")

# Настройка ffmpeg для pydub (если нужно)
FFMPEG_BIN = os.getenv("FFMPEG_BINARY", "")
if FFMPEG_BIN:
    AudioSegment.converter = FFMPEG_BIN

# Логгер и ключ API
logger = logging.getLogger(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")


async def classify_topic(transcript: str) -> str:
    """
    Определить тему ответа ученика на основе его текста.
    """
    prompt = (
        "Определи тему по органической химии из этого ответа:\n\n"
        f"{transcript}"
    )
    resp = await openai.ChatCompletion.acreate(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    topic = resp.choices[0].message.content.strip().capitalize()
    logger.info(f"📚 Тема определена: {topic}")
    return topic


async def analyze_answer(
    transcript: str,
    topic: str,
    textbook_context: str
) -> str:
    """
    Проанализировать ответ ученика, сверив его с текстом учебника:
    сильные стороны, ошибки, несоответствия.
    """
    prompt = (
        f"У тебя есть текст учебника по теме «{topic}»:\n\n"
        f"{textbook_context}\n\n"
        f"Ученик дал такой ответ:\n\"{transcript}\"\n\n"
        "Сверь этот ответ с учебником: отметь, где он точно повторил текст, "
        "где допустил неточности или упустил важное. Ответь тёплым комментарием от учителя."
    )
    resp = await openai.ChatCompletion.acreate(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    feedback = resp.choices[0].message.content.strip()
    logger.info("💬 Ответ ученику с учётом учебника сгенерирован")
    return feedback


async def _transcribe_chunk(file_bytes: bytes) -> str:
    """
    Транскрибирует один кусок аудио через Whisper API.
    """
    url = "https://api.openai.com/v1/audio/transcriptions"
    # Указываем таймауты connect/read/write/pool
    timeout = httpx.Timeout(connect=30.0, read=60.0, write=60.0, pool=60.0)
    files = {
        "file": ("chunk.ogg", file_bytes, "audio/ogg"),
        "model": (None, "whisper-1"),
        "response_format": (None, "text"),
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"},
            files=files
        )
        resp.raise_for_status()
        return resp.text.strip()


async def transcribe_audio(file_path: str) -> str:
    """
    Разбивает аудио на 60-секундные сегменты, транскрибирует каждый
    и возвращает объединённый текст.
    """
    logger.info(f"🔍 Начало транскрипции (с резкой на сегменты): {file_path}")

    audio = AudioSegment.from_file(file_path, format="ogg")
    duration_ms = len(audio)
    chunk_length_ms = 60 * 1000  # 60 секунд

    transcripts: List[str] = []
    for start in range(0, duration_ms, chunk_length_ms):
        end = min(start + chunk_length_ms, duration_ms)
        chunk = audio[start:end]
        buf = chunk.export(format="ogg")
        data = buf.read()
        buf.close()

        logger.info(f"  → Чанк {start//1000}-{end//1000}s, байт {len(data)}")
        try:
            txt = await _transcribe_chunk(data)
            transcripts.append(txt)
        except Exception as e:
            logger.warning(f"Ошибка при транскрипции чанка {start//1000}-{end//1000}: {e}")
            transcripts.append("")
        await asyncio.sleep(0.5)

    full = "\n".join(filter(None, transcripts))
    logger.info("✅ Полная транскрипция завершена")
    return full


async def teach_material(chunk: str) -> str:
    """
    Роль: преподаватель. Дать краткую лекцию по фрагменту и спросить, всё ли понятно.
    """
    system = (
        "Ты — опытный преподаватель органической химии. "
        "Дай краткую, ясную лекцию по этому фрагменту, а в конце спроси, всё ли понятно."
    )
    resp = await openai.ChatCompletion.acreate(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": chunk},
        ],
        temperature=0.7,
    )
    lecture = resp.choices[0].message.content.strip()
    logger.info("🎓 Лекция от преподавателя сгенерирована")
    return lecture


async def answer_student_question(topic: str, question: str) -> str:
    """
    Роль: преподаватель по теме. Дать понятный, краткий ответ на вопрос ученика.
    """
    system = f"Ты — преподаватель по теме «{topic}». Отвечай очень понятно и коротко."
    resp = await openai.ChatCompletion.acreate(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": question},
        ],
        temperature=0.7,
    )
    ans = resp.choices[0].message.content.strip()
    logger.info("❓ Вопрос ученика обработан и ответ сгенерирован")
    return ans
