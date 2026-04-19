# The telegram bot token
token: str = "123456789:ABcdefGhiJKlmnO"

# The logs channel id, if none set to None
logs: int | None = None

# The maximum file size in bytes
max_filesize: int = 50000000

# The output folder for downloaded files, it gets cleared after each download
output_folder: str = "/tmp/satoru"

# The allowed domains for downloading videos
allowed_domains: list[str] = [
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com",
    "youtube-nocookie.com",
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "bsky.app",
    "www.bsky.app",
]

# secret key used to encrypt/decrypt stores cookies
secret_key: str = "your-secret-key"

# optional allowlist for a private bot; leave empty to allow everyone
allowed_usernames: list[str] = []

# optional shared cookie file for all allowed users, useful for Instagram auth
shared_cookie_file: str | None = None

# optional gallery-dl binary path for Instagram image fallback
gallery_dl_binary: str = "gallery-dl"

# this is used to solve youtube challenges, you can set it to None if you don't
# need it or change the runtime like {"node": {"path": "node"}}
js_runtime: dict[str, dict[str, str] | None] | None = {"bun": {"path": "bun"}}
