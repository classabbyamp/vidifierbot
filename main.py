"""
stickdownbot

Copyright (c) 2021 classabbyamp
Released under the BSD-3-Clause license
"""


from datetime import datetime, timedelta
import logging
from pathlib import Path
from typing import Optional
import traceback
import json
import html
import re

import youtube_dl  # type: ignore
import telegram as tg
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

from data import keys


# Enable logging
logging.basicConfig(format='[%(asctime)s] [%(levelname)s] %(name)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


YDL_OPTS = {
    "outtmpl": f"{keys.tempdir}/%(id)s.%(ext)s",
    "logger": logger,
    "max_filesize": 49_500_000,
    "format": "best[ext=mp4]",
    "noplaylist": True,
    "postprocessors": [],
}


YDL_OPTS_GIF = {
    "outtmpl": f"{keys.tempdir}/%(id)s_gif.%(ext)s",
    "logger": logger,
    "max_filesize": 49_500_000,
    "format": "best[ext=mp4]",
    "noplaylist": True,
    "postprocessors": [
        {
            "key": "ExecAfterDownload",
            "exec_cmd": "ffmpeg -y -v 16 -i {} -c copy -an {}.mp4 && mv {}.mp4 {}",
        },
    ],
}


class InternalError(Exception):
    def __init__(self, msg: str):
        self.msg = msg


def help_command(update: tg.Update, _: CallbackContext):
    if update.message:
        update.message.reply_text(("Send me URLs, and I'll try to convert them to videos!\n"
                                   "You can also use the commands /vidify and /gifify when sending URLs "
                                   "or replying to a message with URLs.\n\n"
                                   "To trim the video or gif, set the start time and either the end time or duration. "
                                   "`s=timestamp` or `start=timestamp` will set the start time, `e=timestamp` or "
                                   "`end=timestamp` will set the end time, and `d=timestamp`, `dur=timestamp`, or "
                                   "`duration=timestamp` will set the duration. The timestamp can be a number of "
                                   "seconds, `MM:SS`, or `HH:MM:SS` (leading zeros are not required). "
                                   "Timestamps can also be a number of seconds, milliseconds, or microseconds with "
                                   "`s`, `ms`, or `us` after. Any seconds, milliseconds, or microseconds value also "
                                   "accepts decimal places, e.g. `12.432s` or `12:03:37.123`.\n\n"
                                   "These sites are supported: "
                                   "http://ytdl-org.github.io/youtube-dl/supportedsites.html"),
                                  disable_web_page_preview=True, parse_mode=tg.ParseMode.MARKDOWN)


def vidify_command(update: tg.Update, _: CallbackContext):
    run_cmd(update, gif=False)


def gifify_command(update: tg.Update, _: CallbackContext):
    run_cmd(update, gif=True)


def run_cmd(update: tg.Update, gif: bool):
    urls = []
    if update.message:
        if update.message.text:
            urls += list(update.message.parse_entities(types=["url"]).values())

        if update.message.reply_to_message:
            urls += list(update.message.reply_to_message.parse_entities(types=["url"]).values())

        if urls:
            get_and_send_videos(update.message, urls, gif)
        else:
            update.message.reply_text(("Unable to find any URLs to convert in your message or the replied-to message. "
                                       "If this is a private group, I probably can't see the replied-to message."))


def get_and_send_videos(msg: tg.Message, urls: list[str], gif: bool = False):
    logger.info(f"[{msg.message_id}] {', '.join(urls)}")
    opts: dict = YDL_OPTS if not gif else YDL_OPTS_GIF
    try:
        if trim := parse_timestamp(msg):
            opts["postprocessors"].append(trim)
    except InternalError as e:
        logger.error(f"[{msg.message_id}] {e.msg}")
        msg.reply_text(f"{e.msg}\nid: {msg.message_id}", quote=True, disable_web_page_preview=True)
        return
    with youtube_dl.YoutubeDL(opts) as ydl:
        for url in urls:
            ydl.cache.remove()
            try:
                info = ydl.extract_info(url, download=True)
                v_id = info["id"]
                fn = ydl.prepare_filename(info)
                if trim:
                    fn += ".trim.mp4"
            except youtube_dl.utils.DownloadError as e:
                logger.error(f"[{msg.message_id}] {e}")
                msg.reply_text(f"Unable to find video at {url}\nid: {msg.message_id}",
                               quote=True, disable_web_page_preview=True)
            else:
                send_videos(msg, url, fn, v_id, gif)
                f = Path(fn)
                if f.is_file():
                    f.unlink()


def send_videos(msg: tg.Message, url: str, fn: str, v_id: str, gif: bool = False):
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
                except tg.error.TelegramError as e:
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


def parse_timestamp(msg: tg.Message) -> Optional[dict[str, str]]:
    start = None
    end = None
    dur = None

    if msg.text:
        text = msg.text.lower()
        start = get_timestamp(["s", "start"], text)
        end = get_timestamp(["e", "end"], text)
        dur = get_timestamp(["d", "dur", "duration"], text)

        if end is not None or dur is not None:
            if start is None:
                start = "0"
            flag = "-to" if end is not None else "-t"
            endur = end if end is not None else dur
            cmd = " ".join(["ffmpeg -y -v 16 -ss", start, flag, endur, "-i {} -c copy -acodec copy {}.trim.mp4"])
            return {
                "key": "ExecAfterDownload",
                "exec_cmd": cmd,
            }
        elif start is not None:
            raise InternalError("Must provide end= or dur= with start=")
    return None


def get_timestamp(pfxs: list[str], text: str) -> Optional[str]:
    TS = (r"(?:(?P<sfrac>[0-9]+(?:\.[0-9]+)?(?:s|ms|us))|"
          r"(?:(?:(?P<h>[0-9]+):)?(?P<m>[0-9]{1,2}):)?(?P<s>[0-9]{1,2}(?:\.[0-9]+)?))")
    ts_val = None

    if matches := re.search(fr"(?:{'|'.join(pfxs)})=" + TS, text):
        g = matches.groupdict()
        if "sfrac" in g and g["sfrac"] is not None:
            ts_val = g["sfrac"]
        elif "s" in g and g["s"] is not None:
            h = g["h"] if g["h"] is not None else "0"
            m = g["m"] if g["m"] is not None else "0"
            s = g["s"] if g["s"] is not None else "0"
            ts_val = f"{int(h):0>2}:{int(m):0>2}:{float(s):02.3f}"
    return ts_val


def cleanup_files(_: CallbackContext):
    # delete mp4 files in keys.tempdir older than 5 min
    deleted = 0
    del_age = timedelta(minutes=1)
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

    update_str = update.to_dict() if isinstance(update, tg.Update) else str(update)
    message = (
        f'An exception was raised while handling an update\n'
        f'<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}'
        '</pre>\n\n'
        f'<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n'
        f'<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n'
        f'<pre>{html.escape(tb_string)}</pre>'
    )

    context.bot.send_message(chat_id=keys.owner_id, text=message, parse_mode=tg.ParseMode.HTML)


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
    jq.run_repeating(cleanup_files, interval=timedelta(minutes=5), first=10)

    updater.start_polling()
    updater.idle()
