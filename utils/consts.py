"""Static configuration values for the app (no I/O, no path computation).

File and folder locations live in :mod:`utils.paths`.
"""

APP_TITLE = "Fast Beats Render"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

HORIZONTAL_PRESETS = {
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4K": (3840, 2160),
}

VERTICAL_PRESETS = {
    "480p": (480, 854),
    "720p": (720, 1280),
    "1080p": (1080, 1920),
    "1440p": (1440, 2560),
    "4K": (2160, 3840),
}

AUDIO_BITRATE_OPTIONS = ["96", "128", "160", "192", "256", "320"]
AUDIO_SAMPLE_RATE_OPTIONS = ["22050", "44100", "48000", "96000"]
VIDEO_PRESET_OPTIONS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"]

LANGUAGE_OPTIONS = {
    "Русский": "ru",
    "English": "en",
}

CATEGORY_OPTIONS = {
    "Музыка": "10",
    "Игры": "20",
    "Развлечения": "24",
    "Образование": "27",
    "Люди и блоги": "22",
    "Хобби и стиль": "26",
}

DEFAULT_LANGUAGE = "Русский"
DEFAULT_CATEGORY = "Музыка"

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".avif"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus", ".wma"})

TOKEN_HEADER_ENCRYPTED = b"FBR1"
TOKEN_HEADER_PLAIN = b"FBR0"
TOKEN_ENTROPY = b"FastBeatsRender:token:v1"
