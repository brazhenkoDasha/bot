import os
import logging
from telegram import Update, Message
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")  
ADMIN_CHAT_ID = ""  
allowed_users = {} 
awaiting_question = set()
question_messages = {}

user_fio_map = {}  
message_to_user_map = {} 
user_file_uploaded = set()  
awaiting_large_file_link = set()

async def help_command(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    awaiting_question.add(user_id)
    await update.message.reply_text("Пожалуйста, напишите ваш вопрос в следующем сообщении")

async def handle_question(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    
    if user_id not in awaiting_question:
        return
    
    question_text = update.message.text
    user_name = update.message.from_user.username or "Неизвестный пользователь"
    
    try:
        #send questuin into group
        sent_message = await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"Вопрос от @{user_name}:\n\n{question_text}"
        )
        
        message_to_user_map[sent_message.message_id] = user_id
        question_messages[sent_message.message_id] = True  # Помечаем, что это вопрос
        
        await update.message.reply_text("Ваш вопрос отправлен организаторам. Ожидайте ответа.")
        awaiting_question.remove(user_id)
    except Exception as e:
        logger.error(f"Ошибка при отправке вопроса: {e}")
        await update.message.reply_text("Произошла ошибка при отправке вопроса. Попробуйте позже.")
        awaiting_question.remove(user_id)

async def reply_to_user(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in allowed_users:
        await update.message.reply_text("Вы не являетесь организатором и не можете отправлять ответы")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Надо сначала ответить на сообщение в группе, чтобы отправить обратную связь пользователю")
        return

    original_message_id = update.message.reply_to_message.message_id
    target_user_id = message_to_user_map.get(original_message_id)

    if not target_user_id:
        await update.message.reply_text("Не удалось найти пользователя, которому ответить")
        return

    reply_text = update.message.text.replace("/reply", "").strip()
    if not reply_text:
        await update.message.reply_text("Надо указать текст ответа после команды /reply")
        return

    try:
        # Determine type 
        if original_message_id in question_messages:
            message_text = "Ответ на ваш вопрос: "
        else:
            message_text = "Ответ организаторов: "
            
        await context.bot.send_message(chat_id=target_user_id, text=f"{message_text}{reply_text}")
        await update.message.reply_text("Ответ успешно отправлен")
    except Exception as e:
        logger.error(f"Ошибка при отправке ответа: {e}")
        await update.message.reply_text("Произошла ошибка при отправке ответа. Попробуйте снова позже.")

async def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    message_text = update.message.text
    user_name = update.message.from_user.username or "Неизвестный пользователь"

    if user_id in user_file_uploaded:
        await update.message.reply_text("Если вы хотите задать вопрос организаторам – воспользуйтесь /help, если хотите ещё раз отправить работу – прикрепите файл. В другом случае мы не получим ваш вопрос/ответ.")
        return

    #for big file
    if user_id in awaiting_large_file_link and (message_text.startswith("http://") or message_text.startswith("https://")):
        fio = user_fio_map[user_id]
        try:
            sent_message = await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"Ссылка на файл от {fio} (@{user_name})"
            )
            message_to_user_map[sent_message.message_id] = user_id
            user_file_uploaded.add(user_id)
            awaiting_large_file_link.remove(user_id)
            await update.message.reply_text("Спасибо, ваша ссылка отправлена организаторам.")
            return
        except Exception as e:
            logger.error(f"Ошибка при пересылке ссылки: {e}")
            await update.message.reply_text("Произошла ошибка при отправке ссылки. Попробуйте снова позже")
            return

    # surname, name
    if user_id not in user_fio_map:
        user_fio_map[user_id] = message_text
        try:
            await update.message.reply_text("Спасибо! Ваше ФИО сохранено. Теперь отправьте файл с работой или ссылку на файл")
        except Exception as e:
            logger.error(f"Ошибка при отправке ФИО администраторам: {e}")
            await update.message.reply_text("Произошла ошибка при сохранении ФИО. Попробуйте снова позже")
    else:
        if not (message_text.startswith("http://") or message_text.startswith("https://")):
            await update.message.reply_text("Вы уже ввели свое ФИО. Пожалуйста, отправьте файл с работой или ссылку на файл")


async def handle_file_or_link(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.username or "Неизвестный пользователь"

    if user_id not in user_fio_map:
        await update.message.reply_text("Пожалуйста, сначала введите ваше ФИО текстовым сообщением")
        return

    if update.message.document:
        file = update.message.document
        file_id = file.file_id
        file_name = file.file_name
        file_size = file.file_size

        if file_size > 20 * 1024 * 1024:
            awaiting_large_file_link.add(user_id)
            await update.message.reply_text(
                "К сожалению, мы не можем получать файлы размером более 20 Мб. Можно отправить нам версию без картинок (чтобы размер был меньше 20 Мб) или ссылкой на файл в Google/Яндекс Диске"
            )
            return

        try:
            downloaded_file = await context.bot.get_file(file_id)
            if downloaded_file is None:
                await update.message.reply_text("Произошла ошибка при скачивании файла")
                return
            
            if not os.path.exists("downloads"):
                os.makedirs("downloads")
            
            file_path = os.path.join("downloads", file_name)
            await downloaded_file.download_to_drive(file_path)

            fio = user_fio_map[user_id]
            sent_document = await context.bot.send_document(
                chat_id=ADMIN_CHAT_ID,
                document=open(file_path, "rb"),
                caption=f"Файл от {fio} (@{user_name}) (ID {user_id})"
            )
            message_to_user_map[sent_document.message_id] = user_id
            user_file_uploaded.add(user_id)

            await update.message.reply_text("Спасибо, организаторы в течение 1-2 дней постараются проверить на плагиат (в antiplagiat.ru) и пришлют результаты.")
        except Exception as e:
            logger.error(f"Ошибка при обработке файла: {e}")
            await update.message.reply_text(f"Произошла ошибка при обработке файла: {e}. Попробуйте снова позже")

async def reply_to_user(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in allowed_users:
        await update.message.reply_text("Вы не являетесь организатором и не можете отправлять ответы")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Надо сначала ответить на сообщение в группе, чтобы отправить обратную связь пользователю")
        return

    original_message_id = update.message.reply_to_message.message_id
    target_user_id = message_to_user_map.get(original_message_id)

    if not target_user_id:
        await update.message.reply_text("Не удалось найти пользователя, которому ответить")
        return

    reply_text = update.message.text.replace("/reply", "").strip()
    if not reply_text:
        await update.message.reply_text("Надо указать текст ответа после команды /reply")
        return

    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"Ответ организаторов: {reply_text}")
        await update.message.reply_text("Ответ успешно отправлен")
    except Exception as e:
        logger.error(f"Ошибка при отправке ответа: {e}")
        await update.message.reply_text("Произошла ошибка при отправке ответа. Попробуйте снова позже")

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет, мы организаторы КНР. Напишите сначала ФИО, а затем отправьте файл (в формате Word или PDF) или ссылку на файл, который нужно проверить"
    )

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reply", reply_to_user))
    
    async def message_router(update: Update, context: CallbackContext):
        user_id = update.message.from_user.id
        
        if user_id in awaiting_question:
            await handle_question(update, context)
        else:
            await handle_message(update, context)
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file_or_link))

    application.run_polling(drop_pending_updates=True)

                            
if __name__ == "__main__":
    main()
