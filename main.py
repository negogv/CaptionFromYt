from pytube import YouTube

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

from math import ceil

from telebot import TeleBot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, ReplyKeyboardMarkup, \
    InputFile
from telebot.callback_data import CallbackData, CallbackDataFilter
from telebot.custom_filters import AdvancedCustomFilter

bot = TeleBot('TOKEN')

reply_keyboard = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
reply_keyboard.add('Download video', 'Get captions from video')


class MainFilter(AdvancedCustomFilter):
    key = 'text'

    @staticmethod
    def check(message, text):
        return message.text in text


lang_factory = CallbackData('lang_code', prefix='languages')

languages = {'ru': 'Russian', 'uk': 'Ukrainian', 'en': 'English', 'en-GB': 'British English',
             'en-US': 'American English'}
all_lang_codes = set(languages)


def lang_keyboard(link, available):
    keyboard = [[InlineKeyboardButton(text=languages[lang],
                                      callback_data=lang_factory.new(lang_code=str(lang)))]
                for lang in all_lang_codes.intersection(available)]
    keyboard.append([InlineKeyboardButton(text='Your video', url=link)])
    return InlineKeyboardMarkup(keyboard)


def grade_experience():
    keyboard = [[InlineKeyboardButton(text=str(i), callback_data=str(i))] for i in range(1, 6)]
    return InlineKeyboardMarkup(keyboard)


class LanguagesCallbackFilter(AdvancedCustomFilter):
    key = 'config'

    def check(self, call: CallbackQuery, config: CallbackDataFilter):
        return config.check(query=call)


class VideoConfig:
    def __init__(self, link: str, action: str):
        self.link = link
        self.action = action
        self.caption_language = None
        self.caption_type = 'Message'
        self.grade = 0


users_history = {}


@bot.message_handler(commands=['start'])
def send_welcome(message: Message):
    bot.send_message(message.chat.id, "Hello! This is bot that can help you download youtube video or "
                                      "get a captions from it", reply_markup=reply_keyboard)


@bot.message_handler(text=['Download video'])
def download_start(message: Message):
    bot.send_message(message.chat.id, "We apologise, but this feature is not currently available")


@bot.message_handler(text=['Get captions from video'])
def caption_start(message: Message):
    msg = bot.send_message(message.chat.id, "Please send link to youtube video")
    bot.register_next_step_handler(msg, caption_lang)


def caption_lang(message: Message):
    try:
        link = message.text
        video = VideoConfig(link, 'Get captions')
        users_history[message.chat.id] = [video]
        video = YouTube(link)
        video_id = video.video_id
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        available = set(list(transcript_list.__getattribute__('_generated_transcripts')) +
                        list(transcript_list.__getattribute__('_manually_created_transcripts')))
        bot.send_message(message.chat.id, 'In which language you want receive captions?',
                         reply_markup=lang_keyboard(link, available))
    except Exception as e:
        bot.reply_to(message, 'error with language choose function')


@bot.callback_query_handler(func=None, config=lang_factory.filter())
def caption_type(call: CallbackQuery):
    try:
        # call.data is prefix of lang_factory:<lang_code> next line is getting only lang. code from call.data
        users_history[call.message.chat.id][-1].caption_language = call.data.replace('languages:', '')
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('Regular message', callback_data='message')],
                                         [InlineKeyboardButton('File .txt', callback_data='txt')]])
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text='In which format you want to get captions?', reply_markup=keyboard)
    except Exception as e:
        bot.reply_to(call.message, 'error with language choose function')


def get_txt_capt(id):
    lang = users_history[id][-1].caption_language
    video = YouTube(users_history[id][-1].link)
    video_id = video.video_id
    language_code = YouTubeTranscriptApi.list_transcripts(video_id).find_transcript([lang]).language_code
    data = YouTubeTranscriptApi.get_transcript(video_id,
                                               languages=[language_code])  # creating transcription of the video
    formatter = TextFormatter()  # adding formatter to txt
    text_formatted = formatter.format_transcript(data)  # formatting transcripted video (data)
    return text_formatted


@bot.callback_query_handler(func=lambda c: c.data == 'message')
def caption_send_message(call: CallbackQuery):
    try:
        users_history[call.message.chat.id][-1].caption_type = call.data
        text_formatted = get_txt_capt(call.message.chat.id)
        msg_amount = ceil(len(text_formatted) / 4096)  # message in telegram may contain max 4096
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text='There is your captions!')
        for i in range(msg_amount):  # sending captions
            message_text = text_formatted[4096 * i:4096 * (i + 1)]
            bot.send_message(call.message.chat.id, message_text)
        bot.send_message(call.message.chat.id, 'Grade your experience', reply_markup=grade_experience())
    except Exception as e:
        bot.reply_to(call.message, 'error with sending message function')


@bot.callback_query_handler(func=lambda c: c.data == 'txt')
def caption_send_txt(call: CallbackQuery):
    try:
        users_history[call.message.chat.id][-1].caption_type = call.data
        text_formatted = get_txt_capt(call.message.chat.id)
        with open('../yt to text/captions.txt', 'w', encoding='utf-8') as file_txt:  # creating txt file with subtitles
            file_txt.write(text_formatted)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text='There is your captions!')
        bot.send_document(call.message.chat.id, InputFile('../yt to text/captions.txt'))
        bot.send_message(call.message.chat.id, 'Grade your experience', reply_markup=grade_experience())
    except Exception as e:
        bot.reply_to(call.message, 'error with sending txt file function')


@bot.callback_query_handler(func=lambda c: c.data in ['1', '2', '3', '4', '5'])
def grade_exp(call: CallbackQuery):
    video = users_history[call.message.chat.id][-1]
    action = video.action
    video.grade = int(call.data)
    if action == 'Get captions':
        caption_type = video.caption_type
        lang_code = video.caption_language
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text=f'Thank you for using the bot! There is parameters of your last interaction:\n'
                                   f'Action: {action}\n'
                                   f'Language of captions: {languages[lang_code]}\n'
                                   f'Type of captions: {caption_type}\n\n'
                                   f'Use /start to restart the survey')


if __name__ == '__main__':
    print('Bot started...')
    bot.add_custom_filter(MainFilter())
    bot.add_custom_filter(LanguagesCallbackFilter())
    bot.infinity_polling()
