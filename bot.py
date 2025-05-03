from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from logic import *
import schedule
import threading
import time
from config import *
import tempfile
import cv2
from telebot.types import InputFile

bot = TeleBot(API_TOKEN)

def gen_markup(id):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(InlineKeyboardButton("Получить!", callback_data=id))
    return markup

@bot.callback_query_handler(func=lambda call: True)
def handle_prize_claim(call):
    prize_id = int(call.data)
    user_id = call.message.chat.id

    conn = sqlite3.connect(DATABASE)
    with conn:
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM winners WHERE prize_id = ?', (prize_id,))
        current_winners = cur.fetchone()[0]

        cur.execute('SELECT * FROM winners WHERE user_id = ? AND prize_id = ?', (user_id, prize_id))
        already_winner = cur.fetchone()

        if current_winners >= 3:
            bot.answer_callback_query(call.id, "Увы, ты не успел. Приз уже получен 3 участниками.", show_alert=True)
        elif already_winner:
            bot.answer_callback_query(call.id, "Ты уже получил этот приз.", show_alert=True)
        else:
            manager.add_winner(user_id, prize_id)
            img = manager.get_prize_img(prize_id)
            with open(f'img/{img}', 'rb') as photo:
                bot.send_photo(user_id, photo, caption="Поздравляем! Ты получил приз 🎉")

def send_message():
    prize_id, img = manager.get_random_prize()[:2]
    manager.mark_prize_used(prize_id)
    hide_img(img)
    for user in manager.get_users():
        with open(f'hidden_img/{img}', 'rb') as photo:
            bot.send_photo(user, photo, reply_markup=gen_markup(id = prize_id))

def shedule_thread():
    schedule.every().minute.do(send_message) # Здесь ты можешь задать периодичность отправки картинок
    while True:
        schedule.run_pending()
        time.sleep(1)

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.chat.id
    if user_id in manager.get_users():
        bot.reply_to(message, "Ты уже зарегестрирован!")
    else:
        manager.add_user(user_id, message.from_user.username)
        bot.reply_to(message, """Привет! Добро пожаловать! 
Тебя успешно зарегистрировали!
Каждый час тебе будут приходить новые картинки и у тебя будет шанс их получить!
Для этого нужно быстрее всех нажать на кнопку 'Получить!'

Только три первых пользователя получат картинку!)""")
        

@bot.message_handler(commands=['ratings'])
def handle_rating(message):
    ratings = manager.get_ratings()
    if not ratings:
        bot.reply_to(message, "Рейтинг пока пуст")
        return

    text = "Топ-10 победителей:\n\n"
    for i, (username, count) in enumerate(ratings, start=1):
        name_display = f"@{username}" if username else "(Без имени)"
        text += f"{i}. {name_display}: {count} приз(ов)\n"

    bot.reply_to(message, text)

@bot.message_handler(commands=['get_my_score'])
def handle_my_score(message):
    user_id = message.chat.id
    winners_data = manager.get_winners_img(user_id)
    user_prizes = [x[0] for x in winners_data]

    collage = create_collage(user_prizes)

    if collage is None:
        bot.reply_to(message, "У вас пока нет призов")
        return

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        cv2.imwrite(tmp.name, collage)
        with open(tmp.name, 'rb') as photo:
            bot.send_photo(user_id, photo, caption="Вот твои достижения!")

@bot.message_handler(commands=['resend'])
def handle_resend(message):
    user_id = message.chat.id
    conn = sqlite3.connect(DATABASE)
    with conn:
        cur = conn.cursor()
        cur.execute('''SELECT prize_id FROM winners WHERE user_id = ? AND received = 0''', (user_id,))
        missed_prizes = cur.fetchall()

        if missed_prizes:
            for prize in missed_prizes:
                prize_id = prize[0]
                img = manager.get_prize_img(prize_id)
                with open(f'img/{img}', 'rb') as photo:
                    bot.send_photo(user_id, photo, caption="Ты пропустил картинку. Вот она снова!")
                cur.execute('''UPDATE winners SET received = 1 WHERE user_id = ? AND prize_id = ?''', (user_id, prize_id))
                conn.commit()
        else:
            bot.reply_to(message, "Ты не пропустил никаких картинок!")


def polling_thread():
    bot.polling(none_stop=True)

if __name__ == '__main__':
    manager = DatabaseManager(DATABASE)
    manager.create_tables()

    polling_thread = threading.Thread(target=polling_thread)
    polling_shedule  = threading.Thread(target=shedule_thread)

    polling_thread.start()
    polling_shedule.start()
