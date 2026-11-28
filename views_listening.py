"""
views_listening.py: Ninja Listening Trainer (YouTube & Local Audio) module for NinjaPhonetics
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request
import uuid
import streamlit as st
import streamlit.components.v1 as components
from youtube_transcript_api import YouTubeTranscriptApi
from ui_styles import _ICE_SHURIKEN_B64, get_ice_shuriken_img_tag

TRANSCRIPT_CACHE_DIR = Path.home() / ".ninja_listening_transcripts"


def load_cached_transcript(video_id: str) -> list[dict] | None:
    try:
        p = TRANSCRIPT_CACHE_DIR / f"{video_id}.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
    except Exception:
        pass
    return None


def save_cached_transcript(video_id: str, captions: list[dict]) -> None:
    if not video_id or not captions:
        return
    try:
        TRANSCRIPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p = TRANSCRIPT_CACHE_DIR / f"{video_id}.json"
        p.write_text(json.dumps(captions, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    return None


def merge_into_sentences(raw_items: list[dict]) -> list[dict]:
    """Merge fragmented captions into cleaner sentence/clause lines."""
    if not raw_items:
        return []

    has_punctuation = any(re.search(r"[.?!]$", item["text"]) for item in raw_items[:30])
    merged = []
    buf_text = []
    buf_start = raw_items[0]["start"]
    buf_end = raw_items[0]["end"]

    for i, item in enumerate(raw_items):
        text = item["text"]
        if not buf_text:
            buf_start = item["start"]
        buf_text.append(text)
        buf_end = item["end"]

        joined = " ".join(buf_text)
        next_gap = (raw_items[i + 1]["start"] - buf_end) if i + 1 < len(raw_items) else 999.0

        if has_punctuation:
            should_flush = bool(re.search(r"[.?!][\"')\]]*$", text)) or len(joined) > 140 or next_gap > 1.5
        else:
            should_flush = next_gap > 0.65 or len(joined) >= 75

        if should_flush or i == len(raw_items) - 1:
            merged.append({
                "start": buf_start,
                "duration": max(0.2, buf_end - buf_start),
                "end": buf_end,
                "text": joined,
            })
            buf_text = []

    return merged


def parse_srt_text(srt_content: str) -> list[dict]:
    """Parse .srt subtitle content into Ninja Listening caption dicts."""
    blocks = re.split(r"\r?\n\r?\n+", srt_content.strip())
    items = []
    ts_pat = re.compile(
        r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})"
    )
    for blk in blocks:
        lines = [ln.strip() for ln in blk.splitlines() if ln.strip()]
        if not lines:
            continue
        ts_idx = next((i for i, ln in enumerate(lines) if ts_pat.search(ln)), -1)
        if ts_idx == -1:
            continue
        m = ts_pat.search(lines[ts_idx])
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
        text_lines = [re.sub(r"<[^>]+>", "", ln) for ln in lines[ts_idx + 1 :]]
        txt = " ".join(text_lines).strip()
        if txt:
            items.append({
                "start": start,
                "duration": max(0.2, end - start),
                "end": max(start + 0.2, end),
                "text": txt,
            })
    return items


def _detect_audio_mime(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }.get(ext, "audio/mpeg")


def _get_secret_or_env(name: str) -> str:
    try:
        val = str(st.secrets.get(name, "")).strip()
        if val:
            return val
    except Exception:
        pass
    return os.getenv(name, "").strip()


def _post_whisper_api(endpoint: str, api_key: str, model: str, audio_bytes: bytes, filename: str) -> list[dict]:
    boundary = f"----NinjaBoundary{uuid.uuid4().hex}"
    mime = _detect_audio_mime(filename)
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n".encode("utf-8"),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\nverbose_json\r\n".encode("utf-8"),
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        + audio_bytes
        + b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    body = b"".join(parts)
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "NinjaPhonetics/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    raw_items = []
    for seg in data.get("segments", []):
        start = float(seg.get("start", 0.0))
        end = max(start + 0.2, float(seg.get("end", start + 1.0)))
        txt = str(seg.get("text", "")).strip()
        if txt:
            raw_items.append({
                "start": start,
                "duration": max(0.2, end - start),
                "end": end,
                "text": txt,
            })
    if not raw_items and data.get("text"):
        raw_items.append({
            "start": 0.0,
            "duration": 5.0,
            "end": 5.0,
            "text": str(data["text"]).strip(),
        })
    return merge_into_sentences(raw_items)


def _is_local_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def get_available_whisper_backend() -> tuple[str, str]:
    """Return (backend_id, human_label) in priority order."""
    if _get_secret_or_env("GROQ_API_KEY"):
        return ("groq", "Groq Whisper API (whisper-large-v3-turbo)")
    if _get_secret_or_env("OPENAI_API_KEY"):
        return ("openai", "OpenAI Whisper API (whisper-1)")
    if _is_local_whisper_available():
        return ("local", "Local Whisper (base.en)")
    return ("", "")


def transcribe_audio_hybrid(audio_bytes: bytes, filename: str) -> tuple[list[dict], str]:
    """Transcribe uploaded audio via Groq -> OpenAI -> local faster-whisper/whisper."""
    groq_key = _get_secret_or_env("GROQ_API_KEY")
    if groq_key:
        caps = _post_whisper_api(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            groq_key,
            "whisper-large-v3-turbo",
            audio_bytes,
            filename,
        )
        return caps, "Groq Whisper"

    openai_key = _get_secret_or_env("OPENAI_API_KEY")
    if openai_key:
        caps = _post_whisper_api(
            "https://api.openai.com/v1/audio/transcriptions",
            openai_key,
            "whisper-1",
            audio_bytes,
            filename,
        )
        return caps, "OpenAI Whisper"

    suffix = Path(filename).suffix.lower() or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        from math import gcd
        import numpy as np
        from scipy.signal import resample_poly
        from faster_whisper import WhisperModel
        from audio_processing import decode_audio_bytes

        wav_arr, sr = decode_audio_bytes(audio_bytes)
        wav_1d = np.asarray(wav_arr, dtype=np.float32)
        if wav_1d.ndim > 1:
            wav_1d = wav_1d.mean(axis=1)
        if sr != 16000:
            g = gcd(int(sr), 16000)
            wav_1d = resample_poly(wav_1d, 16000 // g, int(sr) // g).astype(np.float32)

        model = WhisperModel("base.en", device="auto", compute_type="int8")
        segments, _ = model.transcribe(wav_1d, beam_size=5)
        raw_items = [
            {
                "start": float(seg.start),
                "duration": max(0.2, float(seg.end - seg.start)),
                "end": float(seg.end),
                "text": seg.text.strip(),
            }
            for seg in segments
            if seg.text.strip()
        ]
        return merge_into_sentences(raw_items), "Local faster-whisper"
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

def _fetch_via_supadata(video_id: str, lang: str = "en") -> list[dict]:
    api_key = _get_secret_or_env("SUPADATA_API_KEY")
    if not api_key:
        raise RuntimeError("SUPADATA_API_KEY not configured")

    req = urllib.request.Request(
        f"https://api.supadata.ai/v1/youtube/transcript?videoId={video_id}&lang={lang}",
        headers={
            "x-api-key": api_key,
            "User-Agent": "NinjaPhonetics/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data.get("content", [])
    if not content:
        raise RuntimeError("No transcript content returned by Supadata")

    items = []
    for seg in content:
        start = float(seg.get("offset", 0)) / 1000.0
        dur = max(0.2, float(seg.get("duration", 1000)) / 1000.0)
        txt = str(seg.get("text", "")).replace("\n", " ").strip()
        if txt:
            items.append({
                "start": start,
                "duration": dur,
                "end": start + dur,
                "text": txt,
            })
    return merge_into_sentences(items)


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_transcript(video_id: str, languages: tuple = ("en", "en-US", "en-GB")) -> list[dict]:
    try:
        return _fetch_via_supadata(video_id, languages[0])
    except Exception:
        pass

    if hasattr(YouTubeTranscriptApi, "fetch") or not hasattr(YouTubeTranscriptApi, "get_transcript"):
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=list(languages))
        items = [
            {
                "start": float(item.start),
                "duration": float(item.duration),
                "end": float(item.start + item.duration),
                "text": item.text.replace("\n", " ").strip(),
            }
            for item in fetched
        ]
    else:
        raw = YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
        items = [
            {
                "start": float(item["start"]),
                "duration": float(item["duration"]),
                "end": float(item["start"] + item["duration"]),
                "text": item["text"].replace("\n", " ").strip(),
            }
            for item in raw
        ]
    return merge_into_sentences(items)

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<style>
  :root {
    --bg: #0f172a;
    --panel: #0b1120;
    --card: #1e293b;
    --accent: #2ba2bd;
    --primary-blue: #2563eb;
    --neon-magenta: #ff00cc;
    --neon-cyan: #00d2ff;
    --start-color: #10b981;
    --end-color: #f59e0b;
    --yt-red: #ff0000;
    --danger: #ef4444;
    --text: #e2e8f0;
    --muted: #64748b;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", Arial, sans-serif;
    overflow: hidden;
  }

  .app-shell {
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100%;
    overflow: hidden;
  }

  .stage-banner {
    background: #1e293b;
    border-bottom: 1px solid #334155;
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
    padding: 6px 12px;
    text-align: center;
    letter-spacing: 0.01em;
    flex-shrink: 0;
  }
  .stage-banner.hidden {
    display: none;
  }

  .video-section {
    background: #020617;
    flex-shrink: 0;
  }
  .player-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    max-height: 205px;
    background: #000;
  }
  .player-wrap iframe {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }
  /* Local Audio Horizontal Scrub Bar */
  .player-wrap.local-mode {
    aspect-ratio: auto;
    max-height: none;
    padding: 12px 14px 10px;
    background: linear-gradient(180deg, #0b1120 0%, #060b16 100%);
    border-bottom: 1px solid #1e293b;
  }
  .local-audio-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
  }
  .local-audio-title {
    font-size: 12.5px;
    font-weight: 700;
    color: #bae6fd;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  .local-audio-badge {
    font-size: 10px;
    font-weight: 700;
    color: #38bdf8;
    background: rgba(56, 189, 248, 0.14);
    border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 999px;
    padding: 1px 7px;
    flex-shrink: 0;
  }
  .local-scrub-track {
    position: relative;
    width: 100%;
    height: 14px;
    background: #1e293b;
    border-radius: 999px;
    cursor: pointer;
    touch-action: none;
  }
  .local-scrub-range {
    position: absolute;
    top: 0;
    bottom: 0;
    background: rgba(16, 185, 129, 0.28);
    border-left: 2px solid #10b981;
    border-right: 2px solid #f59e0b;
    pointer-events: none;
    display: none;
  }
  .local-scrub-fill {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 0%;
    background: linear-gradient(90deg, #0284c7, #38bdf8);
    border-radius: 999px;
    pointer-events: none;
  }
  .local-scrub-thumb {
    position: absolute;
    top: 50%;
    left: 0%;
    width: 16px;
    height: 16px;
    transform: translate(-50%, -50%);
    background: #f8fafc;
    border: 2.5px solid #38bdf8;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(56, 189, 248, 0.65);
    pointer-events: none;
  }
  .local-scrub-ticks {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 7px;
    font-size: 11px;
    color: #94a3b8;
    font-variant-numeric: tabular-nums;
  }
  .yt-play-btn.local-play-btn {
    background: #0284c7;
  }
  .no-captions-notice {
    padding: 28px 16px;
    text-align: center;
    color: #94a3b8;
    font-size: 13px;
    line-height: 1.65;
  }
  .meta-bar {
    display: flex;
    flex-direction: column;
    padding: 4px 8px;
    background: var(--panel);
    border-bottom: 1px solid #1e293b;
    font-size: 11px;
    flex-shrink: 0;
    gap: 5px;
  }
  .meta-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    min-height: 26px;
  }
  .meta-left-controls,
  .meta-right-controls {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .url-toggle-btn {
    background: var(--card);
    color: #cbd5e1;
    border: 1px solid #334155;
    border-radius: 5px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    line-height: 1.2;
    letter-spacing: 0.02em;
  }
  .url-toggle-btn:hover,
  .url-toggle-btn.active {
    color: #ffffff;
    border-color: #64748b;
  }
  .yt-play-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 22px;
    background: var(--yt-red);
    color: #ffffff;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.45);
    transition: transform 0.08s, filter 0.14s;
  }
  .yt-play-btn:hover { filter: brightness(1.08); }
  .yt-play-btn:active { transform: scale(0.94); }
  .yt-play-btn svg {
    width: 13px;
    height: 13px;
    fill: #ffffff;
    display: block;
  }
  .time-display {
    color: #94a3b8;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .link-icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 24px;
    border-radius: 5px;
    cursor: pointer;
    transition: transform 0.08s, background 0.14s;
  }
  .link-icon-btn svg {
    width: 14px;
    height: 14px;
    fill: none;
    stroke: currentColor;
    stroke-width: 2.2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .link-icon-btn.sync-link {
    background: #10b981;
    color: #020617;
    border: none;
    box-shadow: 0 1px 6px rgba(16, 185, 129, 0.38);
  }
  .link-icon-btn.sync-link:hover { background: #34d399; }
  .link-icon-btn.unsync-unlink {
    background: rgba(251, 191, 36, 0.14);
    color: #fbbf24;
    border: 1px solid rgba(251, 191, 36, 0.4);
  }
  .link-icon-btn.unsync-unlink:hover { background: rgba(251, 191, 36, 0.24); }
  .link-icon-btn:active { transform: scale(0.94); }

  .offset-toggle-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(30, 41, 59, 0.85);
    border: 1px solid #334155;
    border-radius: 5px;
    padding: 2px 7px;
    cursor: pointer;
    transition: border-color 0.14s, background 0.14s;
  }
  .offset-toggle-pill:hover,
  .offset-toggle-pill.open {
    border-color: #38bdf8;
    background: rgba(56, 189, 248, 0.12);
  }
  .offset-badge {
    color: #e2e8f0;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    font-size: 11px;
  }
  .saved-tag {
    font-size: 9.5px;
    color: #34d399;
    background: rgba(16, 185, 129, 0.16);
    border-radius: 3px;
    padding: 0 4px;
    font-weight: 700;
  }

  .sync-nudge-drawer {
    display: none;
    flex-direction: column;
    gap: 4px;
    padding-top: 3px;
    border-top: 1px solid #1e293b;
  }
  .sync-nudge-drawer.open {
    display: flex;
  }
  .nudge-labels-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 10.5px;
    color: #cbd5e1;
    font-weight: 600;
    padding: 0 2px;
  }
  .nudge-buttons-row {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 3px;
  }
  .nudge-btn {
    background: var(--card);
    color: var(--text);
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 3px 0;
    font-size: 10.5px;
    text-align: center;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
  }
  .nudge-btn:active {
    background: var(--accent);
    color: #fff;
  }

  .app-shell.sequence-running .sync-nudge-drawer,
  .app-shell.sequence-running .unsync-unlink,
  .app-shell.sequence-running .saved-tag,
  .app-shell.sequence-running .url-toggle-btn,
  .app-shell.sequence-running .range-row {
    display: none !important;
  }
  .app-shell.sequence-running .protocol-select,
  .app-shell.sequence-running .run-btn,
  .app-shell.sequence-running .cfg-btn {
    opacity: 0.24;
    pointer-events: none;
  }

  .transcript-area {
    flex: 1.25;
    overflow-y: auto;
    padding: 6px 8px;
    scroll-behavior: smooth;
    position: relative;
    border-bottom: 1px solid #1e293b;
    min-height: 0;
    background: #0b1120;
    display: flex;
    flex-direction: column;
  }
  .caption-list {
    width: 100%;
  }
  .caption-line {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    padding: 6px 9px;
    margin: 0;
    background: transparent;
    border-bottom: 1px solid rgba(148, 163, 184, 0.07);
    border-left: 2px solid transparent;
    border-right: 2px solid transparent;
    font-size: 14px;
    line-height: 1.45;
    cursor: pointer;
    transition: background 0.14s, opacity 0.16s;
  }
  .caption-line:last-child {
    border-bottom: none;
  }

  .caption-line.preview-active {
    background: rgba(43, 162, 189, 0.11);
    box-shadow: inset 2px 0 0 rgba(43, 162, 189, 0.7);
    color: #f8fafc;
  }

  .transcript-area:not(.training-active) .caption-line.in-range {
    background: rgba(148, 163, 184, 0.08);
    border-left: 1.5px solid rgba(148, 163, 184, 0.42);
    border-right: 1.5px solid rgba(148, 163, 184, 0.42);
    border-bottom-color: transparent;
  }
  .transcript-area:not(.training-active) .caption-line:not(.in-range) + .caption-line.in-range,
  .transcript-area:not(.training-active) .caption-line.in-range:first-child {
    border-top: 1.5px solid rgba(16, 185, 129, 0.65);
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-top: 3px;
  }
  .transcript-area:not(.training-active) .caption-line.in-range:has(+ .caption-line:not(.in-range)),
  .transcript-area:not(.training-active) .caption-line.in-range:last-child {
    border-bottom: 1.5px solid rgba(245, 158, 11, 0.65);
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
    margin-bottom: 3px;
  }

  .transcript-area:not(.training-active) .caption-line.active {
    background: rgba(43, 162, 189, 0.24);
    box-shadow: inset 3px 0 0 #2ba2bd;
    color: #ffffff;
    font-weight: 600;
  }

  .training-toolbar {
    display: none;
    justify-content: flex-end;
    align-items: center;
    gap: 6px;
    padding-bottom: 4px;
    flex-shrink: 0;
  }
  .transcript-area.training-active:not(.mode-off) .training-toolbar {
    display: flex;
  }
  .view-pill {
    background: rgba(30, 41, 59, 0.85);
    color: #94a3b8;
    border: 1px solid #334155;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.14s;
  }
  .view-pill.selected {
    background: rgba(43, 162, 189, 0.22);
    color: #38bdf8;
    border-color: rgba(43, 162, 189, 0.65);
  }

  .transcript-area.training-active:not(.mode-off) .caption-list {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 4px 6px;
  }

  .transcript-area.training-active .caption-line:not(.in-range) {
    display: none !important;
  }
  .transcript-area.training-active .line-actions {
    display: none !important;
  }

  .transcript-area.training-active.view-spotlight .caption-line.in-range {
    display: none;
    border: none;
    background: transparent;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 19px;
    line-height: 1.55;
    margin: 2px 0;
  }
  .transcript-area.training-active.view-spotlight .caption-line.in-range.neighbor-line {
    display: flex;
    opacity: 0.34;
    font-weight: 400;
    color: #cbd5e1;
  }
  .transcript-area.training-active.view-spotlight .caption-line.in-range.active {
    display: flex;
    opacity: 1;
    font-weight: 600;
    color: #ffffff;
    background: rgba(43, 162, 189, 0.16);
    box-shadow: inset 3px 0 0 #2ba2bd;
  }

  .transcript-area.training-active.view-oneline .caption-line.in-range {
    display: none;
  }
  .transcript-area.training-active.view-oneline .caption-line.in-range.active {
    display: flex;
    justify-content: center;
    text-align: center;
    border: none;
    background: transparent;
    font-size: 22px;
    line-height: 1.6;
    font-weight: 600;
    color: #ffffff;
    padding: 12px 16px;
  }
  .transcript-area.training-active.view-oneline .caption-line.in-range.active .caption-time {
    display: none;
  }

  .caption-main {
    flex: 1;
    min-width: 0;
  }
  .caption-time {
    font-size: 10.5px;
    color: var(--muted);
    margin-right: 6px;
    font-variant-numeric: tabular-nums;
  }
  .line-actions {
    display: flex;
    gap: 5px;
    flex-shrink: 0;
    align-self: center;
  }
  .tag-btn {
    border-radius: 5px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.12s;
  }
  .tag-btn.s-btn {
    background: rgba(16, 185, 129, 0.16);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.5);
  }
  .transcript-area.awaiting-range .tag-btn.s-btn {
    background: rgba(16, 185, 129, 0.25);
    border-color: rgba(16, 185, 129, 0.8);
  }
  .tag-btn.s-btn:hover,
  .tag-btn.s-btn.is-start {
    background: #10b981;
    color: #020617;
    border-color: #10b981;
  }

  .tag-btn.e-btn {
    background: rgba(245, 158, 11, 0.16);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.5);
  }
  .transcript-area.awaiting-range .tag-btn.e-btn {
    background: rgba(245, 158, 11, 0.25);
    border-color: rgba(245, 158, 11, 0.8);
  }
  .tag-btn.e-btn:hover,
  .tag-btn.e-btn.is-end {
    background: #f59e0b;
    color: #020617;
    border-color: #f59e0b;
  }

  .tag-btn.sync-line-btn {
    background: rgba(251, 191, 36, 0.18);
    color: #fbbf24;
    border: 1px solid rgba(251, 191, 36, 0.6);
    font-weight: 700;
    padding: 4px 10px;
    font-size: 11px;
  }
  .tag-btn:active {
    transform: scale(0.95);
  }

  .mode-off .caption-list { display: none !important; }
  .blind-notice {
    display: none;
    height: 100%;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    color: #94a3b8;
    text-align: center;
    font-size: 14px;
    gap: 6px;
  }
  .mode-off .blind-notice { display: flex; }

  .vas-drawer {
    display: none;
    background: #0f172a;
    border-top: 1px solid #334155;
    padding: 10px 14px;
    flex-direction: column;
    gap: 8px;
    flex-shrink: 0;
  }
  .vas-drawer.open {
    display: flex;
  }
  .vas-top-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12.5px;
    font-weight: 700;
    color: #f8fafc;
  }
  .vas-score-readout {
    font-size: 17px;
    font-weight: 800;
    color: #60a5fa;
    font-variant-numeric: tabular-nums;
  }
  .vas-slider-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .vas-end-label {
    font-size: 11px;
    color: #94a3b8;
    white-space: nowrap;
  }
  input[type="range"].vas-slider {
    flex: 1;
    accent-color: var(--primary-blue);
    height: 6px;
    cursor: pointer;
  }
  .vas-actions-row {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
  }
  .vas-submit-btn {
    background: var(--primary-blue);
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 7px 18px;
    font-size: 12.5px;
    font-weight: 700;
    cursor: pointer;
    white-space: nowrap;
  }
  .vas-submit-btn:hover {
    background: #3b82f6;
  }

  .ninja-panel {
    flex: 1;
    background: var(--panel);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 6px 8px 8px;
    gap: 5px;
    min-height: 0;
    transition: opacity 0.22s ease, filter 0.22s ease;
  }
  @media (orientation: portrait) {
    .ninja-panel.steps-collapsed {
      flex: 0 0 auto;
    }
    .ninja-panel.steps-collapsed .steps-list {
      display: none;
    }
  }

  .ninja-panel.locked-unsynced {
    opacity: 0.34;
    pointer-events: none;
    filter: grayscale(0.45);
  }
  .ninja-panel.awaiting-range .next-btn,
  .ninja-panel.awaiting-range .run-btn,
  .ninja-panel.awaiting-range .steps-header,
  .ninja-panel.awaiting-range .steps-list {
    opacity: 0.32;
    pointer-events: none;
  }
  .ninja-panel:not(.running-active) .stop-btn {
    opacity: 0.32;
    pointer-events: none;
  }

  .ninja-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    font-size: 12px;
    font-weight: 700;
    color: #e2e8f0;
    flex-shrink: 0;
  }
  .header-right-group {
    display: flex;
    align-items: center;
    gap: 5px;
    flex-shrink: 0;
  }
  .protocol-select {
    background: var(--card);
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 5px;
    padding: 3px 6px;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    min-width: 0;
    flex: 1;
    transition: opacity 0.2s, border-color 0.14s;
  }
  .protocol-select:hover,
  .protocol-select:focus {
    border-color: #64748b;
    outline: none;
  }
  .log-pill-btn {
    background: var(--card);
    color: #e2e8f0;
    border: 1px solid #475569;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 10.5px;
    font-weight: 700;
    cursor: pointer;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .log-pill-btn:hover {
    border-color: #94a3b8;
    color: #fff;
  }
  .status-badge {
    font-size: 10.5px;
    font-weight: 600;
    color: #e2e8f0;
    background: rgba(148, 163, 184, 0.14);
    padding: 2px 7px;
    border-radius: 999px;
    white-space: nowrap;
  }
  .range-row {
    display: grid;
    grid-template-columns: 1fr 1fr auto;
    gap: 5px;
    align-items: center;
    flex-shrink: 0;
  }
  .mark-box {
    display: flex;
    align-items: center;
    background: var(--card);
    border: 1px solid #334155;
    border-radius: 6px;
    overflow: hidden;
  }
  .mark-box.start-box {
    border-color: rgba(16, 185, 129, 0.45);
  }
  .mark-box.end-box {
    border-color: rgba(245, 158, 11, 0.45);
  }
  .mark-btn {
    color: #fff;
    border: none;
    padding: 6px 9px;
    font-size: 11.5px;
    font-weight: 700;
    cursor: pointer;
    white-space: nowrap;
  }
  .mark-btn.start-btn {
    background: #059669;
  }
  .mark-btn.start-btn:hover {
    background: #10b981;
  }
  .mark-btn.end-btn {
    background: #d97706;
  }
  .mark-btn.end-btn:hover {
    background: #f59e0b;
  }
  .mark-val {
    flex: 1;
    text-align: center;
    font-size: 11.5px;
    font-variant-numeric: tabular-nums;
    padding: 0 4px;
    font-weight: 600;
  }
  .mark-val.start-val { color: #6ee7b7; }
  .mark-val.end-val { color: #fcd34d; }
  .next-btn {
    background: var(--card);
    color: var(--text);
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 6px 9px;
    font-size: 11.5px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }
  .run-row {
    display: grid;
    grid-template-columns: 1.4fr 1fr auto;
    gap: 5px;
    flex-shrink: 0;
  }
  .run-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: var(--primary-blue);
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 7px;
    font-size: 12.5px;
    font-weight: 700;
    cursor: pointer;
    transition: opacity 0.2s, background 0.14s;
  }
  .run-btn span {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }
  .run-btn:hover svg {
    transform: rotate(90deg);
  }
  .stop-btn {
    background: var(--danger);
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 7px;
    font-size: 12.5px;
    font-weight: 700;
    cursor: pointer;
    transition: opacity 0.2s;
  }
  .cfg-btn {
    background: var(--card);
    color: var(--text);
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 12.5px;
    cursor: pointer;
    transition: opacity 0.2s;
  }
  .steps-header {
    font-size: 10.5px;
    font-weight: 700;
    color: var(--muted);
    letter-spacing: 0.04em;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
    padding: 2px 2px;
    user-select: none;
  }
  .steps-toggle-trigger {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
    color: #cbd5e1;
  }
  .steps-chevron {
    display: none;
    font-size: 11px;
    color: #94a3b8;
  }
  @media (orientation: portrait) {
    .steps-chevron {
      display: inline;
    }
  }
  .vas-mode-toggle {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: #cbd5e1;
    cursor: pointer;
    font-size: 10.5px;
    font-weight: 600;
  }
  .steps-list {
    flex: 1;
    overflow-y: auto;
    border: 1px solid #1e293b;
    border-radius: 6px;
    background: #020617;
    min-height: 0;
  }
  .step-item {
    display: grid;
    grid-template-columns: 26px 46px 56px 1fr auto;
    align-items: center;
    padding: 5px 8px;
    border-bottom: 1px solid #1e293b;
    font-size: 12px;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
    gap: 4px;
  }
  .step-item:last-child { border-bottom: none; }
  .step-item.current-step {
    background: rgba(43, 162, 189, 0.28);
    color: #fff;
    font-weight: 700;
  }
  .step-num { color: var(--muted); }
  .step-speed { color: #f8fafc; font-weight: 600; }
  .step-cc-on { color: #38bdf8; font-weight: 600; }
  .step-cc-off { color: #64748b; }
  .step-vas-pill {
    font-size: 10.5px;
    font-weight: 700;
    color: #60a5fa;
    background: rgba(37, 99, 235, 0.22);
    padding: 1px 6px;
    border-radius: 999px;
  }

  @keyframes shuriken-spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
  }
  .step-shuriken {
    width: 18px;
    height: 18px;
    fill: #38bdf8;
    justify-self: end;
    display: block;
    animation: shuriken-spin var(--spin-dur, 1.2s) linear infinite;
  }
  .step-shuriken.paused {
    animation-play-state: paused;
  }

  .fast-tooltip {
    position: fixed;
    z-index: 9999;
    background: #020617;
    color: #f8fafc;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 600;
    pointer-events: none;
    white-space: nowrap;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.65);
    opacity: 0;
    transition: opacity 0.08s ease;
  }
  .fast-tooltip.visible {
    opacity: 1;
  }

  @media (min-width: 640px) and (orientation: landscape) {
    .app-shell {
      display: grid;
      grid-template-columns: minmax(320px, 46%) 1fr;
      grid-template-rows: auto auto 1fr auto;
      grid-template-areas:
        "banner banner"
        "video transcript"
        "ninja transcript"
        "ninja vas";
      height: 100vh;
    }
    .stage-banner {
      grid-area: banner;
    }
    .video-section {
      grid-area: video;
      border-right: 1px solid #1e293b;
    }
    .player-wrap {
      max-height: min(35vh, 260px);
    }
    .ninja-panel {
      grid-area: ninja;
      border-right: 1px solid #1e293b;
      padding: 5px 8px 6px;
      gap: 4px;
    }
    .transcript-area {
      grid-area: transcript;
      border-bottom: none;
      height: 100%;
      padding: 6px 10px;
    }
    .vas-drawer {
      grid-area: vas;
    }
  }

  .modal-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.82);
    z-index: 50;
    align-items: center;
    justify-content: center;
    padding: 8px;
  }
  .modal-backdrop.open { display: flex; }
  .modal-box {
    background: #1e293b;
    border: 1px solid #475569;
    border-radius: 10px;
    width: 100%;
    max-width: 460px;
    max-height: 92vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .modal-box.plot-modal-box {
    width: 96vw;
    max-width: 820px;
    max-height: 94vh;
    background: #181818;
  }
  .modal-head {
    padding: 8px 12px;
    font-weight: 700;
    font-size: 13px;
    border-bottom: 1px solid #334155;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    background: #1e293b;
    flex-shrink: 0;
  }
  .modal-head-title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .modal-name-bar {
    padding: 8px 12px;
    background: #0f172a;
    border-bottom: 1px solid #334155;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }
  .modal-name-bar input {
    flex: 1;
    background: #1e293b;
    color: #fff;
    border: 1px solid #475569;
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 12.5px;
    font-weight: 600;
  }
  .modal-body {
    padding: 8px 12px;
    overflow-y: auto;
    flex: 1;
  }
  .plot-canvas-wrap {
    padding: 6px 10px;
    background: #181818;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
  #vas-plot-canvas {
    width: auto;
    height: auto;
    max-width: 100%;
    max-height: calc(94vh - 86px);
    object-fit: contain;
    border-radius: 6px;
    background: #181818;
  }
  .edit-row {
    display: grid;
    grid-template-columns: 24px 70px 60px 1fr;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
    font-size: 12px;
  }
  .edit-row input[type="number"] {
    width: 100%;
    background: #0f172a;
    color: #fff;
    border: 1px solid #475569;
    border-radius: 4px;
    padding: 4px;
  }
  .modal-foot {
    padding: 6px 12px;
    border-top: 1px solid #334155;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: space-between;
    align-items: center;
    background: #1e293b;
    flex-shrink: 0;
  }
  .export-btn {
    background: var(--neon-cyan);
    color: #020617;
    border: none;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 11.5px;
    font-weight: 800;
    cursor: pointer;
    white-space: nowrap;
  }
  .export-btn:hover {
    filter: brightness(1.1);
  }
  .ninja-spin-hover {
    transition: transform 0.2s ease;
  }
  button:hover .ninja-spin-hover,
  .ninja-spin-hover:hover {
    animation: ninja-shuriken-spin 0.85s linear infinite;
  }
  @keyframes ninja-shuriken-spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
  }
  .ninja-spin-hover {
    transition: transform 0.2s ease;
  }
  button:hover .ninja-spin-hover,
  .ninja-spin-hover:hover {
    animation: ninja-shuriken-spin 0.85s linear infinite;
  }
</style>
</head>
<body>

<div id="fast-tooltip" class="fast-tooltip"></div>

<div class="app-shell" id="app-shell">
  <div class="stage-banner" id="stage-banner">1. Play video &amp; tap Sync on the line you hear (or ✓ Sync OK)</div>

  <div class="video-section">
    <div class="player-wrap" id="player-wrap">
      <div id="yt-player"></div>
      <div id="local-audio-box" style="display:none;">
        <div class="local-audio-header">
          <span class="local-audio-title" id="local-audio-title">Local Audio</span>
          <span class="local-audio-badge">LOCAL AUDIO</span>
        </div>
        <div class="local-scrub-track" id="local-scrub-track">
          <div class="local-scrub-range" id="local-scrub-range"></div>
          <div class="local-scrub-fill" id="local-scrub-fill"></div>
          <div class="local-scrub-thumb" id="local-scrub-thumb"></div>
        </div>
        <div class="local-scrub-ticks">
          <span id="local-cur-precise">00:00.0</span>
          <span>Tap or drag bar to scrub</span>
          <span id="local-dur-precise">00:00.0</span>
        </div>
      </div>
    </div>
    <div class="meta-bar" id="meta-bar"></div>
  </div>

  <div class="transcript-area view-spotlight" id="transcript-area">
    <div class="training-toolbar">
      <button class="view-pill selected" id="pill-spotlight" onclick="setTrainingView('spotlight')">Spotlight</button>
      <button class="view-pill" id="pill-oneline" onclick="setTrainingView('oneline')">1-Line</button>
    </div>
    <div class="blind-notice">
      <div style="font-size: 22px;">🎧</div>
      <div id="blind-step-label">CC OFF — Listen carefully</div>
    </div>
    <div class="caption-list" id="caption-list"></div>
  </div>

  <div class="vas-drawer" id="vas-drawer">
    <div class="vas-top-row">
      <span id="vas-step-prompt">Step 1/19 (1.0x CC OFF) — Speech Clarity</span>
      <span class="vas-score-readout" id="vas-score-readout">50%</span>
    </div>
    <div class="vas-slider-wrap">
      <span class="vas-end-label">0% Unclear</span>
      <input type="range" min="0" max="100" value="50" class="vas-slider" id="vas-slider" oninput="onVasSliderInput(this.value)" />
      <span class="vas-end-label">100% Crystal Clear</span>
    </div>
    <div class="vas-actions-row">
      <button class="vas-submit-btn" onclick="submitVasAndContinue()">Record &amp; Next →</button>
    </div>
  </div>

  <div class="ninja-panel locked-unsynced" id="ninja-panel">
    <div class="ninja-header">
      <select class="protocol-select" id="protocol-select" data-tip="Switch training protocol" onchange="onProtocolChange(this.value)"></select>
      <div class="header-right-group">
        <button class="log-pill-btn" id="log-pill-btn" data-tip="View neon VAS plot &amp; export CSV" onclick="openPlotModal()">📊 0</button>
        <span class="status-badge" id="status-badge">Step 1: Sync</span>
      </div>
    </div>

    <div class="range-row">
      <div class="mark-box start-box">
        <button class="mark-btn start-btn" data-tip="Mark Start at current video timestamp" onclick="markStartNow()">Mark start</button>
        <span class="mark-val start-val" id="start-val">--:--.-</span>
      </div>
      <div class="mark-box end-box">
        <button class="mark-btn end-btn" data-tip="Mark End at current video timestamp" onclick="markEndNow()">Mark end</button>
        <span class="mark-val end-val" id="end-val">--:--.-</span>
      </div>
      <button class="next-btn" data-tip="Advance to the next 30s fragment" onclick="moveToNextFragment()">Next →</button>
    </div>

    <div class="run-row">
      <button class="run-btn" onclick="runSequence(0)">
        <span>__RUN_SEQ_SHURIKEN__ Run sequence</span>
      </button>
      <button class="stop-btn" onclick="stopSequence()">■ Stop</button>
      <button class="cfg-btn" data-tip="Customize or save named sequence" onclick="openModal()">⚙</button>
    </div>

    <div class="steps-header">
      <span class="steps-toggle-trigger" onclick="toggleStepsDrawer()">
        <span>STEPS (TAP TO JUMP IN)</span>
        <span class="steps-chevron" id="steps-chevron">▾</span>
      </span>
      <div style="display:flex;align-items:center;gap:8px;">
        <label class="vas-mode-toggle" data-tip="Ask VAS Clarity rating after each step">
          <input type="checkbox" id="vas-enabled-chk" checked onchange="toggleVasEnabled(this.checked)" />
          <span>VAS</span>
        </label>
        <span id="step-counter">19 steps</span>
      </div>
    </div>
    <div class="steps-list" id="steps-list"></div>
  </div>
</div>

<div class="modal-backdrop" id="plot-modal">
  <div class="modal-box plot-modal-box">
    <div class="modal-head">
      <span class="modal-head-title" id="plot-modal-title">VAS Clarity &amp; Speed Log</span>
      <button class="nudge-btn" onclick="closePlotModal()">✕</button>
    </div>
    <div class="plot-canvas-wrap">
      <canvas id="vas-plot-canvas" width="840" height="440"></canvas>
      <div id="plot-empty-msg" style="color:#94a3b8;font-size:13px;padding:24px 0;display:none;">
        No VAS trials recorded yet. Run a sequence with VAS checked to plot your clarity curve.
      </div>
    </div>
    <div class="modal-foot">
      <div style="display:flex;align-items:center;gap:5px;">
        <span style="font-size:11px;color:#94a3b8;">ID:</span>
        <input type="text" id="subject-id-input" value="SUBJ_001"
               style="width:82px;background:#0f172a;color:#fff;border:1px solid #475569;border-radius:4px;padding:3px 6px;font-size:11px;"
               onchange="saveSubjectId(this.value)" />
        <button class="nudge-btn" onclick="clearTrialLogs()">Clear</button>
      </div>
      <div style="display:flex;gap:6px;">
        <button class="nudge-btn" onclick="downloadPlotPng()">⬇ PNG</button>
        <button class="export-btn" onclick="exportLogsCsv()">⬇ Export CSV</button>
      </div>
    </div>
  </div>
</div>

<div class="modal-backdrop" id="cfg-modal">
  <div class="modal-box">
    <div class="modal-head">
      <span>Customize &amp; Save Sequence</span>
      <button class="nudge-btn" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-name-bar">
      <span style="color:#94a3b8;font-weight:600;">Name:</span>
      <input type="text" id="custom-seq-name" placeholder="e.g. Custom Sequence" />
    </div>
    <div class="modal-body" id="modal-steps-body"></div>
    <div class="modal-foot">
      <div>
        <button class="nudge-btn" id="del-custom-btn" style="color:#f87171;border-color:rgba(239,68,68,0.45);display:none;" onclick="deleteCurrentCustomProtocol()">Delete</button>
      </div>
      <div style="display:flex;gap:6px;">
        <button class="nudge-btn" onclick="addStepRow()">+ Add</button>
        <button class="nudge-btn" onclick="resetDraftToSelected()">Reset</button>
        <button class="nudge-btn" style="background:#2563eb;border-color:#2563eb;" onclick="saveModalSteps()">Save</button>
      </div>
    </div>
  </div>
</div>

<script>
  const captions = __CAPTIONS_JSON__;
  const videoId = __VIDEO_ID_JSON__;
  const sourceUrl = __SOURCE_URL_JSON__;
  const mediaMode = __MEDIA_MODE_JSON__;
  const localAudioDataUri = __LOCAL_AUDIO_URI_JSON__;
  const localTitle = __LOCAL_TITLE_JSON__;
  const initialSynced = __INITIAL_SYNCED_JSON__;

  if (typeof window.YT === "undefined") {
    window.YT = { PlayerState: { UNSTARTED: -1, ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3, CUED: 5 } };
  }

  let urlBarManuallyVisible = false;
  const LAST_VIDEO_KEY = "ninja_last_video_id_v1";

  try {
    if (mediaMode === "youtube" && videoId) {
      localStorage.setItem(LAST_VIDEO_KEY, videoId);
      if (window.parent && window.parent.history) {
        const parentUrl = new URL(window.parent.location.href);
        let changed = false;
        if (parentUrl.searchParams.get("v") !== videoId) {
          parentUrl.searchParams.set("v", videoId);
          changed = true;
        }
        if (parentUrl.searchParams.get("mode") !== "LISTENING") {
          parentUrl.searchParams.set("mode", "LISTENING");
          changed = true;
        }
        if (changed) {
          window.parent.history.replaceState(null, "", parentUrl.toString());
        }
      }
    }
  } catch (e) {}

  function applyParentUrlBarVisibility() {
    try {
      if (!window.parent || !window.parent.document) return;
      const shouldShow = !isRunning && urlBarManuallyVisible;

      const inputEl = window.parent.document.querySelector('input[aria-label="YouTube URL"]');
      const inputBlock = inputEl ? inputEl.closest('div[data-testid="stTextInput"]') : null;
      if (inputBlock) {
        const container = inputBlock.closest('div[data-testid="stElementContainer"]') || inputBlock.closest('div[data-testid="element-container"]') || inputBlock;
        container.style.display = shouldShow ? "" : "none";
      }
      const orDiv = window.parent.document.getElementById("ninja-or-divider");
      if (orDiv) {
        const divContainer = orDiv.closest('div[data-testid="stElementContainer"]') || orDiv;
        divContainer.style.display = shouldShow ? "" : "none";
      }
      const uploaders = window.parent.document.querySelectorAll('div[data-testid="stFileUploader"]');
      uploaders.forEach((up) => {
        const colWrap = up.closest('div[data-testid="stHorizontalBlock"]') || up.closest('div[data-testid="stElementContainer"]') || up;
        colWrap.style.display = shouldShow ? "" : "none";
      });

      const buttons = window.parent.document.querySelectorAll('button');
      buttons.forEach((btn) => {
        const txt = (btn.textContent || "").trim();
        if (txt === "▼" || txt === "▲") {
          const btnContainer = btn.closest('div[data-testid="stElementContainer"]') || btn.closest('div[data-testid="element-container"]') || btn;
          btnContainer.style.display = isRunning ? "none" : "";
        }
      });
    } catch (e) {}
    setTimeout(fitParentIframe, 25);
  }

  function toggleUrlBar() {
    if (isRunning) return;
    urlBarManuallyVisible = !urlBarManuallyVisible;
    applyParentUrlBarVisibility();
    const btn = document.getElementById("url-toggle-btn");
    if (btn) btn.classList.toggle("active", urlBarManuallyVisible);
  }

  function fitParentIframe() {
    try {
      const frame = window.frameElement;
      if (frame && window.parent) {
        const topOffset = frame.getBoundingClientRect().top;
        const avail = Math.max(320, window.parent.innerHeight - topOffset - 6);
        frame.style.height = avail + "px";
      }
    } catch (e) {}
  }
  window.addEventListener("load", fitParentIframe);
  window.addEventListener("resize", fitParentIframe);
  setTimeout(fitParentIframe, 100);

  const tooltipEl = document.getElementById("fast-tooltip");
  document.addEventListener("mouseover", (e) => {
    const target = e.target.closest("[data-tip]");
    if (!target) {
      tooltipEl.classList.remove("visible");
      return;
    }
    const text = target.getAttribute("data-tip");
    if (!text) return;
    tooltipEl.textContent = text;
    tooltipEl.classList.add("visible");

    const rect = target.getBoundingClientRect();
    const tipRect = tooltipEl.getBoundingClientRect();
    let left = rect.left + rect.width / 2 - tipRect.width / 2;
    left = Math.max(8, Math.min(window.innerWidth - tipRect.width - 8, left));
    let top = rect.top - tipRect.height - 6;
    if (top < 8) top = rect.bottom + 6;
    tooltipEl.style.left = left + "px";
    tooltipEl.style.top = top + "px";
  });
  document.addEventListener("mouseout", (e) => {
    if (e.target.closest("[data-tip]")) {
      tooltipEl.classList.remove("visible");
    }
  });
  document.addEventListener("mousedown", () => {
    tooltipEl.classList.remove("visible");
  });

  const DEFAULT_SPAN = 30.0;
  const SYNC_CACHE_KEY = "ninja_sync_cache_v1";
  const CUSTOM_PROTOCOLS_KEY = "ninja_custom_protocols_v1";
  const SELECTED_PROTOCOL_KEY = "ninja_selected_protocol_v1";
  const TRIAL_LOG_KEY = "ninja_trial_logs_v1";
  const SUBJECT_ID_KEY = "ninja_subject_id_v1";
  const MAX_CACHE_ENTRIES = 100;

  const YT_PLAY_ICON = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
  const YT_PAUSE_ICON = '<svg viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
  const LINK_ICON = '<svg viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>';
  const UNLINK_ICON = '<svg viewBox="0 0 24 24"><path d="m18.84 12.25 1.72-1.71h-.02a5.004 5.004 0 0 0-.12-7.07 5.006 5.006 0 0 0-6.95 0l-1.72 1.71"/><path d="m5.17 11.75-1.71 1.71a5.004 5.004 0 0 0 .12 7.07 5.006 5.006 0 0 0 6.95 0l1.71-1.71"/><line x1="8" y1="2" x2="8" y2="5"/><line x1="2" y1="8" x2="5" y2="8"/><line x1="16" y1="19" x2="16" y2="22"/><line x1="19" y1="16" x2="22" y2="16"/></svg>';
  let nudgeDrawerOpen = false;

  function toggleNudgeDrawer() {
    if (isRunning) return;
    nudgeDrawerOpen = !nudgeDrawerOpen;
    renderSyncBar();
  }

  function buildShadowingSteps() {
    const list = [
      { speed: 1.0, cc: false },
      { speed: 1.0, cc: true }
    ];
    for (const spd of [0.5, 0.6, 0.7, 0.8]) {
      for (let r = 0; r < 3; r++) list.push({ speed: spd, cc: true });
    }
    for (const spd of [0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]) {
      for (let r = 0; r < 3; r++) list.push({ speed: spd, cc: false });
    }
    return list;
  }

  const BUILTIN_PROTOCOLS = {
    "anchor_06": {
      name: "Ninja Protocol (0.6x Anchor)",
      shortKey: "ninja",
      steps: [
        { speed: 1.0, cc: false }, { speed: 1.0, cc: true },
        { speed: 0.6, cc: true }, { speed: 0.6, cc: true }, { speed: 0.6, cc: true },
        { speed: 0.7, cc: true }, { speed: 0.8, cc: true }, { speed: 0.9, cc: true },
        { speed: 1.0, cc: false }, { speed: 1.1, cc: false }, { speed: 1.2, cc: false },
        { speed: 1.3, cc: false }, { speed: 1.4, cc: false }, { speed: 1.5, cc: false },
        { speed: 1.6, cc: false }, { speed: 1.7, cc: false }, { speed: 1.8, cc: false },
        { speed: 1.9, cc: false }, { speed: 2.0, cc: false }
      ]
    },
    "express": {
      name: "Ninja Protocol (Express)",
      shortKey: "express",
      steps: [
        { speed: 1.0, cc: false }, { speed: 0.6, cc: true },
        { speed: 1.0, cc: false }, { speed: 1.3, cc: false }, { speed: 1.5, cc: false },
        { speed: 1.6, cc: false }, { speed: 1.7, cc: false }, { speed: 1.8, cc: false },
        { speed: 1.9, cc: false }, { speed: 2.0, cc: false }
      ]
    },
    "shadowing": {
      name: "Ninja Shadowing Protocol",
      shortKey: "shadowing",
      steps: buildShadowingSteps()
    }
  };

  function loadCustomProtocols() {
    try { return JSON.parse(localStorage.getItem(CUSTOM_PROTOCOLS_KEY) || "{}"); }
    catch (e) { return {}; }
  }

  function saveCustomProtocols(obj) {
    try { localStorage.setItem(CUSTOM_PROTOCOLS_KEY, JSON.stringify(obj)); } catch (e) {}
  }

  let customProtocols = loadCustomProtocols();
  let selectedProtocolId = localStorage.getItem(SELECTED_PROTOCOL_KEY) || "anchor_06";

  function getProtocolById(pid) {
    if (BUILTIN_PROTOCOLS[pid]) return BUILTIN_PROTOCOLS[pid];
    if (customProtocols[pid]) return customProtocols[pid];
    return BUILTIN_PROTOCOLS["anchor_06"];
  }

  if (!BUILTIN_PROTOCOLS[selectedProtocolId] && !customProtocols[selectedProtocolId]) {
    selectedProtocolId = "anchor_06";
  }

  let steps = getProtocolById(selectedProtocolId).steps.map(s => ({ ...s }));
  let trainingView = localStorage.getItem("ninja_training_view") || "spotlight";
  let vasEnabled = localStorage.getItem("ninja_vas_enabled") !== "false";
  let subjectId = localStorage.getItem(SUBJECT_ID_KEY) || "SUBJ_001";
  let trialLogs = [];
  try { trialLogs = JSON.parse(localStorage.getItem(TRIAL_LOG_KEY) || "[]"); } catch (e) { trialLogs = []; }

  let player = null;
  let videoTitle = localTitle || videoId;
  let activeCaptionIdx = -1;
  let previewCaptionIdx = -1;

  let isSynced = Boolean(initialSynced);
  let restoredFromCache = false;
  let timeOffset = 0.0;
  let hasUserRange = false;

  let rangeStart = 0.0;
  let rangeEnd = DEFAULT_SPAN;
  let cachedResumeTime = null;
  let lastSavedPlaybackSec = -1;

  let isRunning = false;
  let awaitingVas = false;
  let currentStepIdx = -1;
  let stepTransitionLock = false;
  let stepsCollapsedPortrait = false;

  let userScrolling = false;
  let scrollTimeout = null;

  const appShellEl = document.getElementById("app-shell");
  const stageBannerEl = document.getElementById("stage-banner");
  const protocolSelectEl = document.getElementById("protocol-select");
  const listEl = document.getElementById("caption-list");
  const areaEl = document.getElementById("transcript-area");
  const metaBarEl = document.getElementById("meta-bar");
  const ninjaPanelEl = document.getElementById("ninja-panel");
  const startValEl = document.getElementById("start-val");
  const endValEl = document.getElementById("end-val");
  const statusBadge = document.getElementById("status-badge");
  const stepsListEl = document.getElementById("steps-list");
  const stepsChevronEl = document.getElementById("steps-chevron");
  const blindStepLabel = document.getElementById("blind-step-label");
  const vasDrawerEl = document.getElementById("vas-drawer");
  const vasSliderEl = document.getElementById("vas-slider");
  const vasScoreReadoutEl = document.getElementById("vas-score-readout");
  const logPillBtnEl = document.getElementById("log-pill-btn");

  document.getElementById("vas-enabled-chk").checked = vasEnabled;
  document.getElementById("subject-id-input").value = subjectId;

  function togglePlayPause() {
    if (!player || typeof player.getPlayerState !== "function") return;
    if (player.getPlayerState() === YT.PlayerState.PLAYING) player.pauseVideo();
    else player.playVideo();
  }

  function updatePlayButtonIcon() {
    const btn = document.getElementById("play-toggle-btn");
    if (!btn || !player || typeof player.getPlayerState !== "function") return;
    btn.innerHTML = (player.getPlayerState() === YT.PlayerState.PLAYING) ? YT_PAUSE_ICON : YT_PLAY_ICON;
  }

  function setStepsCollapsedPortrait(collapsed) {
    stepsCollapsedPortrait = collapsed;
    ninjaPanelEl.classList.toggle("steps-collapsed", collapsed);
    if (stepsChevronEl) stepsChevronEl.textContent = collapsed ? "▸" : "▾";
  }

  function toggleStepsDrawer() {
    setStepsCollapsedPortrait(!stepsCollapsedPortrait);
    if (!stepsCollapsedPortrait && isRunning && currentStepIdx >= 0) {
      document.getElementById("step-row-" + currentStepIdx)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function saveTrialLogs() {
    try { localStorage.setItem(TRIAL_LOG_KEY, JSON.stringify(trialLogs)); } catch (e) {}
    updateLogPill();
  }

  function updateLogPill() {
    const videoTrials = trialLogs.filter(r => r.VideoID === videoId);
    logPillBtnEl.textContent = `📊 ${videoTrials.length}`;
  }

  function saveSubjectId(val) {
    subjectId = (val || "").trim() || "SUBJ_001";
    localStorage.setItem(SUBJECT_ID_KEY, subjectId);
  }

  function toggleVasEnabled(checked) {
    vasEnabled = checked;
    localStorage.setItem("ninja_vas_enabled", String(checked));
    if (!checked && awaitingVas) {
      awaitingVas = false;
      vasDrawerEl.classList.remove("open");
      applyStep(currentStepIdx + 1);
    }
  }

  function onVasSliderInput(val) {
    vasScoreReadoutEl.textContent = `${val}%`;
  }

  function promptVasForCurrentStep() {
    awaitingVas = true;
    if (player && typeof player.pauseVideo === "function") player.pauseVideo();
    const step = steps[currentStepIdx];
    document.getElementById("vas-step-prompt").textContent =
      `Step ${currentStepIdx + 1}/${steps.length} (${step.speed.toFixed(1)}x ${step.cc ? 'CC ON' : 'CC OFF'}) — Clarity`;
    vasScoreReadoutEl.textContent = `${vasSliderEl.value}%`;
    vasDrawerEl.classList.add("open");
    statusBadge.textContent = `Rate Step ${currentStepIdx + 1}/${steps.length}`;
    renderStepsList();
  }

  function submitVasAndContinue() {
    if (!awaitingVas || currentStepIdx < 0) return;
    const step = steps[currentStepIdx];
    const score = parseInt(vasSliderEl.value, 10) || 0;
    const proto = getProtocolById(selectedProtocolId);

    trialLogs.push({
      SubjectID: subjectId,
      Timestamp: new Date().toISOString(),
      VideoID: videoId,
      StartTime: Number(rangeStart.toFixed(2)),
      EndTime: Number(rangeEnd.toFixed(2)),
      StepIdx: currentStepIdx + 1,
      PlaybackRate: Number(step.speed.toFixed(1)),
      Subtitles: Boolean(step.cc),
      VAS_Clarity: score,
      URL: sourceUrl || (mediaMode === "youtube" ? `https://www.youtube.com/watch?v=${videoId}` : `local://${videoTitle}`),
      Title: videoTitle || videoId,
      Protocol: proto.shortKey || proto.name
    });
    saveTrialLogs();

    awaitingVas = false;
    vasDrawerEl.classList.remove("open");
    renderStepsList();
    applyStep(currentStepIdx + 1);
  }

  document.addEventListener("keydown", (e) => {
    if (awaitingVas && e.key === "Enter") {
      e.preventDefault();
      submitVasAndContinue();
    }
  });

  function renderProtocolDropdown() {
    protocolSelectEl.innerHTML = "";
    for (const [id, proto] of Object.entries(BUILTIN_PROTOCOLS)) {
      const opt = document.createElement("option");
      opt.value = id; opt.textContent = proto.name;
      protocolSelectEl.appendChild(opt);
    }
    for (const [id, proto] of Object.entries(customProtocols)) {
      const opt = document.createElement("option");
      opt.value = id; opt.textContent = `★ ${proto.name}`;
      protocolSelectEl.appendChild(opt);
    }
    const newCustomOpt = document.createElement("option");
    newCustomOpt.value = "__new_custom__";
    newCustomOpt.textContent = "+ Custom sequence...";
    protocolSelectEl.appendChild(newCustomOpt);
    protocolSelectEl.value = selectedProtocolId;
  }

  function onProtocolChange(val) {
    if (isRunning) { protocolSelectEl.value = selectedProtocolId; return; }
    if (val === "__new_custom__") {
      protocolSelectEl.value = selectedProtocolId;
      openModal(true);
      return;
    }
    selectedProtocolId = val;
    localStorage.setItem(SELECTED_PROTOCOL_KEY, selectedProtocolId);
    steps = getProtocolById(selectedProtocolId).steps.map(s => ({ ...s }));
    renderStepsList();
  }

  function loadSyncCache() {
    try { return JSON.parse(localStorage.getItem(SYNC_CACHE_KEY) || "{}"); } catch (e) { return {}; }
  }

  function saveVideoSyncState(currentPlaybackSec = null) {
    if (!isSynced || !videoId) return;
    try {
      const cache = loadSyncCache();
      const prevEntry = cache[videoId] || {};
      const playbackToSave = (typeof currentPlaybackSec === "number" && currentPlaybackSec >= 0)
        ? Math.round(currentPlaybackSec * 10) / 10
        : (typeof prevEntry.lastPlaybackTime === "number" ? prevEntry.lastPlaybackTime : (hasUserRange ? rangeStart : 0));

      cache[videoId] = {
        timeOffset: timeOffset,
        hasUserRange: hasUserRange,
        rangeStart: rangeStart,
        rangeEnd: rangeEnd,
        lastPlaybackTime: playbackToSave,
        updatedAt: Date.now()
      };
      const keys = Object.keys(cache);
      if (keys.length > MAX_CACHE_ENTRIES) {
        keys.sort((a, b) => (cache[a].updatedAt || 0) - (cache[b].updatedAt || 0));
        for (let i = 0; i < keys.length - MAX_CACHE_ENTRIES; i++) delete cache[keys[i]];
      }
      localStorage.setItem(SYNC_CACHE_KEY, JSON.stringify(cache));
    } catch (e) {}
  }

  function deleteVideoSyncState() {
    if (!videoId) return;
    try {
      const cache = loadSyncCache();
      if (cache[videoId]) { delete cache[videoId]; localStorage.setItem(SYNC_CACHE_KEY, JSON.stringify(cache)); }
    } catch (e) {}
  }

  function restoreVideoSyncState() {
    const cache = loadSyncCache();
    const entry = cache[videoId];
    if (entry && typeof entry.timeOffset === "number") {
      timeOffset = entry.timeOffset;
      isSynced = true;
      restoredFromCache = true;
      if (entry.hasUserRange && typeof entry.rangeStart === "number" && typeof entry.rangeEnd === "number") {
        hasUserRange = true;
        rangeStart = entry.rangeStart;
        rangeEnd = entry.rangeEnd;
        cachedResumeTime = entry.rangeStart;
      } else if (typeof entry.lastPlaybackTime === "number" && entry.lastPlaybackTime > 0) {
        cachedResumeTime = entry.lastPlaybackTime;
      }
      return true;
    }
    return false;
  }

  function getMaxDuration() {
    if (player && typeof player.getDuration === "function") {
      const d = player.getDuration();
      if (d && !isNaN(d) && d > 0) return d;
    }
    if (captions.length > 0) return captions[captions.length - 1].end + 30;
    return 3600;
  }

  function setTrainingView(mode) {
    trainingView = mode;
    localStorage.setItem("ninja_training_view", mode);
    areaEl.classList.toggle("view-spotlight", mode === "spotlight");
    areaEl.classList.toggle("view-oneline", mode === "oneline");
    document.getElementById("pill-spotlight").classList.toggle("selected", mode === "spotlight");
    document.getElementById("pill-oneline").classList.toggle("selected", mode === "oneline");
    updateNeighborClasses();
  }

  function fmtTime(sec) {
    if (sec === undefined || sec === null || isNaN(sec)) return "00:00";
    const sTotal = Math.max(0, Math.floor(sec));
    return String(Math.floor(sTotal / 60)).padStart(2, "0") + ":" + String(sTotal % 60).padStart(2, "0");
  }

  function fmtTimePrecise(sec) {
    if (sec === undefined || sec === null || isNaN(sec)) return "00:00.0";
    const sClamped = Math.max(0, sec);
    return String(Math.floor(sClamped / 60)).padStart(2, "0") + ":" + (sClamped % 60).toFixed(1).padStart(4, "0");
  }

  function updateLocalScrubBar(curT, dur) {
    if (mediaMode !== "local") return;
    const fillEl = document.getElementById("local-scrub-fill");
    const thumbEl = document.getElementById("local-scrub-thumb");
    const rangeEl = document.getElementById("local-scrub-range");
    const curPrecEl = document.getElementById("local-cur-precise");
    const durPrecEl = document.getElementById("local-dur-precise");

    const safeDur = (dur && !isNaN(dur) && dur > 0) ? dur : 0;
    const pct = safeDur > 0 ? Math.max(0, Math.min(100, (curT / safeDur) * 100)) : 0;
    if (fillEl) fillEl.style.width = pct + "%";
    if (thumbEl) thumbEl.style.left = pct + "%";
    if (curPrecEl) curPrecEl.textContent = fmtTimePrecise(curT || 0);
    if (durPrecEl) durPrecEl.textContent = fmtTimePrecise(safeDur);

    if (rangeEl) {
      if (hasUserRange && safeDur > 0) {
        const sPct = Math.max(0, Math.min(100, (rangeStart / safeDur) * 100));
        const ePct = Math.max(sPct, Math.min(100, (rangeEnd / safeDur) * 100));
        rangeEl.style.display = "block";
        rangeEl.style.left = sPct + "%";
        rangeEl.style.width = (ePct - sPct) + "%";
      } else {
        rangeEl.style.display = "none";
      }
    }
  }

  function updatePanelLockState() {
    appShellEl.classList.toggle("sequence-running", isRunning);
    ninjaPanelEl.classList.toggle("running-active", isRunning);
    areaEl.classList.toggle("awaiting-range", isSynced && !hasUserRange);
    applyParentUrlBarVisibility();

    if (!isSynced) {
      ninjaPanelEl.classList.add("locked-unsynced");
      ninjaPanelEl.classList.remove("awaiting-range");
      statusBadge.textContent = "Step 1: Sync";
      stageBannerEl.classList.remove("hidden");
      stageBannerEl.textContent = "1. Play video & tap Sync on the line you hear (or ✓ Sync OK)";
    } else if (!hasUserRange) {
      ninjaPanelEl.classList.remove("locked-unsynced");
      ninjaPanelEl.classList.add("awaiting-range");
      statusBadge.textContent = "Step 2: S / E";
      stageBannerEl.classList.remove("hidden");
      stageBannerEl.textContent = captions.length > 0
        ? "2. Mark start (S) or end (E)"
        : "2. Scrub bar & tap Mark start / Mark end to begin";
    } else {
      ninjaPanelEl.classList.remove("locked-unsynced", "awaiting-range");
      stageBannerEl.classList.add("hidden");
      if (!isRunning) statusBadge.textContent = "Ready";
    }
  }

  function renderSyncBar() {
    const curTimeText = document.getElementById("time-display")?.textContent || "00:00 / 00:00";
    const urlBtnClass = `url-toggle-btn${urlBarManuallyVisible ? " active" : ""}`;
    const srcBtnLabel = mediaMode === "local" ? "SRC" : "URL";
    const playBtnClass = mediaMode === "local" ? "yt-play-btn local-play-btn" : "yt-play-btn";

    if (!isSynced) {
      metaBarEl.innerHTML = `
        <div class="meta-top">
          <div class="meta-left-controls">
            <button class="${urlBtnClass}" id="url-toggle-btn" data-tip="Show / Hide Source Picker" onclick="toggleUrlBar()">${srcBtnLabel}</button>
            <button class="${playBtnClass}" id="play-toggle-btn" data-tip="Play / Pause" onclick="togglePlayPause()">${YT_PLAY_ICON}</button>
            <div class="time-display" id="time-display">${curTimeText}</div>
          </div>
          <button class="link-icon-btn sync-link" data-tip="Sync subtitles (accept current timing)" onclick="acceptSyncAsIs()">${LINK_ICON}</button>
        </div>
      `;
    } else {
      const sign = timeOffset >= 0 ? "+" : "";
      const savedHtml = restoredFromCache ? `<span class="saved-tag">Saved</span>` : "";
      const pillClass = `offset-toggle-pill${nudgeDrawerOpen ? " open" : ""}`;
      const drawerClass = `sync-nudge-drawer${nudgeDrawerOpen ? " open" : ""}`;
      const rightControlsHtml = captions.length > 0
        ? `<div class="meta-right-controls">
             <button class="${pillClass}" data-tip="Tap to fine-tune subtitle timing" onclick="toggleNudgeDrawer()">
               ${savedHtml}<span class="offset-badge">${sign}${timeOffset.toFixed(1)}s</span>
             </button>
             <button class="link-icon-btn unsync-unlink" data-tip="Unsync & reset" onclick="unsyncAll()">${UNLINK_ICON}</button>
           </div>`
        : `<div class="meta-right-controls"><span style="color:#64748b;font-size:10.5px;">Audio-only mode</span></div>`;

      metaBarEl.innerHTML = `
        <div class="meta-top">
          <div class="meta-left-controls">
            <button class="${urlBtnClass}" id="url-toggle-btn" data-tip="Show / Hide Source Picker" onclick="toggleUrlBar()">${srcBtnLabel}</button>
            <button class="${playBtnClass}" id="play-toggle-btn" data-tip="Play / Pause" onclick="togglePlayPause()">${YT_PLAY_ICON}</button>
            <div class="time-display" id="time-display">${curTimeText}</div>
          </div>
          ${rightControlsHtml}
        </div>
        <div class="${drawerClass}">
          <div class="nudge-labels-row"><span>Sub is LAGGING by</span><span>LEADING by</span></div>
          <div class="nudge-buttons-row">
            <button class="nudge-btn" onclick="adjustOffset(-1.0)">1s</button>
            <button class="nudge-btn" onclick="adjustOffset(-0.5)">.5s</button>
            <button class="nudge-btn" onclick="adjustOffset(-0.2)">.2s</button>
            <button class="nudge-btn" onclick="adjustOffset(-0.1)">.1s</button>
            <button class="nudge-btn" onclick="adjustOffset(0.1)">.1s</button>
            <button class="nudge-btn" onclick="adjustOffset(0.2)">.2s</button>
            <button class="nudge-btn" onclick="adjustOffset(0.5)">.5s</button>
            <button class="nudge-btn" onclick="adjustOffset(1.0)">1s</button>
          </div>
        </div>
      `;
    }
    updatePlayButtonIcon();
    updatePanelLockState();
  }

  function acceptSyncAsIs() {
    const now = (player && typeof player.getCurrentTime === "function") ? player.getCurrentTime() : 0;
    timeOffset = 0.0; isSynced = true; restoredFromCache = false;
    activeCaptionIdx = -1; previewCaptionIdx = -1;
    saveVideoSyncState(now); renderSyncBar(); renderCaptions(); updateRangeUI(); updatePlaybackHighlight(now, true);
  }

  function unsyncAll() {
    if (isRunning) return;
    stopSequence(); deleteVideoSyncState();
    isSynced = false; restoredFromCache = false; hasUserRange = false;
    cachedResumeTime = null; timeOffset = 0.0; activeCaptionIdx = -1; previewCaptionIdx = -1;
    renderSyncBar(); renderCaptions(); updateRangeUI();
    if (player && typeof player.getCurrentTime === "function") updatePlaybackHighlight(player.getCurrentTime(), false);
  }

  function adjustOffset(delta) {
    if (isRunning) return;
    const oldOffset = timeOffset;
    timeOffset = Math.round((timeOffset + delta) * 10) / 10;
    restoredFromCache = false;
    const diff = timeOffset - oldOffset;
    if (hasUserRange) {
      rangeStart = Math.max(0, rangeStart + diff);
      rangeEnd = Math.max(rangeStart + 0.5, rangeEnd + diff);
    }
    activeCaptionIdx = -1;
    saveVideoSyncState(); renderSyncBar(); renderCaptions(); updateRangeUI();
    if (player && typeof player.getCurrentTime === "function") updatePlaybackHighlight(player.getCurrentTime(), true);
  }

  function setStartBoundary(newStart) {
    if (isRunning) return;
    rangeStart = Math.max(0, newStart);
    if (!hasUserRange || rangeEnd <= rangeStart + 0.3) rangeEnd = Math.min(getMaxDuration(), rangeStart + DEFAULT_SPAN);
    hasUserRange = true;
    saveVideoSyncState(rangeStart); updatePanelLockState(); updateRangeUI(); renderStepsList();
  }

  function setEndBoundary(newEnd) {
    if (isRunning) return;
    rangeEnd = Math.max(0.5, newEnd);
    if (!hasUserRange || rangeStart >= rangeEnd - 0.3) rangeStart = Math.max(0, rangeEnd - DEFAULT_SPAN);
    hasUserRange = true;
    saveVideoSyncState(rangeStart); updatePanelLockState(); updateRangeUI(); renderStepsList();
  }

  function updateRangeUI() {
    if (!hasUserRange) {
      startValEl.textContent = "--:--.-";
      endValEl.textContent = "--:--.-";
    } else {
      startValEl.textContent = fmtTimePrecise(rangeStart);
      endValEl.textContent = fmtTimePrecise(rangeEnd);
    }
    highlightRangeCaptions();
    if (player && typeof player.getCurrentTime === "function") updateLocalScrubBar(player.getCurrentTime(), player.getDuration());
  }

  function highlightRangeCaptions() {
    let firstInRange = -1, lastInRange = -1;
    captions.forEach((item, idx) => {
      const el = document.getElementById("line-" + idx);
      if (!el) return;
      el.querySelector(".s-btn")?.classList.remove("is-start");
      el.querySelector(".e-btn")?.classList.remove("is-end");
      if (!hasUserRange) { el.classList.remove("in-range"); return; }
      const adjStart = item.start + timeOffset, adjEnd = item.end + timeOffset;
      const inRange = (adjEnd > rangeStart + 0.1) && (adjStart < rangeEnd - 0.1);
      el.classList.toggle("in-range", inRange);
      if (inRange) { if (firstInRange === -1) firstInRange = idx; lastInRange = idx; }
    });
    if (hasUserRange && firstInRange !== -1) {
      document.getElementById("line-" + firstInRange)?.querySelector(".s-btn")?.classList.add("is-start");
      document.getElementById("line-" + lastInRange)?.querySelector(".e-btn")?.classList.add("is-end");
    }
    updateNeighborClasses();
  }

  function updateNeighborClasses() {
    captions.forEach((_, idx) => {
      const el = document.getElementById("line-" + idx);
      if (el) el.classList.toggle("neighbor-line", activeCaptionIdx !== -1 && (idx === activeCaptionIdx - 1 || idx === activeCaptionIdx + 1));
    });
  }

  function renderCaptions() {
    listEl.innerHTML = "";
    if (!captions || captions.length === 0) {
      listEl.innerHTML = `
        <div class="no-captions-notice">
          <div style="font-size:20px;margin-bottom:6px;">🎧</div>
          <div><b>字幕なしモード (Audio Only)</b></div>
          <div style="font-size:12px;color:#64748b;margin-top:4px;">
            上のシークバーで位置を合わせ、<b>Mark start</b> / <b>Mark end</b> を押すとそのまま Run sequence を実行できます。<br/>
            字幕が必要な場合は上の <b>SRC</b> から <code>.srt</code> を選択するか、Whisper 自動文字起こしを使用してください。
          </div>
        </div>
      `;
      return;
    }
    captions.forEach((item, idx) => {
      const adjStart = item.start + timeOffset, adjEnd = item.end + timeOffset;
      const div = document.createElement("div");
      div.className = "caption-line" + (isSynced && idx === activeCaptionIdx ? " active" : "") + (!isSynced && idx === previewCaptionIdx ? " preview-active" : "");
      div.id = "line-" + idx;

      const mainDiv = document.createElement("div");
      mainDiv.className = "caption-main";
      mainDiv.innerHTML = `<span class="caption-time">${fmtTime(adjStart)}</span><span>${item.text}</span>`;
      mainDiv.onclick = () => {
        if (!player || !player.seekTo) return;
        const targetT = Math.max(0, adjStart);
        if (!isSynced) {
          const wasPlaying = (typeof player.getPlayerState === "function" && player.getPlayerState() === YT.PlayerState.PLAYING);
          player.seekTo(targetT, true);
          if (!wasPlaying && typeof player.pauseVideo === "function") player.pauseVideo();
          updatePlaybackHighlight(targetT, false);
        } else {
          player.seekTo(targetT, true);
          player.playVideo();
        }
      };

      const actions = document.createElement("div");
      actions.className = "line-actions";
      if (!isSynced) {
        const syncBtn = document.createElement("button");
        syncBtn.className = "tag-btn sync-line-btn"; syncBtn.textContent = "Sync";
        syncBtn.onclick = (e) => {
          e.stopPropagation();
          if (!player || typeof player.getCurrentTime !== "function") return;
          const now = player.getCurrentTime();
          timeOffset = Math.round((now - item.start) * 10) / 10;
          isSynced = true; restoredFromCache = false; activeCaptionIdx = -1; previewCaptionIdx = -1;
          saveVideoSyncState(now); renderSyncBar(); renderCaptions(); updateRangeUI(); updatePlaybackHighlight(now, true);
        };
        actions.appendChild(syncBtn);
      } else {
        const startBtn = document.createElement("button");
        startBtn.className = "tag-btn s-btn"; startBtn.textContent = "S";
        startBtn.onclick = (e) => { e.stopPropagation(); setStartBoundary(adjStart); };
        const endBtn = document.createElement("button");
        endBtn.className = "tag-btn e-btn"; endBtn.textContent = "E";
        endBtn.onclick = (e) => { e.stopPropagation(); setEndBoundary(adjEnd); };
        actions.appendChild(startBtn); actions.appendChild(endBtn);
      }
      div.appendChild(mainDiv); div.appendChild(actions); listEl.appendChild(div);
    });
    highlightRangeCaptions();
  }

  function getLatestVasForStep(stepNum) {
    for (let i = trialLogs.length - 1; i >= 0; i--) {
      const r = trialLogs[i];
      if (r.VideoID === videoId && r.StepIdx === stepNum && Math.abs(r.StartTime - Number(rangeStart.toFixed(2))) < 0.2) return r.VAS_Clarity;
    }
    return null;
  }

  function renderStepsList() {
    stepsListEl.innerHTML = "";
    document.getElementById("step-counter").textContent = `${steps.length} steps`;
    steps.forEach((stItem, idx) => {
      const isCurrent = isRunning && idx === currentStepIdx;
      const row = document.createElement("div");
      row.className = "step-item" + (isCurrent ? " current-step" : "");
      row.id = "step-row-" + idx;
      const loggedVas = hasUserRange ? getLatestVasForStep(idx + 1) : null;
      const vasBadge = loggedVas !== null ? `<span class="step-vas-pill">${loggedVas}%</span>` : `<span></span>`;
      const spinDur = (1.2 / stItem.speed).toFixed(2) + "s";
      const rightAction = isCurrent
        ? `<img src="__SHURIKEN_DATA_URI__" class="step-shuriken${awaitingVas ? ' paused' : ''}" style="--spin-dur:${spinDur};width:18px;height:18px;" alt="" aria-hidden="true" />`
        : `<span style="font-size:11px;color:#64748b;text-align:right;">Tap to jump</span>`;
      row.innerHTML = `<span class="step-num">${idx + 1}</span><span class="step-speed">${stItem.speed.toFixed(1)}x</span><span class="${stItem.cc ? 'step-cc-on' : 'step-cc-off'}">${stItem.cc ? 'CC on' : 'CC off'}</span>${rightAction}${vasBadge}`;
      row.onclick = () => { runSequence(idx); };
      stepsListEl.appendChild(row);
    });
  }

  function setCCVisibility(showCC) {
    if (showCC) areaEl.classList.remove("mode-off");
    else {
      areaEl.classList.add("mode-off");
      blindStepLabel.textContent = (isRunning && currentStepIdx >= 0)
        ? `Step ${currentStepIdx + 1}/${steps.length} (${steps[currentStepIdx].speed.toFixed(1)}x) — CC OFF`
        : "CC OFF — Listen carefully";
    }
  }

  function markStartNow() { if (player && typeof player.getCurrentTime === "function") setStartBoundary(player.getCurrentTime()); }
  function markEndNow() { if (player && typeof player.getCurrentTime === "function") setEndBoundary(player.getCurrentTime()); }

  function moveToNextFragment() {
    if (!isSynced || !hasUserRange || isRunning) return;
    stopSequence();
    rangeStart = rangeEnd;
    rangeEnd = Math.min(getMaxDuration(), rangeStart + DEFAULT_SPAN);
    hasUserRange = true;
    saveVideoSyncState(rangeStart); updatePanelLockState(); updateRangeUI(); renderStepsList();
    if (player && player.seekTo) { player.seekTo(rangeStart, true); player.playVideo(); }
  }

  function runSequence(startIdx = 0) {
    if (!player || steps.length === 0 || !isSynced || !hasUserRange) return;
    awaitingVas = false; vasDrawerEl.classList.remove("open");
    isRunning = true; areaEl.classList.add("training-active");
    setStepsCollapsedPortrait(true); updatePanelLockState(); applyStep(startIdx);
  }

  function applyStep(idx) {
    if (idx >= steps.length) {
      isRunning = false; awaitingVas = false; vasDrawerEl.classList.remove("open"); currentStepIdx = -1;
      areaEl.classList.remove("training-active"); setStepsCollapsedPortrait(false);
      player.pauseVideo(); player.setPlaybackRate(1.0); setCCVisibility(true);
      updatePanelLockState(); statusBadge.textContent = "Completed!"; renderStepsList();
      return;
    }
    currentStepIdx = idx;
    const step = steps[idx];
    stepTransitionLock = true;
    player.setPlaybackRate(step.speed); setCCVisibility(step.cc);
    statusBadge.textContent = `Step ${idx + 1}/${steps.length} (${step.speed.toFixed(1)}x ${step.cc ? 'CC ON' : 'CC OFF'})`;
    renderStepsList();
    const activeRow = document.getElementById("step-row-" + idx);
    if (activeRow && !stepsCollapsedPortrait) activeRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
    player.seekTo(rangeStart, true); player.playVideo(); updatePlaybackHighlight(rangeStart, true);
    setTimeout(() => { stepTransitionLock = false; }, 350);
  }

  function stopSequence() {
    isRunning = false; awaitingVas = false; vasDrawerEl.classList.remove("open"); currentStepIdx = -1;
    areaEl.classList.remove("training-active"); setStepsCollapsedPortrait(false);
    if (player && typeof player.pauseVideo === "function") { player.pauseVideo(); player.setPlaybackRate(1.0); }
    setCCVisibility(true); updatePanelLockState(); renderStepsList();
    if (activeCaptionIdx !== -1) document.getElementById("line-" + activeCaptionIdx)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const hadCachedSync = restoreVideoSyncState();
  renderProtocolDropdown(); setTrainingView(trainingView); renderSyncBar(); renderCaptions(); renderStepsList(); updateRangeUI(); updateLogPill();

  areaEl.addEventListener("touchstart", () => { userScrolling = true; clearTimeout(scrollTimeout); }, { passive: true });
  areaEl.addEventListener("touchend", () => { clearTimeout(scrollTimeout); scrollTimeout = setTimeout(() => { userScrolling = false; }, 3000); }, { passive: true });

  function initLocalAudioPlayer() {
    const wrapEl = document.getElementById("player-wrap");
    const ytDiv = document.getElementById("yt-player");
    const localBox = document.getElementById("local-audio-box");
    const titleEl = document.getElementById("local-audio-title");
    const trackEl = document.getElementById("local-scrub-track");

    if (wrapEl) wrapEl.classList.add("local-mode");
    if (ytDiv) ytDiv.style.display = "none";
    if (localBox) localBox.style.display = "block";
    if (titleEl) titleEl.textContent = localTitle || "Local Audio";

    const audio = new Audio(localAudioDataUri);
    audio.preload = "metadata";
    audio.preservesPitch = true; audio.mozPreservesPitch = true; audio.webkitPreservesPitch = true;

    player = {
      playVideo: () => { audio.play().catch(() => {}); },
      pauseVideo: () => { audio.pause(); },
      seekTo: (sec) => {
        const dur = (audio.duration && !isNaN(audio.duration)) ? audio.duration : sec;
        audio.currentTime = Math.max(0, Math.min(dur || sec, sec));
        updateLocalScrubBar(audio.currentTime, audio.duration);
      },
      getCurrentTime: () => audio.currentTime || 0,
      getDuration: () => (audio.duration && !isNaN(audio.duration)) ? audio.duration : 0,
      setPlaybackRate: (rate) => { audio.playbackRate = rate; audio.preservesPitch = true; audio.mozPreservesPitch = true; audio.webkitPreservesPitch = true; },
      getPlayerState: () => audio.ended ? YT.PlayerState.ENDED : (audio.paused ? YT.PlayerState.PAUSED : YT.PlayerState.PLAYING),
      getVideoData: () => ({ title: localTitle || videoId })
    };

    audio.addEventListener("play", updatePlayButtonIcon);
    audio.addEventListener("pause", updatePlayButtonIcon);
    audio.addEventListener("ended", () => {
      updatePlayButtonIcon();
      if (isRunning && !awaitingVas && !stepTransitionLock) {
        if (vasEnabled) promptVasForCurrentStep(); else applyStep(currentStepIdx + 1);
      }
    });
    audio.addEventListener("loadedmetadata", () => {
      if (hadCachedSync && cachedResumeTime !== null && cachedResumeTime > 0 && cachedResumeTime < audio.duration) audio.currentTime = cachedResumeTime;
      updateRangeUI(); updateLocalScrubBar(audio.currentTime, audio.duration); fitParentIframe();
    });

    let isScrubbing = false;
    function scrubFromClientX(clientX) {
      if (!trackEl || !audio.duration || isNaN(audio.duration)) return;
      const rect = trackEl.getBoundingClientRect();
      const targetT = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * audio.duration;
      audio.currentTime = targetT;
      updateLocalScrubBar(targetT, audio.duration);
      updatePlaybackHighlight(targetT, true);
    }

    if (trackEl) {
      trackEl.addEventListener("pointerdown", (e) => { if (isRunning) return; isScrubbing = true; trackEl.setPointerCapture(e.pointerId); scrubFromClientX(e.clientX); });
      trackEl.addEventListener("pointermove", (e) => { if (isScrubbing) scrubFromClientX(e.clientX); });
      trackEl.addEventListener("pointerup", () => { isScrubbing = false; });
      trackEl.addEventListener("pointercancel", () => { isScrubbing = false; });
    }
    fitParentIframe();
    setInterval(mainLoop, 100);
  }

  if (mediaMode === "local") {
    initLocalAudioPlayer();
  } else {
    const tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(tag);

    window.onYouTubeIframeAPIReady = function() {
      player = new YT.Player("yt-player", {
        videoId: videoId,
        playerVars: {
          playsinline: 1, controls: 0, iv_load_policy: 3, cc_load_policy: 0, rel: 0, modestbranding: 1,
          start: (hadCachedSync && cachedResumeTime !== null && cachedResumeTime > 0) ? Math.floor(cachedResumeTime) : 0
        },
        events: {
          onReady: () => {
            fitParentIframe();
            try { const data = player.getVideoData(); if (data && data.title) videoTitle = data.title; } catch (e) {}
            if (hadCachedSync && cachedResumeTime !== null && cachedResumeTime > 0) updatePlaybackHighlight(cachedResumeTime, true);
            else if (hadCachedSync) updatePlaybackHighlight(0, true);
            else updatePlaybackHighlight(0, false);
            setInterval(mainLoop, 100);
          },
          onStateChange: () => {
            updatePlayButtonIcon();
            try { const data = player.getVideoData(); if (data && data.title) videoTitle = data.title; } catch (e) {}
          }
        }
      });
    };
  }

  function findCaptionIndexAt(effectiveT) {
    let found = -1;
    for (let i = 0; i < captions.length; i++) {
      if (effectiveT >= captions[i].start && effectiveT < captions[i].end) { found = i; break; }
    }
    if (found === -1) {
      for (let i = captions.length - 1; i >= 0; i--) {
        if (effectiveT >= captions[i].start) { found = i; break; }
      }
    }
    return found;
  }

  function updatePlaybackHighlight(t, forceScroll = false) {
    if (!captions || captions.length === 0) return;
    if (!isSynced) {
      const found = findCaptionIndexAt(t);
      if (found !== previewCaptionIdx && found !== -1) {
        if (previewCaptionIdx !== -1) document.getElementById("line-" + previewCaptionIdx)?.classList.remove("preview-active");
        previewCaptionIdx = found;
        document.getElementById("line-" + previewCaptionIdx)?.classList.add("preview-active");
      }
      return;
    }
    const found = findCaptionIndexAt(t - timeOffset);
    if (found !== activeCaptionIdx && found !== -1) {
      if (activeCaptionIdx !== -1) document.getElementById("line-" + activeCaptionIdx)?.classList.remove("active");
      activeCaptionIdx = found;
      const cur = document.getElementById("line-" + activeCaptionIdx);
      if (cur) {
        cur.classList.add("active");
        updateNeighborClasses();
        if (!isRunning && (forceScroll || !userScrolling) && !areaEl.classList.contains("mode-off")) {
          cur.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    }
  }

  function mainLoop() {
    if (!player || typeof player.getCurrentTime !== "function") return;
    const t = player.getCurrentTime();
    const d = player.getDuration();
    const timeEl = document.getElementById("time-display");
    if (timeEl) timeEl.textContent = `${fmtTime(t)} / ${fmtTime(d)}`;
    if (mediaMode === "local") updateLocalScrubBar(t, d);

    if (isSynced && !isRunning && player.getPlayerState() === YT.PlayerState.PLAYING) {
      const wholeSec = Math.floor(t);
      if (Math.abs(wholeSec - lastSavedPlaybackSec) >= 3) {
        lastSavedPlaybackSec = wholeSec;
        saveVideoSyncState(t);
      }
    }
    if (isRunning && !awaitingVas && !stepTransitionLock && player.getPlayerState() === YT.PlayerState.PLAYING) {
      if (t >= rangeEnd) {
        if (vasEnabled) promptVasForCurrentStep(); else applyStep(currentStepIdx + 1);
        return;
      }
    }
    updatePlaybackHighlight(t, false);
  }

  function openPlotModal() { document.getElementById("plot-modal").classList.add("open"); renderDarkVasPlot(); }
  function closePlotModal() { document.getElementById("plot-modal").classList.remove("open"); }
  function clearTrialLogs() { trialLogs = trialLogs.filter(r => r.VideoID !== videoId); saveTrialLogs(); renderStepsList(); renderDarkVasPlot(); }

  function renderDarkVasPlot() {
    const canvas = document.getElementById("vas-plot-canvas");
    const emptyMsg = document.getElementById("plot-empty-msg");
    const titleEl = document.getElementById("plot-modal-title");
    const rows = trialLogs.filter(r => r.VideoID === videoId);
    titleEl.textContent = `VAS Clarity & Speed — ${videoTitle} (${rows.length} trials)`;
    if (rows.length === 0) { canvas.style.display = "none"; emptyMsg.style.display = "block"; return; }
    canvas.style.display = "block"; emptyMsg.style.display = "none";

    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    const bgCol = "#181818", clarityCol = "#ff00cc", speedCol = "#00d2ff", edgeCol = "#ffffff", axisCol = "#444444";
    ctx.fillStyle = bgCol; ctx.fillRect(0, 0, W, H);

    const padL = 82, padR = 82, padT = 56, padB = 52;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const yClarityToPx = (c) => padT + plotH * (1 - (c - (-5)) / (105 - (-5)));
    const ySpeedToPx = (s) => padT + plotH * (1 - (s - (-0.1)) / (2.1 - (-0.1)));
    const xIdxToPx = (i) => rows.length === 1 ? (padL + plotW / 2) : (padL + (plotW * i) / (rows.length - 1));

    ctx.font = "bold 14px -apple-system, BlinkMacSystemFont, Arial, sans-serif";
    ctx.textBaseline = "middle";
    ctx.fillStyle = clarityCol; ctx.strokeStyle = edgeCol; ctx.lineWidth = 2.0;
    ctx.beginPath(); ctx.arc(padL + 10, 24, 5.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillText("Subtitles ON", padL + 22, 24);

    const leg2X = padL + 175;
    ctx.fillStyle = bgCol; ctx.beginPath(); ctx.arc(leg2X, 24, 5.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = clarityCol; ctx.fillText("Subtitles OFF", leg2X + 12, 24);

    const leg3X = W - padR - 95;
    ctx.fillStyle = speedCol; ctx.fillRect(leg3X - 5, 19, 10, 10); ctx.fillText("Speed", leg3X + 12, 24);

    [0, 50, 100].forEach((val) => {
      const y = yClarityToPx(val);
      ctx.save(); ctx.strokeStyle = val === 50 ? "#444444" : "#333333"; ctx.lineWidth = 1.4; ctx.setLineDash([6, 5]);
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke(); ctx.restore();
    });

    ctx.strokeStyle = axisCol; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(padL, padT); ctx.lineTo(padL, padT + plotH); ctx.lineTo(W - padR, padT + plotH); ctx.lineTo(W - padR, padT); ctx.stroke();

    ctx.fillStyle = clarityCol; ctx.font = "bold 13px -apple-system, BlinkMacSystemFont, Arial, sans-serif"; ctx.textAlign = "right";
    [0, 50, 100].forEach((val) => ctx.fillText(`${val}%`, padL - 10, yClarityToPx(val)));
    ctx.save(); ctx.translate(22, padT + plotH / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = "center"; ctx.font = "bold 15px -apple-system, BlinkMacSystemFont, Arial, sans-serif"; ctx.fillText("Clarity", 0, 0); ctx.restore();

    ctx.fillStyle = speedCol; ctx.font = "bold 13px -apple-system, BlinkMacSystemFont, Arial, sans-serif"; ctx.textAlign = "left";
    [[0.0, "0x"], [1.0, "1.0x"], [2.0, "2.0x"]].forEach(([val, lbl]) => ctx.fillText(lbl, W - padR + 10, ySpeedToPx(val)));
    ctx.save(); ctx.translate(W - 22, padT + plotH / 2); ctx.rotate(Math.PI / 2); ctx.textAlign = "center"; ctx.font = "bold 15px -apple-system, BlinkMacSystemFont, Arial, sans-serif"; ctx.fillText("Speed", 0, 0); ctx.restore();

    ctx.fillStyle = "#aaaaaa"; ctx.font = "bold 12px -apple-system, BlinkMacSystemFont, Arial, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "top";
    const labelStep = rows.length > 22 ? Math.ceil(rows.length / 18) : 1;
    rows.forEach((r, i) => {
      const x = xIdxToPx(i);
      ctx.strokeStyle = axisCol; ctx.beginPath(); ctx.moveTo(x, padT + plotH); ctx.lineTo(x, padT + plotH + 5); ctx.stroke();
      if (i % labelStep === 0 || i === rows.length - 1) ctx.fillText(String(i + 1), x, padT + plotH + 9);
    });

    ctx.save(); ctx.strokeStyle = speedCol; ctx.lineWidth = 2.5; ctx.setLineDash([7, 5]);
    ctx.beginPath(); rows.forEach((r, i) => { const x = xIdxToPx(i), y = ySpeedToPx(r.PlaybackRate); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }); ctx.stroke(); ctx.restore();

    ctx.fillStyle = speedCol;
    rows.forEach((r, i) => { const x = xIdxToPx(i), y = ySpeedToPx(r.PlaybackRate); ctx.fillRect(x - 4.5, y - 4.5, 9, 9); });

    ctx.strokeStyle = clarityCol; ctx.lineWidth = 3.2;
    ctx.beginPath(); rows.forEach((r, i) => { const x = xIdxToPx(i), y = yClarityToPx(r.VAS_Clarity); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }); ctx.stroke();

    rows.forEach((r, i) => {
      const x = xIdxToPx(i), y = yClarityToPx(r.VAS_Clarity);
      ctx.beginPath(); ctx.arc(x, y, 6.2, 0, Math.PI * 2);
      ctx.fillStyle = r.Subtitles ? clarityCol : bgCol; ctx.strokeStyle = edgeCol; ctx.lineWidth = 2.0; ctx.fill(); ctx.stroke();
    });
  }

  function downloadPlotPng() {
    const canvas = document.getElementById("vas-plot-canvas");
    if (!canvas || canvas.style.display === "none") return;
    const safeTitle = (videoTitle || videoId).replace(/[^a-zA-Z0-9 _-]/g, "_").slice(0, 36).trim();
    const link = document.createElement("a"); link.download = `ninja_${safeTitle}_${Date.now()}_plot.png`; link.href = canvas.toDataURL("image/png"); link.click();
  }

  function csvEscape(val) {
    const str = String(val ?? "");
    return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
  }

  function exportLogsCsv() {
    const rows = trialLogs.filter(r => r.VideoID === videoId);
    if (rows.length === 0) return;
    const headers = ["SubjectID", "Timestamp", "VideoID", "StartTime", "EndTime", "StepIdx", "PlaybackRate", "Subtitles", "VAS_Clarity", "URL", "Title", "Protocol"];
    const lines = [headers.join(",")];
    rows.forEach((r) => {
      lines.push(headers.map((h) => h === "Subtitles" ? (r.Subtitles ? "True" : "False") : (h === "PlaybackRate" ? Number(r.PlaybackRate).toFixed(1) : csvEscape(r[h]))).join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const safeTitle = (videoTitle || videoId).replace(/[^a-zA-Z0-9 _-]/g, "_").slice(0, 36).trim();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `ninja_${safeTitle}_${Date.now()}.csv`; a.click(); URL.revokeObjectURL(url);
  }

  let draftSteps = [], editingCustomId = null;

  function openModal(createNew = false) {
    if (isRunning) return;
    const nameInput = document.getElementById("custom-seq-name");
    const delBtn = document.getElementById("del-custom-btn");
    if (!createNew && customProtocols[selectedProtocolId]) {
      editingCustomId = selectedProtocolId; nameInput.value = customProtocols[selectedProtocolId].name; delBtn.style.display = "inline-block";
    } else {
      editingCustomId = null; nameInput.value = createNew ? "Custom Sequence" : `${getProtocolById(selectedProtocolId).name} (Custom)`; delBtn.style.display = "none";
    }
    draftSteps = steps.map(s => ({ ...s }));
    renderModalBody();
    document.getElementById("cfg-modal").classList.add("open");
  }

  function closeModal() { document.getElementById("cfg-modal").classList.remove("open"); }

  function renderModalBody() {
    const body = document.getElementById("modal-steps-body");
    body.innerHTML = "";
    draftSteps.forEach((stItem, idx) => {
      const r = document.createElement("div"); r.className = "edit-row";
      r.innerHTML = `<span>${idx + 1}</span><input type="number" step="0.1" min="0.25" max="2.0" value="${stItem.speed}" onchange="draftSteps[${idx}].speed = parseFloat(this.value) || 1.0" /><label><input type="checkbox" ${stItem.cc ? "checked" : ""} onchange="draftSteps[${idx}].cc = this.checked" /> CC</label><div style="text-align:right;"><button class="nudge-btn" onclick="moveDraft(${idx}, -1)">↑</button><button class="nudge-btn" onclick="moveDraft(${idx}, 1)">↓</button><button class="nudge-btn" onclick="delDraft(${idx})">✕</button></div>`;
      body.appendChild(r);
    });
  }

  function moveDraft(idx, dir) { const t = idx + dir; if (t >= 0 && t < draftSteps.length) { [draftSteps[idx], draftSteps[t]] = [draftSteps[t], draftSteps[idx]]; renderModalBody(); } }
  function delDraft(idx) { draftSteps.splice(idx, 1); renderModalBody(); }
  function addStepRow() { draftSteps.push({ speed: 1.0, cc: false }); renderModalBody(); }
  function resetDraftToSelected() { draftSteps = getProtocolById(selectedProtocolId).steps.map(s => ({ ...s })); renderModalBody(); }

  function saveModalSteps() {
    if (draftSteps.length === 0) return;
    const seqName = document.getElementById("custom-seq-name").value.trim() || "Custom Sequence";
    const targetId = editingCustomId || ("custom_" + Date.now());
    customProtocols[targetId] = { name: seqName, shortKey: seqName.toLowerCase().replace(/[^a-z0-9]+/g, "_"), steps: draftSteps.map(s => ({ ...s })) };
    saveCustomProtocols(customProtocols);
    selectedProtocolId = targetId; localStorage.setItem(SELECTED_PROTOCOL_KEY, selectedProtocolId);
    steps = customProtocols[targetId].steps.map(s => ({ ...s }));
    renderProtocolDropdown(); renderStepsList(); closeModal();
  }

  function deleteCurrentCustomProtocol() {
    if (!editingCustomId || !customProtocols[editingCustomId]) return;
    delete customProtocols[editingCustomId]; saveCustomProtocols(customProtocols);
    selectedProtocolId = "anchor_06"; localStorage.setItem(SELECTED_PROTOCOL_KEY, selectedProtocolId);
    steps = getProtocolById(selectedProtocolId).steps.map(s => ({ ...s }));
    renderProtocolDropdown(); renderStepsList(); closeModal();
  }
</script>
</body>
</html>
"""


def build_player_html(
    video_id: str,
    captions: list[dict],
    source_url: str,
    media_mode: str = "youtube",
    local_audio_uri: str = "",
    local_title: str = "",
    initial_synced: bool = False,
) -> str:
    safe_captions = json.dumps(captions, ensure_ascii=False).replace("</", "<\\/")
    safe_vid = json.dumps(video_id).replace("</", "<\\/")
    safe_url = json.dumps(source_url, ensure_ascii=False).replace("</", "<\\/")
    safe_mode = json.dumps(media_mode)
    safe_audio_uri = json.dumps(local_audio_uri).replace("</", "<\\/")
    safe_title = json.dumps(local_title, ensure_ascii=False).replace("</", "<\\/")
    safe_init_synced = "true" if initial_synced else "false"
    shuriken_icon = get_ice_shuriken_img_tag(size_px=16, extra_class="ninja-spin-hover")
    shuriken_uri = f"data:image/png;base64,{_ICE_SHURIKEN_B64}" if _ICE_SHURIKEN_B64 else ""
    return (
        HTML_TEMPLATE
        .replace("__CAPTIONS_JSON__", safe_captions)
        .replace("__VIDEO_ID_JSON__", safe_vid)
        .replace("__SOURCE_URL_JSON__", safe_url)
        .replace("__MEDIA_MODE_JSON__", safe_mode)
        .replace("__LOCAL_AUDIO_URI_JSON__", safe_audio_uri)
        .replace("__LOCAL_TITLE_JSON__", safe_title)
        .replace("__INITIAL_SYNCED_JSON__", safe_init_synced)
        .replace("__RUN_SEQ_SHURIKEN__", shuriken_icon)
        .replace("__SHURIKEN_DATA_URI__", shuriken_uri)
    )


def render_ninja_listening() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stTextInput"] {
            margin-bottom: -0.35rem !important;
        }
        iframe {
            display: block;
            width: 100% !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "ninja_local_whisper_cache" not in st.session_state:
        st.session_state["ninja_local_whisper_cache"] = {}

    default_v = (
        st.query_params.get("v", "")
        or st.session_state.get("ninja_last_video_id", "")
    )

    if not default_v and not st.session_state.get("ninja_local_audio_input"):
        components.html(
            """
            <script>
            try {
              const savedVid = localStorage.getItem("ninja_last_video_id_v1");
              if (savedVid && /^[A-Za-z0-9_-]{11}$/.test(savedVid) && window.parent) {
                const u = new URL(window.parent.location.href);
                if (!u.searchParams.get("v")) {
                  u.searchParams.set("v", savedVid);
                  u.searchParams.set("mode", "LISTENING");
                  window.parent.location.replace(u.toString());
                }
              }
            } catch (e) {}
            </script>
            """,
            height=0,
        )

    default_url = f"https://youtu.be/{default_v}" if default_v else ""

    url = st.text_input(
        "YouTube URL",
        value=default_url,
        placeholder="YouTube URL を貼り付け...",
        label_visibility="collapsed",
        key="ninja_listening_url_input",
    )

    st.markdown(
        """
        <div id="ninja-or-divider" style="display:flex;align-items:center;gap:16px;margin:20px 0 26px 0;">
          <div style="flex:1;height:2px;background:#334155;"></div>
          <span style="font-size:28px;font-weight:900;letter-spacing:0.15em;color:#f8fafc;background:#1e293b;padding:4px 22px;border:2px solid #38bdf8;border-radius:999px;line-height:1.1;">OR</span>
          <div style="flex:1;height:2px;background:#334155;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    loc_col1, loc_col2 = st.columns([1.45, 1.0])
    with loc_col1:
        local_audio_file = st.file_uploader(
            "Local audio file (WAV / MP3 / M4A / OGG / FLAC)",
            type=["wav", "mp3", "m4a", "ogg", "flac"],
            key="ninja_local_audio_input",
        )
    with loc_col2:
        local_srt_file = st.file_uploader(
            "Subtitle file (.srt, optional)",
            type=["srt"],
            key="ninja_local_srt_input",
        )

    # Mode A: Local Audio File
    if local_audio_file is not None:
        audio_bytes = local_audio_file.getvalue()
        audio_hash = hashlib.sha256(audio_bytes).hexdigest()[:12]
        local_id = f"local_{audio_hash}"
        mime = _detect_audio_mime(local_audio_file.name)
        audio_data_uri = f"data:{mime};base64,{base64.b64encode(audio_bytes).decode('ascii')}"

        captions: list[dict] = []
        caption_source = ""

        if local_srt_file is not None:
            try:
                raw_srt = local_srt_file.getvalue().decode("utf-8", errors="replace")
                captions = parse_srt_text(raw_srt)
                caption_source = f"SRT: {local_srt_file.name} ({len(captions)} lines)"
            except Exception as e:
                st.warning(f"SRTの読み込みに失敗しました: {e}")
        elif local_id in st.session_state["ninja_local_whisper_cache"]:
            captions = st.session_state["ninja_local_whisper_cache"][local_id]
            caption_source = f"Whisper 字幕 ({len(captions)} lines)"

        if not captions:
            backend_id, backend_label = get_available_whisper_backend()
            if backend_id:
                w_col1, w_col2 = st.columns([2.0, 2.5], vertical_alignment="center")
                with w_col1:
                    if st.button(
                        f"音声から字幕を自動生成 ({backend_label})",
                        key=f"whisper_btn_{local_id}",
                        type="primary",
                        use_container_width=True,
                    ):
                        if len(audio_bytes) > 24 * 1024 * 1024 and backend_id in ("groq", "openai"):
                            st.error("API上限 (25MB) を超えています。MP3/M4A へ圧縮するか短い区間を使用してください。")
                        else:
                            try:
                                with st.spinner(f"{backend_label} で文字起こし中..."):
                                    gen_caps, _ = transcribe_audio_hybrid(audio_bytes, local_audio_file.name)
                                if gen_caps:
                                    st.session_state["ninja_local_whisper_cache"][local_id] = gen_caps
                                    st.rerun()
                                else:
                                    st.warning("音声からテキストを検出できませんでした。")
                            except urllib.error.HTTPError as e:
                                err_body = e.read().decode("utf-8", errors="replace")
                                st.error(f"Whisper API Error (HTTP {e.code}): {err_body}")
                            except Exception as e:
                                st.error(f"文字起こしに失敗しました: {e}")
                with w_col2:
                    st.caption("※ 字幕なしのまま下の水平バー＆Mark start/end でトレーニングすることも可能です。")
            else:
                st.caption("💡 字幕を付けるには `.srt` を選択するか、Secrets に `GROQ_API_KEY` / `OPENAI_API_KEY`（またはローカル `faster-whisper`）を設定してください。")
        else:
            st.caption(f"✅ {caption_source}")

        components.html(
            build_player_html(
                video_id=local_id,
                captions=captions,
                source_url=f"local://{local_audio_file.name}",
                media_mode="local",
                local_audio_uri=audio_data_uri,
                local_title=local_audio_file.name,
                initial_synced=True,
            ),
            height=680,
            scrolling=False,
        )
        return

    # Mode B: YouTube URL
    if url:
        vid = extract_video_id(url)
        if not vid:
            st.error("有効なYouTube URLではありません。")
            return

        if st.query_params.get("v") != vid:
            st.query_params["v"] = vid
        st.session_state["ninja_last_video_id"] = vid

        captions = load_cached_transcript(vid)
        if captions is None:
            try:
                with st.spinner("字幕取得中..."):
                    captions = fetch_transcript(vid)
                if captions:
                    save_cached_transcript(vid, captions)
            except Exception as e:
                st.error(f"字幕を取得できませんでした: {e}")
                return

        components.html(
            build_player_html(
                video_id=vid,
                captions=captions,
                source_url=url.strip(),
                media_mode="youtube",
                initial_synced=False,
            ),
            height=680,
            scrolling=False,
        )