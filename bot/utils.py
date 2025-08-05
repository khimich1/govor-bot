# bot/utils.py

import os
import json
import re
from typing import Any

# ====== Тестовые темы (режим "Темы") ======
ALL_TOPICS = [
    "Алканы", "Алкены", "Алкины", "Арены", "Спирты", "Фенол",
    "Альдегиды и кетоны", "Карбоновые кислоты и эфиры", "Амины",
    "Аминокислоты и белки", "Углеводы", "Применение орг веществ"
]

# ====== Режим "Изучение": загружаем порции из JSON ======
BASE_DIR = os.path.dirname(__file__)
TB_DIR = os.path.join(BASE_DIR, "textbooks")

LEARNING_TOPICS = [
    os.path.splitext(fname)[0]
    for fname in sorted(os.listdir(TB_DIR))
    if fname.lower().endswith(".json")
]

TEXTBOOK_CONTENT: dict[str, list[str]] = {}
for topic in LEARNING_TOPICS:
    path = os.path.join(TB_DIR, f"{topic}.json")
    with open(path, encoding="utf-8") as f:
        TEXTBOOK_CONTENT[topic] = json.load(f)

# ====== Состояния пользователей ======
user_learning_state: dict[int, dict[str, Any]] = {}
user_topics: dict[int, str] = {}


def clean_html(text: str) -> str:
    """
    Простая очистка HTML-тегов из ответов GPT.
    """
    text = text.replace("<p>", "").replace("</p>", "")
    text = text.replace("<br>", "\n")
    text = text.replace("<ul>", "").replace("</ul>", "")
    text = text.replace("<ol>", "").replace("</ol>", "")
    text = text.replace("<li>", "• ").replace("</li>", "\n")
    return re.sub(r"<.*?>", "", text)

# ====== Конвертация LaTeX- и инлайн-формул в Markdown code-block ======

# подстрочные цифры (₀₁₂…₉)
_SUBSCRIPT = {str(i): chr(0x2080 + i) for i in range(10)}
# надстрочные цифры и знаки (¹²³…⁹, ⁺, ⁻)
_SUPERSCRIPT = {
    '0':'⁰','1':'¹','2':'²','3':'³','4':'⁴',
    '5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹',
    '+':'⁺','-':'⁻'
}

# Используем raw строку для docstring, чтобы backslashes не интерпретировались
# pylint: disable=use-xrange
r"""
latex_to_codeblock(text: str) -> str

Заменяет LaTeX-блоки (\[...\]) и инлайн-формулы ($...$)
на Markdown code-block'и с Unicode-формулами.

Особенности замены:
  - убирает \text{...}
  - _{n} или _n → подстрочные цифры (₀₁₂...)
  - ^{n} или ^n → надстрочные цифры (¹²³...)
  - любые \rightarrow, \to, \longrightarrow, \xrightarrow → стрелка →
  - \equiv → знак эквивалентности ≡
  - удаляет фигурные скобки и лишние слеши
"""
def latex_to_codeblock(text: str) -> str:
    def _convert(match: re.Match) -> str:
        frm = match.group(1)
        # убрать \text{...}
        frm = re.sub(r'\\text\{([^}]*)\}', r'\1', frm)
        # подстрочные индексы _{digits}
        frm = re.sub(
            r'_(?:\{)?(\d+)(?:\})?',
            lambda m: ''.join(_SUBSCRIPT.get(ch, ch) for ch in m.group(1)),
            frm
        )
        # надстрочные ^{digits} или ^digit
        frm = re.sub(
            r'\^(?:\{)?([^}]+)(?:\})?',
            lambda m: ''.join(_SUPERSCRIPT.get(ch, ch) for ch in m.group(1)),
            frm
        )
        # стрелки и эквивалентность
        frm = re.sub(r'\\(?:rightarrow|to|longrightarrow|xrightarrow)', '→', frm)
        frm = re.sub(r'\\equiv', '≡', frm)
        # удалить фигурные скобки и обратные слеши
        frm = frm.replace('{', '').replace('}', '')
        frm = frm.replace('\\,', '')
        frm = frm.strip()
        # обернуть в Markdown code-block
        return f"```\n{frm}\n```"

    # заменить блочные формулы \[ ... \]
    text = re.sub(r'\\\[([\s\S]*?)\\\]', _convert, text, flags=re.DOTALL)
    # заменить инлайн-формулы $ ... $
    text = re.sub(r'\$([^$]+)\$', _convert, text)
    return text
