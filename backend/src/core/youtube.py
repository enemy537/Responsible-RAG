"""YouTube audio download and transcription pipeline."""

import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path

import ffmpeg

from src.core.cloudflare import Cloudflare
from src.core.transcriber import transcribe

logger = logging.getLogger(__name__)

# ── pytubefix helpers with PoToken support ───────────────────────────────────
# YouTube has been aggressively blocking server-side requests.  pytubefix
# supports PoToken (Proof of Origin Token) to bypass bot detection.
# We try several strategies in order:
#   1. pytubefix with use_po_token=True (auto-generates token via nodejs)
#   2. pytubefix with WEB client (alternative PoToken client)
#   3.  yt-dlp as a robust fallback


def _try_pytubefix_download(
    url: str, output_dir: str | Path,
) -> str | None:
    """
    Attempt to download audio via pytubefix with PoToken strategies.

    Returns the path to the downloaded file, or ``None`` if all attempts fail.
    """
    import pytubefix

    strategies = [
        ("pytubefix use_po_token=True", {"use_po_token": True}),
        ("pytubefix client=WEB", {"client": "WEB"}),
    ]

    for label, kwargs in strategies:
        try:
            logger.info("Trying %s for %s", label, url)
            yt = pytubefix.YouTube(url, **kwargs)
            stream = yt.streams.filter(only_audio=True).first()
            if not stream:
                logger.warning("%s: no audio stream found", label)
                continue

            temp_dir = tempfile.mkdtemp()
            try:
                out_path = os.path.join(str(output_dir), f"{yt.video_id}.wav")
                downloaded = stream.download(output_path=temp_dir)
                ffmpeg.input(downloaded).output(
                    out_path,
                    format="wav",
                    acodec="pcm_s16le",
                    ar="16000",
                    ac=1,
                    loglevel="error",
                ).run(overwrite_output=True)
                logger.info("%s succeeded for %s", label, url)
                return out_path
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as exc:
            logger.warning("%s failed for %s: %s", label, url, exc)
            continue

    return None


def _try_ytdlp_download(url: str, output_dir: str | Path) -> str | None:
    """
    Fallback: download audio via yt-dlp.

    yt-dlp is more resilient to bot detection but slower.  Returns the
    path to the downloaded WAV file, or ``None`` on failure.
    """
    import yt_dlp

    temp_dir = tempfile.mkdtemp()
    try:
        out_template = os.path.join(temp_dir, "%(id)s.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "unknown")
            downloaded = os.path.join(temp_dir, f"{video_id}.webm")
            if not os.path.exists(downloaded):
                # yt-dlp may use different extensions; find any file in temp_dir
                files = os.listdir(temp_dir)
                audio_file = next(
                    (os.path.join(temp_dir, f) for f in files if os.path.isfile(os.path.join(temp_dir, f))),
                    None,
                )
                if not audio_file:
                    logger.warning("yt-dlp: no audio file found for %s", url)
                    return None
                downloaded = audio_file

            out_path = os.path.join(str(output_dir), f"{video_id}.wav")
            ffmpeg.input(downloaded).output(
                out_path,
                format="wav",
                acodec="pcm_s16le",
                ar="16000",
                ac=1,
                loglevel="error",
            ).run(overwrite_output=True)
            logger.info("yt-dlp succeeded for %s", url)
            return out_path

    except Exception as exc:
        logger.warning("yt-dlp failed for %s: %s", url, exc)
        return None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── Public API ───────────────────────────────────────────────────────────────


def extract_audio(url: str, output_dir: str | Path) -> str:
    """
    Download audio from a YouTube URL and convert to 16 kHz mono WAV.

    Tries pytubefix (with PoToken) first, then falls back to yt-dlp.

    Returns
    -------
    str
        Path to the downloaded WAV file.

    Raises
    ------
    ValueError
        If all download strategies fail.
    """
    out_path = _try_pytubefix_download(url, output_dir)
    if out_path:
        return out_path

    logger.info("pytubefix strategies exhausted — falling back to yt-dlp for %s", url)
    out_path = _try_ytdlp_download(url, output_dir)
    if out_path:
        return out_path

    raise ValueError(
        f"Could not download audio from {url}. "
        f"All download strategies (pytubefix PoToken, yt-dlp) failed."
    )


def transcribe_youtube(url: str, cf: Cloudflare | None = None) -> str:
    temp_dir = tempfile.mkdtemp()
    try:
        wav = extract_audio(url, temp_dir)
        return transcribe(wav, cf)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def transcribe_youtube_async(url: str, cf: Cloudflare | None = None) -> str:
    """Async variant — runs the full download+transcribe pipeline in a thread pool."""
    return await asyncio.to_thread(transcribe_youtube, url, cf)
