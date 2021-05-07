"""
stickdownbot

Copyright (c) 2021 classabbyamp
Released under the BSD-3-Clause license
"""


from datetime import datetime, timedelta
import logging
from pathlib import Path
import traceback
import json
import html

import youtube_dl  # type: ignore
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

from data import keys


# Enable logging
logging.basicConfig(format='[%(asctime)s] [%(levelname)s] %(name)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


ydl_opts = {
    "outtmpl": f"{keys.tempdir}/%(id)s.%(ext)s",
    "logger": logger,
    "max_filesize": 49_500_000,
    "format": "best[ext=mp4]",
}


ydl_opts_gif = {
    "outtmpl": f"{keys.tempdir}/%(id)s_gif.%(ext)s",
    "logger": logger,
    "max_filesize": 49_500_000,
    "format": "best[ext=mp4]",
    "postprocessors": [
        {
            "key": "ExecAfterDownload",
            "exec_cmd": "ffmpeg -i {} -c copy -an {}.mp4 && mv {}.mp4 {}",
        },
    ],
}


def help_command(update: telegram.Update, _: CallbackContext):
    if update.message:
        update.message.reply_text(("Send me URLs, and I'll try to convert them to videos!\n"
                                   "You can also use the commands /vidify and /gifify when sending URLs "
                                   "or replying to a message with URLs.\n\n"
                                   "These sites are supported: "
                                   "http://ytdl-org.github.io/youtube-dl/supportedsites.html"),
                                  disable_web_page_preview=True)


def vidify_command(update: telegram.Update, _: CallbackContext):
    if update.message:
        urls = list(update.message.parse_entities(types=["url"]).values())
        if urls:
            get_and_send_videos(update.message, urls, False)
        elif update.message.reply_to_message:
            urls = list(update.message.reply_to_message.parse_entities(types=["url"]).values())
            if urls:
                get_and_send_videos(update.message, urls, False)
        else:
            update.message.reply_text(("Unable to find any URLs to convert in your message or the replied-to message."
                                       "If this is a private group, I probably can't see the replied-to message."))

def gifify_command(update: telegram.Update, _: CallbackContext):
    if update.message:
        urls = list(update.message.parse_entities(types=["url"]).values())
        if urls:
            get_and_send_videos(update.message, urls, True)
        elif update.message.reply_to_message:
            urls = list(update.message.reply_to_message.parse_entities(types=["url"]).values())
            if urls:
                get_and_send_videos(update.message, urls, True)
        else:
            update.message.reply_text(("Unable to find any URLs to convert in your message or the replied-to message."
                                       "If this is a private group, I probably can't see the replied-to message."))


def get_and_send_videos(msg: telegram.Message, urls: list[str], gif: bool = False):
    logger.info(str(urls))
    opts = ydl_opts if not gif else ydl_opts_gif
    with youtube_dl.YoutubeDL(opts) as ydl:
        for url in urls:
            ydl.cache.remove()
            try:
                info = ydl.extract_info(url, download=True)
                v_id = info["id"]
                fn = ydl.prepare_filename(info)
            except youtube_dl.utils.DownloadError as e:
                logger.error(f"{e}")
                msg.reply_text(f"Unable to find video at {url}",
                               quote=True, disable_web_page_preview=True)
            else:
                send_videos(msg, url, fn, v_id, gif)


def send_videos(msg: telegram.Message, url: str, fn: str, v_id: str, gif: bool = False):
    if fn:
        fp = Path(fn)
        # check vid is <50MB
        if fp.is_file() and fp.stat().st_size < 49_500_000:
            with fp.open("rb") as video:
                try:
                    if gif:
                        msg.reply_animation(animation=video, caption=url, quote=True)
                    else:
                        msg.reply_video(video=video, caption=url, quote=True)
                except telegram.error.TelegramError as e:
                    logger.error(f"[{v_id}] {e}")
                    msg.reply_text(f"Unable to upload video from {url}\nid: {v_id}",
                                   quote=True, disable_web_page_preview=True)
        else:
            logger.error(f"[{v_id}] file does not exist or too large for upload")
            msg.reply_text(f"Unable to find video at {url}, or video is too large to upload\nid: {v_id}",
                           quote=True, disable_web_page_preview=True)
    else:
        logger.error(f"[{v_id}] file does not exist")
        msg.reply_text(f"Unable to find video at {url}\nid: {v_id}",
                       quote=True, disable_web_page_preview=True)


def cleanup_files(_: CallbackContext):
    # delete mp4 files in keys.tempdir older than 15 min
    deleted = 0
    del_age = timedelta(minutes=15)
    tmp = Path(keys.tempdir)
    files = tmp.glob("*.mp4")
    for f in files:
        age = abs(datetime.utcnow() - datetime.utcfromtimestamp(f.stat().st_ctime))
        if f.is_file() and age > del_age:
            f.unlink()
            deleted += 1
    if deleted:
        logger.info(f"Deleted {deleted} cached mp4 files from {keys.tempdir}")


def error_handler(update: object, context: CallbackContext):
    logger.error("Exception while handling an update:", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)  # type: ignore
    tb_string = ''.join(tb_list)

    update_str = update.to_dict() if isinstance(update, telegram.Update) else str(update)
    message = (
        f'An exception was raised while handling an update\n'
        f'<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}'
        '</pre>\n\n'
        f'<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n'
        f'<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n'
        f'<pre>{html.escape(tb_string)}</pre>'
    )

    context.bot.send_message(chat_id=keys.owner_id, text=message, parse_mode=telegram.ParseMode.HTML)


if __name__ == "__main__":
    updater = Updater(keys.tg_token, use_context=True)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", help_command, run_async=True))
    dp.add_handler(CommandHandler("help", help_command, run_async=True))
    dp.add_handler(CommandHandler("vidify", vidify_command, run_async=True))
    dp.add_handler(CommandHandler("gifify", gifify_command, run_async=True))
    dp.add_handler(MessageHandler(Filters.chat_type.private & Filters.entity("url"), vidify_command, run_async=True))
    dp.add_error_handler(error_handler)

    jq = updater.job_queue
    jq.run_repeating(cleanup_files, interval=timedelta(minutes=10), first=10)

    updater.start_polling()
    updater.idle()
