import importlib.util
import os
import pathlib
import sys
import tempfile
import types


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_PATH = REPO_ROOT / "main.py"
INSTAGRAM_PHOTO_URL = (
    "https://www.instagram.com/p/DXShON4gKIZ/"
    "?utm_source=ig_web_copy_link&igsh=NTc4MTIwNjQ2YQ=="
)
YOUTUBE_VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
DEFAULT_SHARED_COOKIE_PAYLOAD = (
    "# Netscape HTTP Cookie File\n"
    ".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\tshared-session\n"
).encode("utf-8")


def load_main_module(media_extension=".mp4", raised_error=None, config_overrides=None):
    temp_root = pathlib.Path(tempfile.mkdtemp(prefix="yt-dlp-telegram-e2e-"))
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
    fake_config.allowed_usernames = ["denzavr", "Deeana_zvrn"]
    fake_config.shared_cookie_admin_usernames = ["denzavr"]
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
            return types.SimpleNamespace(chat=message.chat, message_id=99, text=text)

        def edit_message_text(self, *args, **kwargs):
            return None

        def edit_message_caption(self, *args, **kwargs):
            return None

        def send_audio(self, *args, **kwargs):
            return None

        def send_photo(self, *args, **kwargs):
            return None

        def send_video(self, *args, **kwargs):
            return None

        def send_document(self, *args, **kwargs):
            return None

        def delete_message(self, *args, **kwargs):
            return None

        def send_message(self, *args, **kwargs):
            return None

        def get_file(self, _file_id):
            return types.SimpleNamespace(file_path="cookies.txt")

        def download_file(self, _file_path):
            return b""

        def answer_callback_query(self, *args, **kwargs):
            return None

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
                "title": "Test media",
                "requested_downloads": [
                    {
                        "filepath": filepath,
                        "width": 320,
                        "height": 240,
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
        module_name = f"main_e2e_under_test_{media_extension.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        for name, previous in old_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    return module, FakeYoutubeDL


class E2EHarness:
    def __init__(self, module, fake_ydl):
        self.module = module
        self.fake_ydl = fake_ydl
        self.events = []

    def _reset_events(self):
        self.events = []

    def _install_recorders(self):
        def reply_to(message, text, **kwargs):
            self.events.append({"event": "reply", "text": text, "kwargs": kwargs})
            return types.SimpleNamespace(chat=message.chat, message_id=999, text=text)

        def edit_message_text(*args, **kwargs):
            self.events.append({"event": "edit", "args": list(args), "kwargs": kwargs})

        def edit_message_caption(*args, **kwargs):
            self.events.append(
                {"event": "edit_caption", "args": list(args), "kwargs": kwargs}
            )

        def delete_message(*args, **kwargs):
            self.events.append({"event": "delete", "args": list(args), "kwargs": kwargs})

        def send_file(kind, chat_id, file_obj, **kwargs):
            self.events.append(
                {
                    "event": kind,
                    "chat_id": chat_id,
                    "name": os.path.basename(getattr(file_obj, "name", "")),
                    "size": os.fstat(file_obj.fileno()).st_size,
                    "kwargs": kwargs,
                }
            )

        self.module.bot.reply_to = reply_to
        self.module.bot.edit_message_text = edit_message_text
        self.module.bot.edit_message_caption = edit_message_caption
        self.module.bot.delete_message = delete_message
        self.module.bot.send_photo = (
            lambda chat_id, file_obj, **kwargs: send_file(
                "send_photo", chat_id, file_obj, **kwargs
            )
        )
        self.module.bot.send_video = (
            lambda chat_id, file_obj, **kwargs: send_file(
                "send_video", chat_id, file_obj, **kwargs
            )
        )
        self.module.bot.send_audio = (
            lambda chat_id, file_obj, **kwargs: send_file(
                "send_audio", chat_id, file_obj, **kwargs
            )
        )
        self.module.bot.send_document = (
            lambda chat_id, file_obj, **kwargs: send_file(
                "send_document", chat_id, file_obj, **kwargs
            )
        )

    def make_message(
        self,
        text,
        username="denzavr",
        document=None,
        caption=None,
    ):
        return types.SimpleNamespace(
            chat=types.SimpleNamespace(id=123, type="private"),
            message_id=7,
            from_user=types.SimpleNamespace(id=456, username=username),
            text=text,
            caption=caption,
            document=document,
        )

    def enable_gallery_dl_photo_success(self, filename="photo.jpg", content=b"image"):
        def fake_run(command, capture_output, text, check, timeout):
            download_dir = pathlib.Path(command[command.index("-D") + 1])
            download_dir.mkdir(parents=True, exist_ok=True)
            (download_dir / filename).write_bytes(content)
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        self.module.subprocess.run = fake_run

    def run_download(self, url, username="denzavr", audio=False):
        self._reset_events()
        self._install_recorders()
        message = self.make_message(url, username=username)
        self.module.download_video(message, url, audio=audio)
        return self.events

    def run_personal_cookie_command(self, username="denzavr"):
        self._reset_events()
        self._install_recorders()
        message = self.make_message("/cookies", username=username)
        self.module.handle_cookie(message)
        return self.events

    def run_shared_cookie_command(
        self,
        username="denzavr",
        cookie_payload=DEFAULT_SHARED_COOKIE_PAYLOAD,
    ):
        self._reset_events()
        self._install_recorders()
        self.module.bot.download_file = lambda _path: cookie_payload
        message = self.make_message(
            "/sharedcookies",
            username=username,
            document=types.SimpleNamespace(file_id="file-1"),
        )
        self.module.handle_shared_cookie(message)
        return self.events


def build_e2e_harness(
    media_extension=".mp4",
    raised_error=None,
    config_overrides=None,
):
    module, fake_ydl = load_main_module(
        media_extension=media_extension,
        raised_error=raised_error,
        config_overrides=config_overrides,
    )
    return E2EHarness(module, fake_ydl)
