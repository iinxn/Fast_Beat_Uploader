import ctypes
import json
import os
import random
import socket
import ssl
import sys
import time
from typing import Callable, Optional

import httplib2
import google_auth_httplib2
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from utils.consts import (
    CATEGORY_OPTIONS,
    DEFAULT_CATEGORY,
    DEFAULT_LANGUAGE,
    LANGUAGE_OPTIONS,
    SCOPES,
    TOKEN_ENTROPY,
    TOKEN_HEADER_ENCRYPTED,
    TOKEN_HEADER_PLAIN,
)
from utils.paths import CLIENT_SECRET_FILE, TOKEN_FILE, resource_path

# ---------------------------------------------------------------------------
# Network behaviour
# ---------------------------------------------------------------------------

# Time (seconds) to wait for a quick "can we even reach YouTube?" probe.
REACHABILITY_TIMEOUT = 8.0
# Time (seconds) before a single network read/write during upload gives up.
UPLOAD_SOCKET_TIMEOUT = 60.0
# Upload chunk size. Smaller chunks survive flaky VPN/proxy tunnels far better:
# each chunk that the server confirms (HTTP 308) is "locked in", so a reset only
# costs the current chunk, not the whole transfer. 1 MB is a good resilience/speed
# trade-off and also gives smooth progress updates.
UPLOAD_CHUNK_SIZE = 1024 * 1024
# How many times to retry a *stuck* upload (no forward progress) before giving up.
MAX_UPLOAD_RETRIES = 5
# HTTP statuses from YouTube that are worth retrying (transient server issues).
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
# Low-level exceptions that mean "network hiccup, try again".
RETRIABLE_EXCEPTIONS = (
    httplib2.HttpLib2Error,
    ssl.SSLError,
    socket.timeout,
    socket.gaierror,
    TimeoutError,
    ConnectionError,
    BrokenPipeError,
    OSError,
)

# Routes to try, in order, until one gets the upload through.
# Background: some ISPs (esp. with DPI) block "youtube.googleapis.com" by SNI
# while the older "www.googleapis.com" front-end stays reachable. The YouTube
# Data API is served on both hosts, so we prefer www.googleapis.com and only
# fall back to the canonical host. We also try direct first (a flaky/duplicated
# VPN-proxy can corrupt the TLS stream), then via the system proxy/VPN.
#   (human label, api_endpoint or None for default, use_system_proxy)
UPLOAD_STRATEGIES = [
    ("www.googleapis.com напрямую", "https://www.googleapis.com/", False),
    ("www.googleapis.com через прокси/VPN", "https://www.googleapis.com/", True),
    ("youtube.googleapis.com через прокси/VPN", None, True),
]


class _StrategyFailed(Exception):
    """A single endpoint/proxy route could not get the upload through.

    Carries the underlying network error as ``__cause__`` so the caller can try
    the next route and, if all fail, report the real reason.
    """


def resolve_client_secret() -> str:
    """Find client_secret.json, preferring a copy next to the program.

    Looks next to the .exe first (so the user can swap credentials without a
    rebuild), then falls back to a copy bundled inside the executable.
    """
    if os.path.exists(CLIENT_SECRET_FILE):
        return CLIENT_SECRET_FILE
    bundled = resource_path("client_secret.json")
    if os.path.exists(bundled):
        return bundled
    raise FileNotFoundError(
        "Файл client_secret.json не найден.\n"
        "Положи его в ту же папку, что и программа (рядом с .exe), и попробуй снова."
    )


def check_youtube_reachable(timeout: float = REACHABILITY_TIMEOUT) -> None:
    """Raise a clear, human-readable error if the YouTube API host is unreachable.

    This runs *before* the upload so the user gets an instant, understandable
    message ("нет интернета") instead of a long hang followed by a cryptic
    socket traceback.
    """
    try:
        with socket.create_connection(("www.googleapis.com", 443), timeout=timeout):
            return
    except socket.gaierror:
        raise ConnectionError(
            "Не удаётся найти серверы YouTube (ошибка DNS).\n"
            "Скорее всего нет интернета. Проверь подключение и попробуй снова."
        )
    except (socket.timeout, TimeoutError):
        raise ConnectionError(
            "YouTube не отвечает: превышено время ожидания.\n"
            "Возможно, очень медленный интернет или соединение блокируется. Попробуй позже."
        )
    except OSError as e:
        raise ConnectionError(
            f"Не удалось подключиться к YouTube: {e}.\nПроверь интернет-соединение."
        )


def friendly_upload_error(exc: Exception) -> str:
    """Translate a low-level exception into a clear Russian message for the user."""
    if isinstance(exc, _StrategyFailed):
        exc = exc.__cause__ or exc
    if isinstance(exc, RefreshError):
        return (
            "Не удалось обновить вход Google (возможно, доступ отозван или истёк).\n"
            "Сбрось сохранённый вход и авторизуйся заново."
        )
    if isinstance(exc, HttpError):
        status = getattr(exc.resp, "status", None)
        if status in (401, 403):
            return (
                f"YouTube отклонил запрос (код {status}).\n"
                "Проверь, что для проекта включён YouTube Data API v3 и не исчерпана дневная квота."
            )
        if status == 400:
            return f"YouTube не принял данные видео (код 400). Проверь название, дату и теги.\n{exc}"
        return f"YouTube вернул ошибку {status}.\n{exc}"
    if isinstance(exc, ssl.SSLError) and "BAD_RECORD_MAC" in str(exc).upper():
        return (
            "VPN/прокси повреждает соединение с YouTube (ошибка шифрования TLS).\n"
            "Похоже, запущено несколько VPN-клиентов сразу. Оставь только один — "
            "или отключи VPN полностью: YouTube часто доступен напрямую."
        )
    if isinstance(exc, socket.gaierror):
        return "Не удаётся найти серверы YouTube (DNS). Проверь интернет-соединение."
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "YouTube не отвечает: превышено время ожидания. Попробуй позже."
    if isinstance(exc, (TransportError, ConnectionError, httplib2.HttpLib2Error, ssl.SSLError, OSError)):
        return f"Проблема с соединением при работе с YouTube:\n{exc}\nПроверь интернет и попробуй снова."
    return str(exc)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class TokenStorage:
    """Stores and loads YouTube OAuth credentials.

    On Windows the token is encrypted with DPAPI (user-scoped).
    On other platforms it is stored as plain JSON with a magic header.
    """

    def __init__(self, path: str = TOKEN_FILE):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    # ------------------------------------------------------------------
    # DPAPI helpers (Windows only)
    # ------------------------------------------------------------------

    @staticmethod
    def _dpapi_available() -> bool:
        return sys.platform.startswith("win") and hasattr(ctypes, "windll")

    @staticmethod
    def _make_blob(data: bytes) -> _DataBlob:
        buf = ctypes.create_string_buffer(data)
        blob = _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
        blob._buffer = buf  # type: ignore[attr-defined]
        return blob

    @classmethod
    def _encrypt(cls, data: bytes) -> bytes:
        in_blob = cls._make_blob(data)
        entropy = cls._make_blob(TOKEN_ENTROPY)
        out = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, ctypes.byref(entropy), None, None, 0x01, ctypes.byref(out)):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32.LocalFree(out.pbData)

    @classmethod
    def _decrypt(cls, data: bytes) -> bytes:
        in_blob = cls._make_blob(data)
        entropy = cls._make_blob(TOKEN_ENTROPY)
        out = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, ctypes.byref(entropy), None, None, 0, ctypes.byref(out)):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32.LocalFree(out.pbData)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_credentials(self) -> Optional[Credentials]:
        legacy_path = os.path.join(os.path.dirname(self.path), "token.json")

        if os.path.exists(self.path):
            raw = self._read_raw(self.path)
            if raw is None:
                return None
            return Credentials.from_authorized_user_info(json.loads(raw.decode()), SCOPES)

        # Fall back to the old plain token.json from previous versions
        if os.path.exists(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    return Credentials.from_authorized_user_info(json.load(f), SCOPES)
            except Exception:
                return None

        return None

    def save_credentials(self, creds: Credentials) -> None:
        raw = creds.to_json().encode()
        if self._dpapi_available():
            payload = TOKEN_HEADER_ENCRYPTED + self._encrypt(raw)
        else:
            payload = TOKEN_HEADER_PLAIN + raw
        with open(self.path, "wb") as f:
            f.write(payload)

    def _read_raw(self, path: str) -> Optional[bytes]:
        try:
            with open(path, "rb") as f:
                data = f.read()
            if data.startswith(TOKEN_HEADER_ENCRYPTED):
                return self._decrypt(data[len(TOKEN_HEADER_ENCRYPTED):])
            if data.startswith(TOKEN_HEADER_PLAIN):
                return data[len(TOKEN_HEADER_PLAIN):]
            return data
        except Exception:
            return None

    def clear(self) -> bool:
        """Delete the saved token (current + legacy). Returns True if anything was removed."""
        removed = False
        legacy_path = os.path.join(os.path.dirname(self.path), "token.json")
        for path in (self.path, legacy_path):
            if os.path.exists(path):
                try:
                    os.remove(path)
                    removed = True
                except OSError:
                    pass
        return removed


class YoutubeService:
    """High-level wrapper around the YouTube Data API v3."""

    def __init__(self, token_storage: Optional[TokenStorage] = None):
        self.token_storage = token_storage or TokenStorage()

    def authenticate(self, log: Optional[Callable[[str], None]] = None) -> Credentials:
        def _log(msg: str) -> None:
            if log:
                try:
                    log(msg)
                except Exception:
                    pass

        creds = self.token_storage.load_credentials()
        _log("Найден сохранённый токен" if creds else "Сохранённый токен не найден")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                _log("Токен устарел, обновляю...")
                try:
                    creds.refresh(Request())
                except (TransportError, ConnectionError, socket.error) as e:
                    raise ConnectionError(
                        "Не удалось обновить вход Google: нет связи с серверами Google.\n"
                        f"Проверь интернет и попробуй снова. ({e})"
                    )
                _log("Токен обновлён")
            else:
                _log("Открываю окно входа Google...")
                client_secret_path = resolve_client_secret()
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
                creds = flow.run_local_server(port=0)
                _log("Авторизация завершена")
            self.token_storage.save_credentials(creds)
            _log("Токен сохранён в защищённом хранилище")

        return creds

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        publish_at_rfc3339: str,
        category_id: str = CATEGORY_OPTIONS[DEFAULT_CATEGORY],
        language_code: str = LANGUAGE_OPTIONS[DEFAULT_LANGUAGE],
        log: Optional[Callable[[str], None]] = None,
    ) -> dict:
        def _log(msg: str) -> None:
            if log:
                try:
                    log(msg)
                except Exception:
                    pass

        # Don't let a dropped connection hang a socket read forever.
        socket.setdefaulttimeout(UPLOAD_SOCKET_TIMEOUT)

        try:
            _log("Создаю сервис YouTube...")
            creds = self.authenticate(log=_log)

            body = {
                "snippet": {
                    "title": title or "Без названия",
                    "description": description or "",
                    "categoryId": category_id,
                    "defaultLanguage": language_code,
                    "defaultAudioLanguage": language_code,
                    **({"tags": tags} if tags else {}),
                },
                "status": {
                    "privacyStatus": "private",
                    "publishAt": publish_at_rfc3339,
                    "selfDeclaredMadeForKids": False,
                },
            }

            # Try each route (host + proxy mode) until one gets the file through.
            last_error: Optional[Exception] = None
            for label, endpoint, use_proxy in UPLOAD_STRATEGIES:
                try:
                    _log(f"Маршрут: {label}")
                    youtube = self._make_service(creds, endpoint, use_proxy)
                    request = youtube.videos().insert(
                        part="snippet,status",
                        body=body,
                        media_body=MediaFileUpload(video_path, resumable=True, chunksize=UPLOAD_CHUNK_SIZE),
                    )
                    _log("Начинаю передачу файла на YouTube...")
                    response = self._upload_with_retries(request, _log)
                    _log("Загрузка завершена")
                    return response
                except HttpError as e:
                    if getattr(e.resp, "status", None) not in RETRIABLE_STATUS_CODES:
                        raise  # permanent (auth/quota/bad request) — other routes won't help
                    last_error = e
                    _log(f"Маршрут не сработал (сервер: {getattr(e.resp, 'status', '?')}). Пробую другой...")
                except _StrategyFailed as e:
                    last_error = e.__cause__ or e
                    _log(f"Маршрут не сработал: {last_error}. Пробую другой...")

            raise last_error or RuntimeError("Не удалось связаться с YouTube ни одним маршрутом.")

        except Exception as e:
            # Log the raw error for debugging, but raise a clear message for the UI.
            _log(f"Техническая ошибка: {e!r}")
            raise RuntimeError(friendly_upload_error(e)) from e

    def _make_service(self, creds, endpoint: Optional[str], use_proxy: bool):
        """Build a YouTube service bound to a specific host + proxy mode.

        endpoint=None    -> canonical host from the discovery doc (youtube.googleapis.com)
        endpoint=URL     -> override host (e.g. https://www.googleapis.com/)
        use_proxy=False  -> ignore the system/env proxy and connect directly
        use_proxy=True   -> honour HTTP(S)_PROXY / system proxy

        A custom http object is used so we can control the proxy per attempt;
        cache_discovery=False + static_discovery=True avoid any network discovery.
        """
        proxy_info = httplib2.proxy_info_from_environment if use_proxy else None
        base_http = httplib2.Http(timeout=UPLOAD_SOCKET_TIMEOUT, proxy_info=proxy_info)
        # CRITICAL for resumable uploads: a resumable PUT returns HTTP 308
        # ("Resume Incomplete") with a Range but NO Location header. httplib2
        # >=0.20 treats 308 as a redirect and would raise
        # "Redirected but the response is missing a Location: header." googleapiclient
        # interprets 308 itself (it manages the resumable session URI), so we must
        # stop httplib2 from intercepting these responses.
        base_http.follow_redirects = False
        authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=base_http)
        client_options = {"api_endpoint": endpoint} if endpoint else None
        return build(
            "youtube", "v3",
            http=authed_http,
            cache_discovery=False,
            static_discovery=True,
            client_options=client_options,
        )

    def _upload_with_retries(self, request, log: Callable[[str], None]) -> dict:
        """Run the resumable upload, retrying transient network/server failures.

        A flaky connection that drops mid-upload is retried with exponential
        backoff instead of failing the whole upload. Crucially, the retry budget
        resets whenever the upload makes *any* forward progress — so an unstable
        tunnel (e.g. a VPN/proxy that resets the connection every few MB) can
        still finish the file by inching through it, because the resumable
        protocol continues from the last byte the server confirmed.

        Permanent errors (bad request, auth) are re-raised immediately.
        """
        response = None
        last_pct = -1
        retries = 0
        last_sent = 0  # bytes the server has confirmed so far
        while response is None:
            try:
                status, response = request.next_chunk()
                retries = 0  # a successful chunk resets the retry budget
                if status:
                    pct = int(status.progress() * 100)
                    if pct != last_pct:
                        last_pct = pct
                        log(f"Загрузка: {pct}%")
            except HttpError as e:
                if getattr(e.resp, "status", None) not in RETRIABLE_STATUS_CODES:
                    raise  # permanent API error — don't retry
                retries = self._next_retry(request, last_sent, retries, e, f"сервер YouTube занят ({e.resp.status})", log)
                last_sent = getattr(request, "resumable_progress", last_sent)
            except RETRIABLE_EXCEPTIONS as e:
                retries = self._next_retry(request, last_sent, retries, e, f"обрыв связи ({e})", log)
                last_sent = getattr(request, "resumable_progress", last_sent)
        return response

    def _next_retry(self, request, last_sent: int, retries: int, exc: Exception,
                    reason: str, log: Callable[[str], None]) -> int:
        """Decide whether to keep retrying this route, and sleep with backoff.

        If the upload advanced since the previous failure, the budget is reset
        (we're making progress despite the flaky link). Returns the new retry
        count, or raises ``_StrategyFailed`` once a *stuck* upload exhausts the
        budget — which tells the caller to try the next route.
        """
        progressed = getattr(request, "resumable_progress", 0) > last_sent
        retries = 1 if progressed else retries + 1
        if retries > MAX_UPLOAD_RETRIES:
            raise _StrategyFailed(reason) from exc
        self._backoff(retries, reason, log)
        return retries

    @staticmethod
    def _backoff(attempt: int, reason: str, log: Callable[[str], None]) -> None:
        """Sleep with exponential backoff + jitter between upload retries."""
        delay = min(2 ** attempt + random.random(), 30.0)
        log(f"Сбой передачи: {reason}. Повтор {attempt}/{MAX_UPLOAD_RETRIES} через {delay:.0f} с...")
        time.sleep(delay)
