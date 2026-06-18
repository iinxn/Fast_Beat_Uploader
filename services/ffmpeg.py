import json
import math
import os
import re
import subprocess
from typing import Optional

from utils.paths import resource_path


def _hms_to_seconds(h: str, m: str, s: str, cs: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100


def parse_ffmpeg_progress(line: str) -> Optional[float]:
    """Return the current encode position in seconds from an ffmpeg progress line.
    These lines look like: frame=  100 fps= 25 ... time=00:00:04.00 ...
    Returns None if the line has no time info.
    """
    m = re.search(r'\btime=(\d{2}):(\d{2}):(\d{2})\.(\d{2})', line)
    return _hms_to_seconds(*m.groups()) if m else None


def parse_ffmpeg_duration(line: str) -> Optional[float]:
    """Return the total stream duration in seconds from ffmpeg's 'Duration:' header.
    Returns None if the line is not the duration header.
    """
    m = re.search(r'\bDuration:\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2})', line)
    return _hms_to_seconds(*m.groups()) if m else None


def get_ffmpeg_path() -> str:
    local = resource_path(os.path.join("ffmpeg", "ffmpeg.exe"))
    return local if os.path.exists(local) else "ffmpeg"


def get_ffprobe_path() -> str:
    local = resource_path(os.path.join("ffmpeg", "ffprobe.exe"))
    return local if os.path.exists(local) else "ffprobe"


def probe_audio_duration(audio_path: str) -> float:
    """Return the duration of an audio file in seconds using ffprobe."""
    cmd = [
        get_ffprobe_path(),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Не удалось прочитать длительность аудио")
    duration = float(json.loads(result.stdout)["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("Не удалось определить длительность аудио")
    return duration


def build_ffmpeg_command(
    image_path: str,
    audio_path: str,
    output_path: str,
    width: int,
    height: int,
    fps: int,
    video_crf: int,
    video_preset: str,
    audio_bitrate_kbps: int,
    audio_sample_rate: int,
    loop_audio: bool,
    fill_frame: bool = False,
) -> list[str]:
    """Build an ffmpeg command that combines a static image with audio into an MP4.

    fill_frame=False (default, horizontal):
        Image is scaled to fit inside the frame; empty space is padded with black bars.

    fill_frame=True (vertical):
        Image is scaled to fill the entire frame; the parts that don't fit are cropped
        from the center — no black bars, image always covers the full frame.
    """
    duration = probe_audio_duration(audio_path)
    if fill_frame:
        # Scale up so the image covers the whole frame, then crop the center.
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"fps={fps},format=yuv420p"
        )
    else:
        # Scale down to fit inside the frame, pad the remainder with black.
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={fps},format=yuv420p"
        )
    cmd = [
        get_ffmpeg_path(),
        "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
    ]
    if loop_audio:
        cmd += ["-shortest"]
    cmd += [
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", video_preset,
        "-crf", str(video_crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", f"{audio_bitrate_kbps}k",
        "-ar", str(audio_sample_rate),
        "-movflags", "+faststart",
        output_path,
    ]
    return cmd
