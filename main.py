import asyncio
import logging
import sqlite3
from datetime import date

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp
import os

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

conn = sqlite3.connect('bot_data.db')
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id TEXT PRIMARY KEY,
    goal TEXT,
    goal_category TEXT DEFAULT 'общая'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_tasks (
    chat_id TEXT,
    date TEXT,
    task TEXT,
    PRIMARY KEY(chat_id, date)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS progress_logs (
    chat_id TEXT,
    date TEXT,
    progress TEXT
)
""")

conn.commit()

def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton("💎 VIP-доступ"))
    kb.add(KeyboardButton("🎯 Моя цель"))
    kb.add(KeyboardButton("📋 Помощь"))
    return kb.as_markup(resize_keyboard=True)

def goal_menu():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton("📝 Ввести/изменить цель"))
    kb.add(KeyboardButton("🔍 Анализ моей цели"))
    kb.add(KeyboardButton("📈 Мой прогресс"))
    kb.add(KeyboardButton("♻️ Сбросить цель"))
    kb.add(KeyboardButton("⬅️ Назад"))
    return kb.as_markup(resize_keyboard=True)

def vip_menu():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton("💎 Что входит"))
    kb.add(KeyboardButton("💰 Оплатить подписку"))
    kb.add(KeyboardButton("✅ Я оплатил"))
    kb.add(KeyboardButton("⬅️ Назад"))
    return kb.as_markup(resize_keyboard=True)

def help_menu():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton("📖 Условия подписки"))
    kb.add(KeyboardButton("📬 Поддержка"))
    kb.add(KeyboardButton("⬅️ Назад"))
    return kb.as_markup(resize_keyboard=True)

def detect_goal_category(goal_text: str) -> str:
    goal_text = goal_text.lower()
    finance_words = ['деньги', 'финанс', 'доход', 'заработок', 'эконом', 'инвест', 'бюджет']
    personal_words = ['эмоцион', 'развитие', 'саморазвитие', 'навык', 'личност', 'медитац', 'здоровье', 'спорт']

    for w in finance_words:
        if w in goal_text:
            return 'финансы'
    for w in personal_words:
        if w in goal_text:
            return 'личностный рост'
    return 'другое'

async def ask_ai(prompt: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    json_data = {
        "model": "anthropic/claude-3-haiku",
        "max_tokens": 500,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "Ты коуч, который помогает пользователю достигать целей."},
            {"role": "user", "content": prompt}
        ]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=json_data) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"OpenRouter error {resp.status}: {text}")
            data = await resp.json()
            return data['choices'][0]['message']['content']

PROMPTS = {
    "финансы": "Ты финансовый коуч. У пользователя цель: '{goal}'. Дай простой шаг на сегодня, чтобы улучшить его финансовое положение. Тон — мотивирующий, поддерживающий. Пожелай доброго утра.",
    "личностный рост": "Ты дружелюбный коуч по развитию личности. У пользователя цель: '{goal}'. Дай маленький, но мощный шаг на сегодня. Тон — мягкий и заботливый. Пожелай доброго утра.",
    "другое": "Ты коуч. У пользователя цель: '{goal}'. Предложи небольшой шаг на сегодня. Тон — дружелюбный и поддерживающий."
}

user_states = {}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я *Больше чем наставник* — ИИ-коуч, который поможет тебе достигать целей.\n"
        "Выбери, с чего хочешь начать 👇",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

@dp.message(lambda message: message.text == "⬅️ Назад")
async def back_to_main(message: types.Message):
    user_states.pop(str(message.chat.id), None)
    await message.answer("⬅️ Возврат в главное меню", reply_markup=main_menu())

@dp.message(lambda message: message.text == "🎯 Моя цель")
async def open_goal_menu(message: types.Message):
    await message.answer("🎯 Работаем над твоей целью", reply_markup=goal_menu())

@dp.message(lambda message: message.text == "📝 Ввести/изменить цель")
async def input_goal(message: types.Message):
    chat_id = str(message.chat.id)
    user_states[chat_id] = "await_goal"
    await message.answer("📝 Напиши свою новую цель")

@dp.message(lambda message: message.text == "♻️ Сбросить цель")
async def reset_goal(message: types.Message):
    chat_id = str(message.chat.id)
    cursor.execute("UPDATE users SET goal = NULL, goal_category = 'общая' WHERE chat_id = ?", (chat_id,))
    conn.commit()
    await message.answer("🎯 Цель сброшена.")

@dp.message(lambda message: message.text == "🔍 Анализ моей цели")
async def analyze_goal(message: types.Message):
    chat_id = str(message.chat.id)
    cursor.execute("SELECT goal FROM users WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        await message.answer("❌ У тебя ещё нет цели. Введи её.")
        return
    goal = row[0]
    await message.answer("🤖 Анализирую...")
    prompt = f"Анализ цели: {goal}\nДай рекомендации и мотивацию."
    try:
        answer = await ask_ai(prompt)
        await message.answer(answer)
    except Exception as e:
        logging.error(e)
        await message.answer("⚠️ Ошибка при анализе.")

@dp.message(lambda message: message.text == "📈 Мой прогресс")
async def show_progress(message: types.Message):
    chat_id = str(message.chat.id)
    cursor.execute("SELECT date, progress FROM progress_logs WHERE chat_id = ? ORDER BY date DESC LIMIT 5", (chat_id,))
    rows = cursor.fetchall()
    if not rows:
        await message.answer("Ты ещё не фиксировал свой прогресс. Начни сегодня!")
        return
    text = "📈 Последние записи прогресса:\n\n"
    for d, prog in rows:
        text += f"📅 {d} — {prog}\n"
    await message.answer(text)

@dp.message()
async def handle_all_messages(message: types.Message):
    chat_id = str(message.chat.id)
    state = user_states.get(chat_id)

    if state == "await_goal":
        goal_text = message.text.strip()
        category = detect_goal_category(goal_text)
        cursor.execute("""
            INSERT INTO users (chat_id, goal, goal_category) VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET goal=excluded.goal, goal_category=excluded.goal_category
        """, (chat_id, goal_text, category))
        conn.commit()
        user_states.pop(chat_id)
        await message.answer(f"🎯 Цель сохранена: *{goal_text}* (Категория: {category})", parse_mode="Markdown")
        return

    cursor.execute("SELECT date FROM daily_tasks WHERE chat_id = ? ORDER BY date DESC LIMIT 1", (chat_id,))
    last_task = cursor.fetchone()
    if last_task and user_states.get(chat_id) == "await_progress":
        progress_text = message.text.strip()
        progress_date = last_task[0]
        cursor.execute("INSERT INTO progress_logs (chat_id, date, progress) VALUES (?, ?, ?)", (chat_id, progress_date, progress_text))
        conn.commit()
        user_states.pop(chat_id)
        await message.answer("Спасибо, что поделился! Продолжаем движение вперёд. 💪")
        return

    await message.answer("Пожалуйста, выбери пункт из меню.", reply_markup=main_menu())

scheduler = AsyncIOScheduler()

async def send_morning_task():
    today = date.today().isoformat()
    cursor.execute("SELECT chat_id, goal, goal_category FROM users WHERE goal IS NOT NULL")
    users = cursor.fetchall()
    for chat_id, goal, category in users:
        prompt = PROMPTS.get(category, PROMPTS['другое']).format(goal=goal)
        try:
            task_text = await ask_ai(prompt)
        except Exception as e:
            logging.error(f"Error generating task for {chat_id}: {e}")
            task_text = "Сделай сегодня небольшой шаг к своей цели."
        cursor.execute("""
            INSERT OR REPLACE INTO daily_tasks (chat_id, date, task) VALUES (?, ?, ?)
        """, (chat_id, today, task_text))
        conn.commit()
        try:
            await bot.send_message(chat_id,
                f"☀️ Доброе утро, мой друг!\n\nСегодня твой шаг к цели:\n\n{task_text}")
        except Exception as e:
            logging.error(f"Error sending morning message to {chat_id}: {e}")

async def send_evening_check():
    today = date.today().isoformat()
    cursor.execute("SELECT chat_id FROM daily_tasks WHERE date = ?", (today,))
    users = cursor.fetchall()
    for (chat_id,) in users:
        try:
            await bot.send_message(chat_id,
                "🌙 Как прошёл твой день? Удалось выполнить шаг, который я предложил утром? Напиши коротко, как было.")
            user_states[chat_id] = "await_progress"
        except Exception as e:
            logging.error(f"Error sending evening message to {chat_id}: {e}")

# ⏰ Планировщик заданий
scheduler = AsyncIOScheduler()
scheduler.add_job(send_morning_task, 'cron', hour=8, minute=0)
scheduler.add_job(send_evening_check, 'cron', hour=20, minute=0)

# 🚀 Старт бота и планировщика
async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())