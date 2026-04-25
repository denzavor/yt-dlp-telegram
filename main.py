import datetime
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import telebot
import yt_dlp
from telebot import types
from telebot.util import quick_markup
from yt_dlp.utils import DownloadError, ExtractorError

import config

os.makedirs(config.output_folder, exist_ok=True)

bot = telebot.TeleBot(config.token)
last_edited = {}
allowed_usernames = {
    username.lstrip("@").lower()
    for username in getattr(config, "allowed_usernames", [])
}
shared_cookie_admin_usernames = {
    username.lstrip("@").lower()
    for username in getattr(config, "shared_cookie_admin_usernames", ["denzavr"])
}
shared_cookie_file = getattr(config, "shared_cookie_file", None)
gallery_dl_binary = getattr(config, "gallery_dl_binary", "gallery-dl")
gallery_dl_timeout = getattr(config, "gallery_dl_timeout", 25)
image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
instagram_browser_user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def normalize_username(username: Optional[str]) -> Optional[str]:
    if not username:
        return None
    return username.lstrip("@").lower()


def is_user_allowed(user: Any) -> bool:
    if not allowed_usernames:
        return True
    return normalize_username(getattr(user, "username", None)) in allowed_usernames


def is_shared_cookie_admin(user: Any) -> bool:
    return normalize_username(getattr(user, "username", None)) in shared_cookie_admin_usernames


def format_shared_cookie_admins() -> str:
    if not shared_cookie_admin_usernames:
        return "@denzavr"

    return ", ".join(
        f"@{username}" for username in sorted(shared_cookie_admin_usernames)
    )


def ensure_message_access(message) -> bool:
    if is_user_allowed(message.from_user):
        return True

    bot.reply_to(message, "Этот бот приватный.")
    return False


def ensure_callback_access(call) -> bool:
    if is_user_allowed(call.from_user):
        return True

    bot.answer_callback_query(call.id, "Этот бот приватный.")
    return False


def resolve_shared_cookie_file() -> Optional[str]:
    if shared_cookie_file and os.path.exists(shared_cookie_file):
        return shared_cookie_file
    return None


def copy_cookie_file_to_temp(source_path: str, prefix: str) -> str:
    fd, temp_path = tempfile.mkstemp(
        prefix=prefix,
        suffix=".txt",
        dir=config.output_folder,
    )
    os.close(fd)
    shutil.copyfile(source_path, temp_path)
    return temp_path


def is_instagram_url(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
    except ValueError:
        return False

    if ":" in domain:
        domain = domain.split(":")[0]

    return domain in {"instagram.com", "www.instagram.com"}


def is_instagram_post_url(url: str) -> bool:
    if not is_instagram_url(url):
        return False

    try:
        path = urlparse(url).path
    except ValueError:
        return False

    return path.startswith("/p/")


def send_photos(message, filepaths: list[str]) -> None:
    for filepath in filepaths:
        with open(filepath, "rb") as f:
            bot.send_photo(message.chat.id, f, reply_to_message_id=message.message_id)


def collect_downloaded_images(directory: str) -> list[str]:
    image_paths = []

    for root, _, files in os.walk(directory):
        for filename in files:
            extension = os.path.splitext(filename)[1].lower()
            if extension in image_extensions:
                image_paths.append(os.path.join(root, filename))

    return sorted(image_paths)


def run_gallery_dl_instagram(url: str, download_dir: str, cookie_path: Optional[str]) -> None:
    command = [
        gallery_dl_binary,
        "--quiet",
        "--no-part",
        "-D",
        download_dir,
        "-a",
        instagram_browser_user_agent,
        "-o",
        "extractor.instagram.videos=false",
    ]

    if cookie_path:
        command.extend(["-C", cookie_path])

    command.append(url)

    subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=gallery_dl_timeout,
    )


def try_instagram_gallery_download(
    message,
    msg,
    url: str,
    cookie_candidates: list[Optional[str]],
) -> bool:
    temp_dir = tempfile.mkdtemp(prefix="instagram-gallery-", dir=config.output_folder)

    try:
        for index, cookie_path in enumerate(cookie_candidates):
            attempt_dir = os.path.join(temp_dir, f"attempt_{index}")
            os.makedirs(attempt_dir, exist_ok=True)

            try:
                run_gallery_dl_instagram(url, attempt_dir, cookie_path)
            except OSError:
                return False
            except subprocess.TimeoutExpired:
                continue

            image_paths = collect_downloaded_images(attempt_dir)

            if image_paths:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=msg.message_id,
                    text="Отправляю файл в Telegram...",
                )
                send_photos(message, image_paths)
                bot.delete_message(message.chat.id, msg.message_id)
                return True

        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def is_shared_cookie_command(message) -> bool:
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    return text.startswith("/sharedcookie") or text.startswith("/sharedcookies")


def youtube_url_validation(url):
    youtube_regex = (
        r"(https?://)?(www\.|m\.)?"
        r"(youtube|youtu|youtube-nocookie)\.(com|be)/"
        r"(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})"
    )

    youtube_regex_match = re.match(youtube_regex, url)
    if youtube_regex_match:
        return youtube_regex_match

    return youtube_regex_match


def is_allowed_domain(url):
    """
    Check if URL belongs to allowed domains: YouTube, TikTok, Instagram, Twitter/X, Bluesky
    """

    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        # Remove port if present
        if ":" in domain:
            domain = domain.split(":")[0]

        return domain in config.allowed_domains
    except (ValueError, AttributeError):
        return False


@bot.message_handler(commands=["start", "help"])
def test(message):
    if not ensure_message_access(message):
        return

    bot.reply_to(
        message,
        "*Send me a video link* and I'll download it for you, works with *YouTube*, *TikTok*, *Instagram*, *Twitter* and *Bluesky*.\n\n_Powered by_ [yt-dlp](https://github.com/yt-dlp/yt-dlp/)",
        parse_mode="MARKDOWN",
        disable_web_page_preview=True,
    )


def _validate_url(message, url: str) -> bool:
    """Validate URL domain and YouTube-specific rules. Returns False and replies if invalid."""
    if not is_allowed_domain(url):
        bot.reply_to(
            message,
            "Неверная ссылка. Поддерживаются только YouTube, TikTok, Instagram, Twitter/X и Bluesky.",
        )
        return False

    if urlparse(url).netloc in {
        "www.youtube.com",
        "youtube.com",
        "youtu.be",
        "m.youtube.com",
        "youtube-nocookie.com",
    }:
        if not youtube_url_validation(url):
            bot.reply_to(message, "Неверная ссылка.")
            return False

    return True


def _make_progress_hook(message, msg) -> Callable:
    """Return a yt-dlp progress hook that throttles Telegram edits to once per 5s."""

    def progress(d):
        if d["status"] != "downloading":
            return
        try:
            last = last_edited.get(f"{message.chat.id}-{msg.message_id}")
            if last and (datetime.datetime.now() - last).total_seconds() < 5:
                return

            perc = round(d["downloaded_bytes"] * 100 / d["total_bytes"])
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"Скачиваю {d['info_dict']['title']}\n\n{perc}%",
            )
            last_edited[f"{message.chat.id}-{msg.message_id}"] = datetime.datetime.now()
        except Exception as e:
            print(e)

    return progress


def _send_media(message, info: Any, audio: bool) -> None:
    """Send the downloaded file back to the user via Telegram."""
    downloads = info.get("requested_downloads") or []
    filepath = downloads[0]["filepath"]
    extension = os.path.splitext(filepath)[1].lower()
    is_image = extension in image_extensions

    with open(filepath, "rb") as f:
        if audio:
            bot.send_audio(message.chat.id, f, reply_to_message_id=message.message_id)
        elif is_image:
            bot.send_photo(message.chat.id, f, reply_to_message_id=message.message_id)
        else:
            send_kwargs = {"reply_to_message_id": message.message_id}
            if downloads[0].get("width"):
                send_kwargs["width"] = downloads[0]["width"]
            if downloads[0].get("height"):
                send_kwargs["height"] = downloads[0]["height"]

            bot.send_video(message.chat.id, f, **send_kwargs)


def _cleanup(video_title: int) -> None:
    """Remove all files in the output folder that belong to this download."""
    for file in os.listdir(config.output_folder):
        if file.startswith(str(video_title)):
            os.remove(os.path.join(config.output_folder, file))


def check_url(content: str, message) -> dict:
    match = re.search(r"https?://\S+", content)
    url = match.group(0) if match else content

    if not urlparse(url).scheme:
        bot.reply_to(message, "Неверная ссылка.")
        return {"success": False}

    if not _validate_url(message, url):
        return {"success": False}

    return {"success": True, "url": url}


def download_video(message, content, audio=False, format_id="mp4") -> None:
    check = check_url(content, message)
    if not check["success"]:
        return

    url = check["url"]

    msg = bot.reply_to(
        message,
        "Скачиваю...",
    )
    video_title = round(time.time() * 1000)

    ydl_opts: yt_dlp._Params = {
        "format": format_id,
        "outtmpl": f"{config.output_folder}/{video_title}.%(ext)s",
        "progress_hooks": [_make_progress_hook(message, msg)],
        "max_filesize": config.max_filesize,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
        if audio
        else [],
        "js_runtimes": {"bun": {"path": "bun"}},
        "remote_components": {"ejs:github"},
    }

    if config.js_runtime:
        ydl_opts["js_runtimes"] = config.js_runtime
        ydl_opts["remote_components"] = {"ejs:github"}

    shared_cookie_copy = None
    cookie_candidates: list[Optional[str]] = []
    attempted_instagram_gallery = False
    try:
        shared_cookie_path = resolve_shared_cookie_file()
        if shared_cookie_path:
            shared_cookie_copy = copy_cookie_file_to_temp(
                shared_cookie_path,
                "shared_cookies_",
            )

        if shared_cookie_copy:
            ydl_opts["cookiefile"] = shared_cookie_copy
            cookie_candidates.append(shared_cookie_copy)

        cookie_candidates.append(None)

        if not audio and format_id == "mp4" and is_instagram_post_url(url):
            attempted_instagram_gallery = True
            if try_instagram_gallery_download(message, msg, url, cookie_candidates):
                return

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text="Отправляю файл в Telegram...",
            )

            _send_media(message, info, audio)
            bot.delete_message(message.chat.id, msg.message_id)

    except (DownloadError, ExtractorError) as e:
        err = str(e).lower()
        text: str

        if (
            not audio
            and is_instagram_url(url)
            and not attempted_instagram_gallery
            and "[instagram]" in err
            and (
                "there is no video in this post" in err
                or "no video formats found" in err
            )
            and try_instagram_gallery_download(message, msg, url, cookie_candidates)
        ):
            return
        if "[instagram]" in err and audio and (
            "there is no video in this post" in err
            or "no video formats found" in err
        ):
            text = "Это Instagram-пост с картинками, из него нельзя извлечь аудио."
        elif "[instagram]" in err and (
            "there is no video in this post" in err
            or "no video formats found" in err
        ):
            text = "Похоже, это пост только с фото. Сейчас yt-dlp не умеет скачивать такой тип Instagram-поста."
        elif "[youtube]" in err and "sign in" in err:
            text = "YouTube сейчас ограничивает сторонние загрузчики. Попробуйте позже."
        elif "instagram sent an empty media response" in err:
            text = "Instagram не отдал медиа. Обычно это значит, что нужен вход или текущие cookies больше не подходят."
        elif "login required" in err or "rate-limit reached" in err:
            text = "Контент недоступен: нужен вход или сработало ограничение по запросам."
        else:
            text = "Не удалось скачать файл. Попробуйте еще раз позже."

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text=text,
        )

    except Exception:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text=(
                f"Не удалось отправить файл. Убедитесь, что он не больше "
                f"*{round(config.max_filesize / 1_000_000)}MB* и поддерживается Telegram."
            ),
            parse_mode="MARKDOWN",
        )

    finally:
        for temp_cookie_path in (shared_cookie_copy,):
            if temp_cookie_path and os.path.exists(temp_cookie_path):
                os.remove(temp_cookie_path)
        _cleanup(video_title)


def log(message, text: str, media: str):
    if config.logs:
        if message.chat.type == "private":
            chat_info = "Private chat"
        else:
            chat_info = f"Group: *{message.chat.title}* (`{message.chat.id}`)"

        bot.send_message(
            config.logs,
            f"Download request ({media}) from @{message.from_user.username} ({message.from_user.id})\n\n{chat_info}\n\n{text}",
        )


def get_text(message):
    if len(message.text.split(" ")) < 2:
        if message.reply_to_message and message.reply_to_message.text:
            return message.reply_to_message.text
        else:
            return None
    else:
        return message.text.split(" ")[1]


@bot.message_handler(commands=["download"])
def download_command(message):
    if not ensure_message_access(message):
        return

    text = get_text(message)
    if not text:
        bot.reply_to(
            message, "Неверное использование. Используйте `/download url`.", parse_mode="MARKDOWN"
        )
        return

    log(message, text, "video")
    download_video(message, text)


@bot.message_handler(commands=["audio"])
def download_audio_command(message):
    if not ensure_message_access(message):
        return

    text = get_text(message)
    if not text:
        bot.reply_to(message, "Неверное использование. Используйте `/audio url`.", parse_mode="MARKDOWN")
        return

    log(message, text, "audio")
    download_video(message, text, True)


@bot.message_handler(commands=["custom"])
def custom(message):
    if not ensure_message_access(message):
        return

    text = message.text if message.text else message.caption

    check = check_url(text, message)
    if not check["success"]:
        return

    url = check["url"]

    msg = bot.reply_to(message, "Получаю доступные форматы...")

    with yt_dlp.YoutubeDL() as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats") or []

    data = {
        f"{x['resolution']}.{x['ext']}": {"callback_data": f"{x['format_id']}"}
        for x in formats
        if x["video_ext"] != "none"
    }

    markup = quick_markup(data, row_width=2)

    bot.delete_message(msg.chat.id, msg.message_id)
    bot.reply_to(message, "Выберите формат.", reply_markup=markup)


def filter_cookies_by_domain(cookie_data: str) -> str:
    lines = cookie_data.split("\n")
    filtered_lines = []

    for line in lines:
        if line.startswith("#") or not line.strip():
            filtered_lines.append(line)
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            continue

        domain = parts[0].lstrip(".")

        is_allowed = False
        for allowed_domain in config.allowed_domains:
            if domain == allowed_domain or domain.endswith("." + allowed_domain):
                is_allowed = True
                break

        if is_allowed:
            filtered_lines.append(line)

    return "\n".join(filtered_lines)


@bot.message_handler(commands=["id"])
def get_chat_id(message):
    if not ensure_message_access(message):
        return

    bot.reply_to(message, message.chat.id)


def is_cookie_command(message):
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    return text.startswith("/cookie") or text.startswith("/cookies")


@bot.message_handler(func=is_shared_cookie_command, content_types=["document", "text"])
def handle_shared_cookie(message):
    if not ensure_message_access(message):
        return
    if not is_shared_cookie_admin(message.from_user):
        bot.reply_to(
            message,
            f"Общие cookies может обновлять только {format_shared_cookie_admins()}.",
        )
        return

    shared_cookie_path = resolve_shared_cookie_file() or shared_cookie_file
    if not shared_cookie_path:
        bot.reply_to(
            message,
            "Общие cookies не настроены в config.py.",
        )
        return

    document = getattr(message, "document", None)

    if not document:
        if os.path.exists(shared_cookie_path):
            bot.reply_to(
                message,
                "Общие cookies уже настроены. Отправьте новый файл с этой командой, чтобы обновить их.",
            )
        else:
            bot.reply_to(
                message,
                "Общие cookies пока не загружены. Отправьте файл с этой командой.",
            )
        return

    file_info = bot.get_file(document.file_id)
    if not file_info.file_path:
        bot.reply_to(message, "Не удалось получить информацию о файле.")
        return

    downloaded_file = bot.download_file(file_info.file_path)
    cookie_data = downloaded_file.decode("utf-8")
    filtered_cookie_data = filter_cookies_by_domain(cookie_data)

    os.makedirs(os.path.dirname(shared_cookie_path), exist_ok=True)
    with open(shared_cookie_path, "w") as f:
        f.write(filtered_cookie_data)

    bot.reply_to(
        message,
        "Общие cookies успешно обновлены. Бот начнет использовать их для новых запросов.",
    )


@bot.message_handler(func=is_cookie_command, content_types=["document", "text"])
def handle_cookie(message):
    if not ensure_message_access(message):
        return

    bot.reply_to(
        message,
        (
            "Личные cookies отключены. Бот использует только общие cookies. "
            f"Обновить их через /sharedcookies может только {format_shared_cookie_admins()}."
        ),
    )


@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if not ensure_callback_access(call):
        return

    if call.message.reply_to_message:
        if call.from_user.id == call.message.reply_to_message.from_user.id:
            url = get_text(call.message.reply_to_message)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            download_video(
                call.message.reply_to_message, url, format_id=f"{call.data}+bestaudio"
            )
        else:
            bot.answer_callback_query(call.id, "Эту кнопку нажали не вы.")


@bot.message_handler(
    func=lambda m: True,
    content_types=[
        "text",
        "photo",
        "audio",
        "video",
        "document",
    ],
)
def handle_private_messages(message: types.Message):
    if not ensure_message_access(message):
        return

    text = (
        message.text if message.text else message.caption if message.caption else None
    )

    if message.chat.type == "private":
        log(message, text or "<no text>", "video")
        download_video(message, text)
        return


def main() -> None:
    print(f"ready as @{bot.user.username}")
    bot.infinity_polling()


if __name__ == "__main__":
    main()
