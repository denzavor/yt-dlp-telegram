import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_PATH = REPO_ROOT / "main.py"
INSTAGRAM_PHOTO_URL = (
    "https://www.instagram.com/p/DXShON4gKIZ/"
    "?utm_source=ig_web_copy_link&igsh=NTc4MTIwNjQ2YQ=="
)
INSTAGRAM_REEL_URL = "https://www.instagram.com/reel/DXQ4sDqAFOS/"


def load_main_module(media_extension=".mp4", raised_error=None, config_overrides=None):
    temp_root = pathlib.Path(tempfile.mkdtemp(prefix="yt-dlp-telegram-tests-"))
    output_dir = temp_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    fake_config = types.ModuleType("config")
    fake_config.token = "test-token"
    fake_config.logs = None
    fake_config.max_filesize = 50_000_000
    fake_config.output_folder = str(output_dir)
    fake_config.allowed_domains = [
        "youtube.com",
        "www.youtube.com",
        "youtu.be",
        "m.youtube.com",
        "youtube-nocookie.com",
        "instagram.com",
        "www.instagram.com",
        "tiktok.com",
        "www.tiktok.com",
        "twitter.com",
        "www.twitter.com",
        "x.com",
        "www.x.com",
        "bsky.app",
        "www.bsky.app",
    ]
    fake_config.js_runtime = {"bun": {"path": "bun"}}
    fake_config.allowed_usernames = []
    fake_config.shared_cookie_file = None
    for key, value in (config_overrides or {}).items():
        setattr(fake_config, key, value)

    fake_types_module = types.ModuleType("telebot.types")

    class InlineKeyboardMarkup:
        def __init__(self):
            self.buttons = []

        def add(self, button):
            self.buttons.append(button)

    class InlineKeyboardButton:
        def __init__(self, text, callback_data=None):
            self.text = text
            self.callback_data = callback_data

    class Message:
        pass

    fake_types_module.InlineKeyboardMarkup = InlineKeyboardMarkup
    fake_types_module.InlineKeyboardButton = InlineKeyboardButton
    fake_types_module.Message = Message

    fake_util_module = types.ModuleType("telebot.util")

    def quick_markup(data, row_width=2):
        return {"data": data, "row_width": row_width}

    fake_util_module.quick_markup = quick_markup

    fake_telebot = types.ModuleType("telebot")

    class FakeTeleBot:
        def __init__(self, token):
            self.token = token
            self.user = types.SimpleNamespace(username="test_bot")
            self.sent_audio = []
            self.sent_photo = []
            self.sent_video = []
            self.sent_document = []
            self.replies = []
            self.deleted = []
            self.edited = []
            self.polled = False

        def message_handler(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def callback_query_handler(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def reply_to(self, message, text, **kwargs):
            reply = types.SimpleNamespace(chat=message.chat, message_id=99, text=text)
            self.replies.append((message, text, kwargs))
            return reply

        def edit_message_text(self, *args, **kwargs):
            self.edited.append((args, kwargs))

        def edit_message_caption(self, *args, **kwargs):
            self.edited.append((args, kwargs))

        def send_audio(self, chat_id, file_obj, **kwargs):
            self.sent_audio.append((chat_id, file_obj.read(), kwargs))

        def send_photo(self, chat_id, file_obj, **kwargs):
            self.sent_photo.append((chat_id, file_obj.read(), kwargs))

        def send_video(self, chat_id, file_obj, **kwargs):
            self.sent_video.append((chat_id, file_obj.read(), kwargs))

        def send_document(self, chat_id, file_obj, **kwargs):
            self.sent_document.append((chat_id, file_obj.read(), kwargs))

        def delete_message(self, *args, **kwargs):
            self.deleted.append((args, kwargs))

        def send_message(self, *args, **kwargs):
            pass

        def get_file(self, _file_id):
            return types.SimpleNamespace(file_path="cookies.txt")

        def download_file(self, _file_path):
            return b""

        def answer_callback_query(self, *args, **kwargs):
            pass

        def infinity_polling(self):
            self.polled = True

    fake_telebot.TeleBot = FakeTeleBot
    fake_telebot.types = fake_types_module

    fake_yt_dlp_utils = types.ModuleType("yt_dlp.utils")

    class DownloadError(Exception):
        pass

    class ExtractorError(Exception):
        pass

    fake_yt_dlp_utils.DownloadError = DownloadError
    fake_yt_dlp_utils.ExtractorError = ExtractorError

    fake_yt_dlp = types.ModuleType("yt_dlp")
    fake_yt_dlp._Params = dict

    class FakeYoutubeDL:
        last_url = None
        last_download = None
        last_opts = None

        def __init__(self, opts=None):
            self.opts = opts or {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            FakeYoutubeDL.last_url = url
            FakeYoutubeDL.last_download = download
            FakeYoutubeDL.last_opts = self.opts

            if raised_error is not None:
                raise DownloadError(raised_error)

            output_template = self.opts["outtmpl"]
            filepath = output_template.replace("%(ext)s", media_extension.lstrip("."))
            pathlib.Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(filepath).write_bytes(b"test-media")

            return {
                "title": "Instagram media",
                "requested_downloads": [
                    {
                        "filepath": filepath,
                        "width": 1080,
                        "height": 1350,
                    }
                ],
            }

    fake_yt_dlp.YoutubeDL = FakeYoutubeDL

    patched_modules = {
        "config": fake_config,
        "telebot": fake_telebot,
        "telebot.types": fake_types_module,
        "telebot.util": fake_util_module,
        "yt_dlp": fake_yt_dlp,
        "yt_dlp.utils": fake_yt_dlp_utils,
    }

    old_modules = {name: sys.modules.get(name) for name in patched_modules}

    try:
        sys.modules.update(patched_modules)
        module_name = f"main_under_test_{media_extension.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        module.subprocess = types.SimpleNamespace(
            run=subprocess.run,
            TimeoutExpired=subprocess.TimeoutExpired,
            CompletedProcess=subprocess.CompletedProcess,
        )
    finally:
        for name, previous in old_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    return module, FakeYoutubeDL


class MainTests(unittest.TestCase):
    def test_initial_download_message_has_no_status_footer(self):
        module, _fake_ydl = load_main_module(media_extension=".mp4")
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text="https://www.youtube.com/watch?v=jNQXAC9IVRw",
        )

        module.download_video(message, message.text)

        self.assertEqual(module.bot.replies[0][1], "Скачиваю...")

    def test_progress_message_has_no_status_footer(self):
        module, _fake_ydl = load_main_module(media_extension=".mp4")
        message = types.SimpleNamespace(chat=types.SimpleNamespace(id=123), message_id=7)
        status_message = types.SimpleNamespace(message_id=99)

        hook = module._make_progress_hook(message, status_message)
        hook(
            {
                "status": "downloading",
                "downloaded_bytes": 50,
                "total_bytes": 100,
                "info_dict": {"title": "Test video"},
            }
        )

        self.assertEqual(
            module.bot.edited[-1][1]["text"],
            "Скачиваю Test video\n\n50%",
        )

    def test_instagram_photo_url_is_downloaded_and_sent_as_photo(self):
        module, fake_ydl = load_main_module(media_extension=".jpg")
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="alice"),
            text=INSTAGRAM_PHOTO_URL,
        )

        module.download_video(message, INSTAGRAM_PHOTO_URL)

        self.assertEqual(fake_ydl.last_url, INSTAGRAM_PHOTO_URL)
        self.assertTrue(fake_ydl.last_download)
        self.assertEqual(len(module.bot.sent_photo), 1)
        self.assertEqual(len(module.bot.sent_video), 0)

    def test_instagram_photo_post_uses_gallery_dl_with_shared_cookies_before_yt_dlp(self):
        shared_cookie = pathlib.Path(tempfile.mkdtemp()) / "instagram.txt"
        shared_cookie.write_text("cookie-data", encoding="utf-8")
        module, fake_ydl = load_main_module(
            media_extension=".mp4",
            config_overrides={"shared_cookie_file": str(shared_cookie)},
        )
        calls = []

        def fake_run(command, capture_output, text, check, timeout):
            calls.append(
                {
                    "command": command,
                    "timeout": timeout,
                }
            )
            download_dir = pathlib.Path(command[command.index("-D") + 1])
            download_dir.mkdir(parents=True, exist_ok=True)
            (download_dir / "photo.jpg").write_bytes(b"image-bytes")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        module.subprocess.run = fake_run

        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text=INSTAGRAM_PHOTO_URL,
        )

        module.download_video(message, INSTAGRAM_PHOTO_URL)

        self.assertIsNone(fake_ydl.last_url)
        self.assertEqual(len(calls), 1)
        command = calls[0]["command"]
        self.assertEqual(calls[0]["timeout"], 25)
        self.assertIn("-C", command)
        shared_cookie_arg = command[command.index("-C") + 1]
        self.assertNotEqual(shared_cookie_arg, str(shared_cookie))
        self.assertTrue(pathlib.Path(shared_cookie_arg).name.startswith("shared_cookies_"))
        self.assertEqual(len(module.bot.sent_photo), 1)
        self.assertEqual(len(module.bot.sent_video), 0)

    def test_shared_cookie_file_is_used_when_personal_cookie_is_missing(self):
        shared_cookie = pathlib.Path(tempfile.mkdtemp()) / "instagram.txt"
        shared_cookie.write_text("cookie-data", encoding="utf-8")

        module, fake_ydl = load_main_module(
            media_extension=".mp4",
            config_overrides={"shared_cookie_file": str(shared_cookie)},
        )
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text=INSTAGRAM_REEL_URL,
        )

        module.download_video(message, INSTAGRAM_REEL_URL)

        self.assertNotEqual(fake_ydl.last_opts["cookiefile"], str(shared_cookie))
        self.assertTrue(
            pathlib.Path(fake_ydl.last_opts["cookiefile"]).name.startswith(
                "shared_cookies_"
            )
        )

    def test_shared_cookie_file_is_copied_before_downloader_can_mutate_it(self):
        shared_cookie = pathlib.Path(tempfile.mkdtemp()) / "instagram.txt"
        original_cookie_text = "cookie-data"
        shared_cookie.write_text(original_cookie_text, encoding="utf-8")

        module, fake_ydl = load_main_module(
            media_extension=".mp4",
            config_overrides={"shared_cookie_file": str(shared_cookie)},
        )
        original_youtube_dl = module.yt_dlp.YoutubeDL

        class MutatingYoutubeDL(original_youtube_dl):
            def extract_info(self, url, download=False):
                cookiefile = self.opts.get("cookiefile")
                if cookiefile:
                    with open(cookiefile, "a", encoding="utf-8") as f:
                        f.write("\nmutated")
                return super().extract_info(url, download=download)

        module.yt_dlp.YoutubeDL = MutatingYoutubeDL
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text=INSTAGRAM_REEL_URL,
        )

        module.download_video(message, INSTAGRAM_REEL_URL)

        self.assertNotEqual(fake_ydl.last_opts["cookiefile"], str(shared_cookie))
        self.assertEqual(shared_cookie.read_text(encoding="utf-8"), original_cookie_text)

    def test_instagram_photo_error_falls_back_to_gallery_dl(self):
        module, _fake_ydl = load_main_module(
            media_extension=".mp4",
            raised_error="ERROR: [Instagram] DXShON4gKIZ: No video formats found!",
        )

        def fake_run(command, capture_output, text, check, timeout):
            download_dir = pathlib.Path(command[command.index("-D") + 1])
            download_dir.mkdir(parents=True, exist_ok=True)
            (download_dir / "photo.jpg").write_bytes(b"image-bytes")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        module.subprocess.run = fake_run

        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text=INSTAGRAM_PHOTO_URL,
        )

        module.download_video(message, INSTAGRAM_PHOTO_URL)

        self.assertEqual(len(module.bot.sent_photo), 1)
        self.assertEqual(
            module.bot.edited[-1][1]["text"], "Отправляю файл в Telegram..."
        )

    def test_instagram_gallery_download_tries_shared_cookies_then_public(self):
        shared_cookie = pathlib.Path(tempfile.mkdtemp()) / "instagram.txt"
        shared_cookie.write_text("cookie-data", encoding="utf-8")
        module, _fake_ydl = load_main_module(
            media_extension=".mp4",
            raised_error="ERROR: [Instagram] DXShON4gKIZ: No video formats found!",
            config_overrides={"shared_cookie_file": str(shared_cookie)},
        )
        calls = []

        def fake_run(command, capture_output, text, check, timeout):
            calls.append(command)
            download_dir = pathlib.Path(command[command.index("-D") + 1])
            download_dir.mkdir(parents=True, exist_ok=True)
            if "-C" not in command:
                (download_dir / "photo.jpg").write_bytes(b"image-bytes")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        module.subprocess.run = fake_run

        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text=INSTAGRAM_PHOTO_URL,
        )

        module.download_video(message, INSTAGRAM_PHOTO_URL)

        self.assertEqual(len(calls), 2)
        self.assertIn("-C", calls[0])
        self.assertNotIn("-C", calls[1])
        shared_cookie_arg = calls[0][calls[0].index("-C") + 1]
        self.assertNotEqual(shared_cookie_arg, str(shared_cookie))
        self.assertTrue(pathlib.Path(shared_cookie_arg).name.startswith("shared_cookies_"))

    def test_instagram_photo_error_without_gallery_dl_keeps_russian_message(self):
        module, _fake_ydl = load_main_module(
            media_extension=".jpg",
            raised_error="ERROR: [Instagram] DXShON4gKIZ: No video formats found!",
        )
        module.subprocess.run = lambda *args, **kwargs: (_ for _ in ()).throw(
            FileNotFoundError("gallery-dl")
        )

        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text=INSTAGRAM_PHOTO_URL,
        )

        module.download_video(message, INSTAGRAM_PHOTO_URL)

        edited_args, edited_kwargs = module.bot.edited[-1]
        self.assertEqual(edited_args, ())
        self.assertEqual(
            edited_kwargs["text"],
            "Похоже, это пост только с фото. Сейчас yt-dlp не умеет скачивать такой тип Instagram-поста.",
        )

    def test_shared_cookie_command_updates_bot_cookie_file(self):
        shared_cookie = pathlib.Path(tempfile.mkdtemp()) / "instagram.txt"
        module, _fake_ydl = load_main_module(
            media_extension=".mp4",
            config_overrides={"shared_cookie_file": str(shared_cookie)},
        )
        cookie_payload = (
            "# Netscape HTTP Cookie File\n"
            ".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\tabc\n"
        ).encode("utf-8")
        module.bot.download_file = lambda _path: cookie_payload

        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text="/sharedcookies",
            caption=None,
            document=types.SimpleNamespace(file_id="file-1"),
        )

        module.handle_shared_cookie(message)

        self.assertTrue(shared_cookie.exists())
        self.assertIn("sessionid", shared_cookie.read_text(encoding="utf-8"))
        self.assertEqual(
            module.bot.replies[-1][1],
            "Общие cookies успешно обновлены. Бот начнет использовать их для новых запросов.",
        )

    def test_shared_cookie_command_is_limited_to_denzavr(self):
        shared_cookie = pathlib.Path(tempfile.mkdtemp()) / "instagram.txt"
        module, _fake_ydl = load_main_module(
            media_extension=".mp4",
            config_overrides={
                "shared_cookie_file": str(shared_cookie),
                "shared_cookie_admin_usernames": ["denzavr"],
            },
        )
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="Deeana_zvrn"),
            text="/sharedcookies",
            caption=None,
            document=types.SimpleNamespace(file_id="file-1"),
        )

        module.handle_shared_cookie(message)

        self.assertFalse(shared_cookie.exists())
        self.assertEqual(
            module.bot.replies[-1][1],
            "Общие cookies может обновлять только @denzavr.",
        )

    def test_personal_cookie_command_is_disabled(self):
        module, _fake_ydl = load_main_module(media_extension=".mp4")
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="Deeana_zvrn"),
            text="/cookies",
            caption=None,
            document=None,
        )

        module.handle_cookie(message)

        self.assertEqual(
            module.bot.replies[-1][1],
            "Личные cookies отключены. Бот использует только общие cookies. Обновить их через /sharedcookies может только @denzavr.",
        )

    def test_private_mode_blocks_unknown_users(self):
        module, fake_ydl = load_main_module(
            media_extension=".mp4",
            config_overrides={"allowed_usernames": ["denzavr", "Deeana_zvrn"]},
        )
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="someone_else"),
            text=INSTAGRAM_REEL_URL,
            caption=None,
        )

        module.handle_private_messages(message)

        self.assertEqual(module.bot.replies[-1][1], "Этот бот приватный.")
        self.assertIsNone(fake_ydl.last_url)

    def test_instagram_photo_only_error_gets_specific_message(self):
        module, _fake_ydl = load_main_module(
            media_extension=".jpg",
            raised_error="ERROR: [Instagram] DXShON4gKIZ: There is no video in this post",
        )
        module.subprocess.run = lambda *args, **kwargs: types.SimpleNamespace(
            returncode=1, stdout="", stderr=""
        )
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="alice"),
            text=INSTAGRAM_PHOTO_URL,
        )

        module.download_video(message, INSTAGRAM_PHOTO_URL)

        edited_args, edited_kwargs = module.bot.edited[-1]
        self.assertEqual(edited_args, ())
        self.assertEqual(
            edited_kwargs["text"],
            "Похоже, это пост только с фото. Сейчас yt-dlp не умеет скачивать такой тип Instagram-поста.",
        )
        self.assertEqual(edited_kwargs["chat_id"], 123)
        self.assertEqual(edited_kwargs["message_id"], 99)

    def test_instagram_no_video_formats_error_gets_photo_message(self):
        module, _fake_ydl = load_main_module(
            media_extension=".jpg",
            raised_error="ERROR: [Instagram] DXShON4gKIZ: No video formats found!",
        )
        module.subprocess.run = lambda *args, **kwargs: types.SimpleNamespace(
            returncode=1, stdout="", stderr=""
        )
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text=INSTAGRAM_PHOTO_URL,
        )

        module.download_video(message, INSTAGRAM_PHOTO_URL)

        edited_args, edited_kwargs = module.bot.edited[-1]
        self.assertEqual(edited_args, ())
        self.assertEqual(
            edited_kwargs["text"],
            "Похоже, это пост только с фото. Сейчас yt-dlp не умеет скачивать такой тип Instagram-поста.",
        )

    def test_instagram_photo_post_audio_request_gets_russian_message(self):
        module, _fake_ydl = load_main_module(
            media_extension=".jpg",
            raised_error="ERROR: [Instagram] DXShON4gKIZ: No video formats found!",
        )
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text=INSTAGRAM_PHOTO_URL,
        )

        module.download_video(message, INSTAGRAM_PHOTO_URL, audio=True)

        edited_args, edited_kwargs = module.bot.edited[-1]
        self.assertEqual(edited_args, ())
        self.assertEqual(
            edited_kwargs["text"],
            "Это Instagram-пост с картинками, из него нельзя извлечь аудио.",
        )

    def test_instagram_empty_media_error_gets_russian_message(self):
        module, _fake_ydl = load_main_module(
            media_extension=".mp4",
            raised_error=(
                "ERROR: [Instagram] DXQ4sDqAFOS: Instagram sent an empty media response. "
                "Check if this post is accessible in your browser without being logged-in."
            ),
        )
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text=INSTAGRAM_REEL_URL,
        )

        module.download_video(message, INSTAGRAM_REEL_URL)

        edited_args, edited_kwargs = module.bot.edited[-1]
        self.assertEqual(edited_args, ())
        self.assertEqual(
            edited_kwargs["text"],
            "Instagram не отдал медиа. Обычно это значит, что нужен вход или текущие cookies больше не подходят.",
        )

    def test_invalid_download_command_usage_is_russian(self):
        module, _fake_ydl = load_main_module(media_extension=".mp4")
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="denzavr"),
            text="/download",
            reply_to_message=None,
        )

        module.download_command(message)

        self.assertEqual(
            module.bot.replies[-1][1],
            "Неверное использование. Используйте `/download url`.",
        )


if __name__ == "__main__":
    unittest.main()
