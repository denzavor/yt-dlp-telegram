import pathlib
import subprocess
import tempfile
import unittest

try:
    from e2e_harness import (
        DEFAULT_SHARED_COOKIE_PAYLOAD,
        INSTAGRAM_PHOTO_URL,
        YOUTUBE_VIDEO_URL,
        build_e2e_harness,
    )
except ModuleNotFoundError:
    from tests.e2e_harness import (
        DEFAULT_SHARED_COOKIE_PAYLOAD,
        INSTAGRAM_PHOTO_URL,
        YOUTUBE_VIDEO_URL,
        build_e2e_harness,
    )


class E2ETests(unittest.TestCase):
    def test_allowed_user_can_download_video_end_to_end(self):
        harness = build_e2e_harness(media_extension=".mp4")

        events = harness.run_download(YOUTUBE_VIDEO_URL, username="Deeana_zvrn")

        self.assertEqual(events[0]["event"], "reply")
        self.assertEqual(events[0]["text"], "Скачиваю...")
        self.assertEqual(events[-2]["event"], "send_video")
        self.assertEqual(events[-1]["event"], "delete")

    def test_instagram_photo_end_to_end_uses_gallery_fallback(self):
        shared_cookie = pathlib.Path(tempfile.mkdtemp()) / "instagram.txt"
        shared_cookie.write_text("cookie-data", encoding="utf-8")
        harness = build_e2e_harness(
            media_extension=".mp4",
            raised_error="ERROR: [Instagram] DXShON4gKIZ: No video formats found!",
            config_overrides={"shared_cookie_file": str(shared_cookie)},
        )
        harness.enable_gallery_dl_photo_success()

        events = harness.run_download(INSTAGRAM_PHOTO_URL, username="Deeana_zvrn")

        self.assertEqual(events[0]["event"], "reply")
        self.assertEqual(events[0]["text"], "Скачиваю...")
        self.assertEqual(events[-2]["event"], "send_photo")
        self.assertEqual(events[-1]["event"], "delete")

    def test_instagram_photo_end_to_end_retries_public_after_shared_cookie_timeout(self):
        shared_cookie = pathlib.Path(tempfile.mkdtemp()) / "instagram.txt"
        shared_cookie.write_text("cookie-data", encoding="utf-8")
        harness = build_e2e_harness(
            media_extension=".mp4",
            raised_error="ERROR: [Instagram] DXShON4gKIZ: No video formats found!",
            config_overrides={"shared_cookie_file": str(shared_cookie)},
        )
        calls = []

        def fake_run(command, capture_output, text, check, timeout):
            calls.append(command)
            download_dir = pathlib.Path(command[command.index("-D") + 1])
            download_dir.mkdir(parents=True, exist_ok=True)

            if "-C" in command:
                raise subprocess.TimeoutExpired(command, timeout)

            (download_dir / "photo.jpg").write_bytes(b"image")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        harness.module.subprocess.run = fake_run

        events = harness.run_download(INSTAGRAM_PHOTO_URL, username="Deeana_zvrn")

        self.assertEqual(len(calls), 2)
        self.assertIn("-C", calls[0])
        self.assertNotIn("-C", calls[1])
        self.assertEqual(events[-2]["event"], "send_photo")
        self.assertEqual(events[-1]["event"], "delete")

    def test_shared_cookie_upload_is_reserved_for_denzavr(self):
        shared_cookie = pathlib.Path(tempfile.mkdtemp()) / "instagram.txt"
        harness = build_e2e_harness(
            config_overrides={
                "shared_cookie_file": str(shared_cookie),
                "shared_cookie_admin_usernames": ["denzavr"],
            }
        )

        blocked_events = harness.run_shared_cookie_command(username="Deeana_zvrn")
        allowed_events = harness.run_shared_cookie_command(
            username="denzavr",
            cookie_payload=DEFAULT_SHARED_COOKIE_PAYLOAD,
        )

        self.assertEqual(
            blocked_events[0]["text"],
            "Общие cookies может обновлять только @denzavr.",
        )
        self.assertEqual(
            allowed_events[-1]["text"],
            "Общие cookies успешно обновлены. Бот начнет использовать их для новых запросов.",
        )
        self.assertTrue(shared_cookie.exists())

    def test_personal_cookie_command_is_disabled_end_to_end(self):
        harness = build_e2e_harness()

        events = harness.run_personal_cookie_command(username="Deeana_zvrn")

        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["text"],
            "Личные cookies отключены. Бот использует только общие cookies. Обновить их через /sharedcookies может только @denzavr.",
        )


if __name__ == "__main__":
    unittest.main()
