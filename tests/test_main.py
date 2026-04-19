import importlib.util
import os
import pathlib
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
    data_dir = temp_root / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

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
    fake_config.secret_key = "test-secret"
    fake_config.js_runtime = {"bun": {"path": "bun"}}
    fake_config.allowed_usernames = []
    fake_config.shared_cookie_file = None
    for key, value in (config_overrides or {}).items():
        setattr(fake_config, key, value)

    fake_requests = types.ModuleType("requests")

    class FakeSession:
        pass

    fake_requests.Session = FakeSession

    fake_fernet_module = types.ModuleType("cryptography.fernet")

    class FakeFernet:
        def __init__(self, _key):
            pass

        def encrypt(self, data):
            return data

        def decrypt(self, data):
            return data

    fake_fernet_module.Fernet = FakeFernet
    fake_cryptography = types.ModuleType("cryptography")
    fake_cryptography.fernet = fake_fernet_module

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
        "requests": fake_requests,
        "cryptography": fake_cryptography,
        "cryptography.fernet": fake_fernet_module,
        "telebot": fake_telebot,
        "telebot.types": fake_types_module,
        "telebot.util": fake_util_module,
        "yt_dlp": fake_yt_dlp,
        "yt_dlp.utils": fake_yt_dlp_utils,
    }

    old_modules = {name: sys.modules.get(name) for name in patched_modules}
    old_app_data_dir = os.environ.get("APP_DATA_DIR")
    os.environ["APP_DATA_DIR"] = str(data_dir)

    try:
        sys.modules.update(patched_modules)
        module_name = f"main_under_test_{media_extension.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        if old_app_data_dir is None:
            os.environ.pop("APP_DATA_DIR", None)
        else:
            os.environ["APP_DATA_DIR"] = old_app_data_dir

        for name, previous in old_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    return module, FakeYoutubeDL


class MainTests(unittest.TestCase):
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

        self.assertEqual(fake_ydl.last_opts["cookiefile"], str(shared_cookie))

    def test_app_data_dir_is_used_for_sqlite_db(self):
        module, _fake_ydl = load_main_module(media_extension=".mp4")

        self.assertTrue(module.db_path.endswith("/data/db.db"))
        self.assertTrue(pathlib.Path(module.db_path).exists())

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

        self.assertEqual(module.bot.replies[-1][1], "This bot is private.")
        self.assertIsNone(fake_ydl.last_url)

    def test_instagram_photo_only_error_gets_specific_message(self):
        module, _fake_ydl = load_main_module(
            media_extension=".jpg",
            raised_error="ERROR: [Instagram] DXShON4gKIZ: There is no video in this post",
        )
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username="alice"),
            text=INSTAGRAM_PHOTO_URL,
        )

        module.download_video(message, INSTAGRAM_PHOTO_URL)

        edited_args, edited_kwargs = module.bot.edited[-1]
        self.assertEqual(
            edited_args[0],
            "This Instagram post appears to be photo-only, and yt-dlp cannot download that post type right now.",
        )
        self.assertEqual(edited_args[1], 123)
        self.assertEqual(edited_args[2], 99)


if __name__ == "__main__":
    unittest.main()
