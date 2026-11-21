import json
import re
import streamlit as st
import streamlit.components.v1 as components
from youtube_transcript_api import YouTubeTranscriptApi

st.set_page_config(
    page_title="Ninja Listening Trainer",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 100% !important;
        padding-top: 0.45rem !important;
        padding-bottom: 0.2rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    header[data-testid="stHeader"] { display: none; }
    div[data-testid="stTextInput"] {
        margin-bottom: -0.5rem !important;
    }
    iframe {
        display: block;
        width: 100% !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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
    """Merge fragmented YouTube captions into cleaner sentence/clause lines."""
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


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_transcript(video_id: str, merge_sentences: bool = True, languages: tuple = ("en", "en-US", "en-GB")) -> list[dict]:
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
    return merge_into_sentences(items) if merge_sentences else items


def build_player_html(video_id: str, captions: list[dict]) -> str:
    captions_json = json.dumps(captions, ensure_ascii=False)
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<style>
  :root {{
    --bg: #0f172a;
    --panel: #0b1120;
    --card: #1e293b;
    --accent: #2ba2bd;
    --danger: #ef4444;
    --text: #e2e8f0;
    --muted: #64748b;
  }}
  * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
  html, body {{
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", Arial, sans-serif;
    overflow: hidden;
  }}

  .app-shell {{
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100%;
    overflow: hidden;
  }}
  .video-section {{
    background: #020617;
    flex-shrink: 0;
  }}
  .player-wrap {{
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    max-height: 205px;
    background: #000;
  }}
  .player-wrap iframe {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }}

  /* Meta & Sync Calibration Bar */
  .meta-bar {{
    display: flex;
    flex-direction: column;
    padding: 4px 8px;
    background: var(--panel);
    border-bottom: 1px solid #1e293b;
    font-size: 11px;
    flex-shrink: 0;
    gap: 4px;
  }}
  .meta-top {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    min-height: 22px;
  }}
  .time-display {{
    color: #94a3b8;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }}
  .unsync-hint {{
    color: #fbbf24;
    font-size: 11px;
    font-weight: 600;
  }}
  .unsync-btn {{
    background: rgba(251, 191, 36, 0.14);
    color: #fbbf24;
    border: 1px solid rgba(251, 191, 36, 0.4);
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 10.5px;
    font-weight: 600;
    cursor: pointer;
  }}
  .offset-badge {{
    color: #38bdf8;
    font-weight: 700;
    padding: 0 5px;
    font-variant-numeric: tabular-nums;
    font-size: 11px;
  }}
  .sync-nudge-grid {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
  }}
  .nudge-group {{
    display: flex;
    align-items: center;
    gap: 3px;
  }}
  .group-label {{
    font-size: 10px;
    color: #94a3b8;
    white-space: nowrap;
    margin-right: 1px;
  }}
  .group-label.lag {{ color: #38bdf8; }}
  .group-label.lead {{ color: #a78bfa; }}
  .nudge-btn {{
    background: var(--card);
    color: var(--text);
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 10.5px;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
  }}
  .nudge-btn:active {{
    background: var(--accent);
    color: #fff;
  }}

  /* Quiet, Low-Distraction Transcript Area */
  .transcript-area {{
    flex: 1.15;
    overflow-y: auto;
    padding: 4px 6px;
    scroll-behavior: smooth;
    position: relative;
    border-bottom: 1px solid #1e293b;
    min-height: 0;
    background: #0b1120;
  }}
  .caption-line {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    padding: 6px 8px;
    margin: 0;
    background: transparent;
    border-bottom: 1px solid rgba(148, 163, 184, 0.07);
    font-size: 14px;
    line-height: 1.45;
    cursor: pointer;
    border-left: 3px solid transparent;
    transition: background 0.12s;
  }}
  .caption-line:last-child {{
    border-bottom: none;
  }}
  .caption-line.in-range {{
    background: rgba(56, 189, 248, 0.09);
    border-left-color: rgba(56, 189, 248, 0.55);
  }}
  .caption-line.active {{
    background: rgba(43, 162, 189, 0.22);
    border-left-color: #2ba2bd;
    color: #ffffff;
    font-weight: 600;
  }}
  .caption-main {{
    flex: 1;
    min-width: 0;
  }}
  .caption-time {{
    font-size: 10.5px;
    color: var(--muted);
    margin-right: 6px;
    font-variant-numeric: tabular-nums;
  }}
  .line-actions {{
    display: flex;
    gap: 3px;
    flex-shrink: 0;
    align-self: center;
  }}
  .tag-btn {{
    background: transparent;
    color: #64748b;
    border: 1px solid rgba(100, 116, 139, 0.28);
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 10px;
    cursor: pointer;
  }}
  .caption-line.active .tag-btn,
  .caption-line.in-range .tag-btn {{
    color: #cbd5e1;
    border-color: rgba(148, 163, 184, 0.4);
  }}
  .tag-btn.sync-line-btn {{
    background: rgba(251, 191, 36, 0.14);
    color: #fbbf24;
    border-color: rgba(251, 191, 36, 0.45);
    font-weight: 600;
    padding: 2px 7px;
  }}
  .tag-btn:active {{
    background: var(--accent);
    color: #fff;
  }}

  .mode-off .caption-list {{ display: none; }}
  .blind-notice {{
    display: none;
    height: 100%;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    color: #94a3b8;
    text-align: center;
    font-size: 13px;
    gap: 4px;
  }}
  .mode-off .blind-notice {{ display: flex; }}

  /* Ninja Controls + Steps */
  .ninja-panel {{
    flex: 1;
    background: var(--panel);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 6px 8px 8px;
    gap: 5px;
    min-height: 0;
  }}
  .ninja-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
    font-weight: 700;
    color: #e2e8f0;
    flex-shrink: 0;
  }}
  .status-badge {{
    font-size: 11px;
    font-weight: 600;
    color: #38bdf8;
    background: rgba(56, 189, 248, 0.12);
    padding: 2px 8px;
    border-radius: 999px;
  }}
  .range-row {{
    display: grid;
    grid-template-columns: 1fr 1fr auto;
    gap: 5px;
    align-items: center;
    flex-shrink: 0;
  }}
  .mark-box {{
    display: flex;
    align-items: center;
    background: var(--card);
    border: 1px solid #334155;
    border-radius: 6px;
    overflow: hidden;
  }}
  .mark-btn {{
    background: #2563eb;
    color: #fff;
    border: none;
    padding: 5px 7px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }}
  .mark-val {{
    flex: 1;
    text-align: center;
    font-size: 11.5px;
    font-variant-numeric: tabular-nums;
    color: #f8fafc;
    padding: 0 3px;
  }}
  .next-btn {{
    background: var(--card);
    color: var(--text);
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }}
  .run-row {{
    display: grid;
    grid-template-columns: 1.4fr 1fr auto;
    gap: 5px;
    flex-shrink: 0;
  }}
  .run-btn {{
    background: #2563eb;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 7px;
    font-size: 12.5px;
    font-weight: 700;
    cursor: pointer;
  }}
  .stop-btn {{
    background: var(--danger);
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 7px;
    font-size: 12.5px;
    font-weight: 700;
    cursor: pointer;
  }}
  .cfg-btn {{
    background: var(--card);
    color: var(--text);
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 12.5px;
    cursor: pointer;
  }}
  .steps-header {{
    font-size: 10px;
    font-weight: 700;
    color: var(--muted);
    letter-spacing: 0.04em;
    display: flex;
    justify-content: space-between;
    flex-shrink: 0;
  }}
  .steps-list {{
    flex: 1;
    overflow-y: auto;
    border: 1px solid #1e293b;
    border-radius: 6px;
    background: #020617;
    min-height: 0;
  }}
  .step-item {{
    display: grid;
    grid-template-columns: 26px 50px 60px 1fr;
    align-items: center;
    padding: 5px 8px;
    border-bottom: 1px solid #1e293b;
    font-size: 12px;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
  }}
  .step-item:last-child {{ border-bottom: none; }}
  .step-item.current-step {{
    background: rgba(43, 162, 189, 0.28);
    color: #fff;
    font-weight: 700;
  }}
  .step-num {{ color: var(--muted); }}
  .step-speed {{ color: #f8fafc; font-weight: 600; }}
  .step-cc-on {{ color: #38bdf8; font-weight: 600; }}
  .step-cc-off {{ color: #64748b; }}

  /* Landscape & Desktop Split-Pane */
  @media (min-width: 640px) and (orientation: landscape) {{
    .app-shell {{
      display: grid;
      grid-template-columns: minmax(340px, 46%) 1fr;
      grid-template-rows: auto 1fr;
      grid-template-areas:
        "video transcript"
        "ninja transcript";
      height: 100vh;
    }}
    .video-section {{
      grid-area: video;
      border-right: 1px solid #1e293b;
    }}
    .player-wrap {{
      max-height: min(35vh, 290px);
    }}
    .ninja-panel {{
      grid-area: ninja;
      border-right: 1px solid #1e293b;
      padding: 5px 8px 6px;
      gap: 4px;
    }}
    .transcript-area {{
      grid-area: transcript;
      border-bottom: none;
      height: 100%;
      padding: 6px 10px;
    }}
  }}

  /* Protocol Modal */
  .modal-backdrop {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.75);
    z-index: 50;
    align-items: center;
    justify-content: center;
    padding: 12px;
  }}
  .modal-backdrop.open {{ display: flex; }}
  .modal-box {{
    background: #1e293b;
    border: 1px solid #475569;
    border-radius: 10px;
    width: 100%;
    max-width: 460px;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  .modal-head {{
    padding: 10px 12px;
    font-weight: 700;
    font-size: 14px;
    border-bottom: 1px solid #334155;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .modal-body {{
    padding: 8px 12px;
    overflow-y: auto;
    flex: 1;
  }}
  .edit-row {{
    display: grid;
    grid-template-columns: 24px 70px 60px 1fr;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
    font-size: 12px;
  }}
  .edit-row input[type="number"] {{
    width: 100%;
    background: #0f172a;
    color: #fff;
    border: 1px solid #475569;
    border-radius: 4px;
    padding: 4px;
  }}
  .modal-foot {{
    padding: 8px 12px;
    border-top: 1px solid #334155;
    display: flex;
    gap: 6px;
    justify-content: flex-end;
  }}
</style>
</head>
<body>

<div class="app-shell">
  <!-- 1. Video + Sync State Bar -->
  <div class="video-section">
    <div class="player-wrap">
      <div id="yt-player"></div>
    </div>
    <div class="meta-bar" id="meta-bar"></div>
  </div>

  <!-- 2. Quiet Transcript Pane -->
  <div class="transcript-area" id="transcript-area">
    <div class="blind-notice">
      <div style="font-size: 20px;">🎧</div>
      <div id="blind-step-label">CC OFF — Listen carefully</div>
    </div>
    <div class="caption-list" id="caption-list"></div>
  </div>

  <!-- 3. Ninja Controls -->
  <div class="ninja-panel">
    <div class="ninja-header">
      <span>Ninja Protocol (0.6x Anchor)</span>
      <span class="status-badge" id="status-badge">Ready</span>
    </div>

    <div class="range-row">
      <div class="mark-box">
        <button class="mark-btn" onclick="markStartNow()">Mark start</button>
        <span class="mark-val" id="start-val">00:00</span>
      </div>
      <div class="mark-box">
        <button class="mark-btn" onclick="markEndNow()">Mark end</button>
        <span class="mark-val" id="end-val">00:10</span>
      </div>
      <button class="next-btn" onclick="moveToNextFragment()">Next →</button>
    </div>

    <div class="run-row">
      <button class="run-btn" onclick="runSequence(0)">▶ Run sequence</button>
      <button class="stop-btn" onclick="stopSequence()">■ Stop</button>
      <button class="cfg-btn" onclick="openModal()" title="Customize steps">⚙</button>
    </div>

    <div class="steps-header">
      <span>STEPS (TAP TO JUMP IN)</span>
      <span id="step-counter">19 steps</span>
    </div>
    <div class="steps-list" id="steps-list"></div>
  </div>
</div>

<!-- Protocol Customization Modal -->
<div class="modal-backdrop" id="cfg-modal">
  <div class="modal-box">
    <div class="modal-head">
      <span>Customize Ninja Steps</span>
      <button class="nudge-btn" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body" id="modal-steps-body"></div>
    <div class="modal-foot">
      <button class="nudge-btn" onclick="addStepRow()">+ Add</button>
      <button class="nudge-btn" onclick="resetDefaultSteps()">Reset</button>
      <button class="nudge-btn" style="background:#2563eb;border-color:#2563eb;" onclick="saveModalSteps()">Save</button>
    </div>
  </div>
</div>

<script>
  function fitParentIframe() {{
    try {{
      const frame = window.frameElement;
      if (frame && window.parent) {{
        const topOffset = frame.getBoundingClientRect().top;
        const avail = Math.max(300, window.parent.innerHeight - topOffset - 6);
        frame.style.height = avail + "px";
      }}
    }} catch (e) {{}}
  }}
  window.addEventListener("load", fitParentIframe);
  window.addEventListener("resize", fitParentIframe);
  setTimeout(fitParentIframe, 100);

  const captions = {captions_json};
  const videoId = "{video_id}";

  const DEFAULT_STEPS = [
    {{ speed: 1.0, cc: false }},
    {{ speed: 1.0, cc: true }},
    {{ speed: 0.6, cc: true }},
    {{ speed: 0.6, cc: true }},
    {{ speed: 0.6, cc: true }},
    {{ speed: 0.7, cc: true }},
    {{ speed: 0.8, cc: true }},
    {{ speed: 0.9, cc: true }},
    {{ speed: 1.0, cc: false }},
    {{ speed: 1.1, cc: false }},
    {{ speed: 1.2, cc: false }},
    {{ speed: 1.3, cc: false }},
    {{ speed: 1.4, cc: false }},
    {{ speed: 1.5, cc: false }},
    {{ speed: 1.6, cc: false }},
    {{ speed: 1.7, cc: false }},
    {{ speed: 1.8, cc: false }},
    {{ speed: 1.9, cc: false }},
    {{ speed: 2.0, cc: false }}
  ];

  let steps = JSON.parse(localStorage.getItem("ninja_steps_v1") || "null") || [...DEFAULT_STEPS];
  let player = null;
  let activeCaptionIdx = -1;

  let isSynced = false;
  let timeOffset = 0.0;

  let rangeStart = 0.0;
  let rangeEnd = 10.0;

  let isRunning = false;
  let currentStepIdx = -1;
  let stepTransitionLock = false;

  let userScrolling = false;
  let scrollTimeout = null;

  const listEl = document.getElementById("caption-list");
  const areaEl = document.getElementById("transcript-area");
  const metaBarEl = document.getElementById("meta-bar");
  const startValEl = document.getElementById("start-val");
  const endValEl = document.getElementById("end-val");
  const statusBadge = document.getElementById("status-badge");
  const stepsListEl = document.getElementById("steps-list");
  const blindStepLabel = document.getElementById("blind-step-label");

  function fmtTime(sec) {{
    if (sec === undefined || sec === null || isNaN(sec)) return "00:00";
    const sTotal = Math.max(0, Math.floor(sec));
    const m = Math.floor(sTotal / 60);
    const s = sTotal % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }}

  function fmtTimePrecise(sec) {{
    if (sec === undefined || sec === null || isNaN(sec)) return "00:00.0";
    const sClamped = Math.max(0, sec);
    const m = Math.floor(sClamped / 60);
    const s = (sClamped % 60).toFixed(1).padStart(4, "0");
    return String(m).padStart(2, "0") + ":" + s;
  }}

  function renderSyncBar() {{
    const curTimeText = document.getElementById("time-display")?.textContent || "00:00 / 00:00";
    if (!isSynced) {{
      metaBarEl.innerHTML = `
        <div class="meta-top">
          <div class="time-display" id="time-display">${{curTimeText}}</div>
          <span class="unsync-hint">⏸ Scroll locked — tap Sync when heard</span>
        </div>
      `;
    }} else {{
      const sign = timeOffset >= 0 ? "+" : "";
      metaBarEl.innerHTML = `
        <div class="meta-top">
          <div class="time-display" id="time-display">${{curTimeText}}</div>
          <div>
            <span class="offset-badge">${{sign}}${{timeOffset.toFixed(1)}}s</span>
            <button class="unsync-btn" onclick="unsyncAll()">Unsync</button>
          </div>
        </div>
        <div class="sync-nudge-grid">
          <div class="nudge-group">
            <span class="group-label lag">Sub is LAGGING by:</span>
            <button class="nudge-btn" onclick="adjustOffset(-1.0)">1s</button>
            <button class="nudge-btn" onclick="adjustOffset(-0.5)">.5s</button>
            <button class="nudge-btn" onclick="adjustOffset(-0.2)">.2s</button>
            <button class="nudge-btn" onclick="adjustOffset(-0.1)">.1s</button>
          </div>
          <div class="nudge-group">
            <span class="group-label lead">Sub is LEADING by:</span>
            <button class="nudge-btn" onclick="adjustOffset(0.1)">.1s</button>
            <button class="nudge-btn" onclick="adjustOffset(0.2)">.2s</button>
            <button class="nudge-btn" onclick="adjustOffset(0.5)">.5s</button>
            <button class="nudge-btn" onclick="adjustOffset(1.0)">1s</button>
          </div>
        </div>
      `;
    }}
  }}

  function unsyncAll() {{
    isSynced = false;
    activeCaptionIdx = -1;
    renderSyncBar();
    renderCaptions();
  }}

  function adjustOffset(delta) {{
    timeOffset = Math.round((timeOffset + delta) * 10) / 10;
    renderSyncBar();
    renderCaptions();
  }}

  function updateRangeUI() {{
    startValEl.textContent = fmtTimePrecise(rangeStart);
    endValEl.textContent = fmtTimePrecise(rangeEnd);
    highlightRangeCaptions();
  }}

  function highlightRangeCaptions() {{
    captions.forEach((item, idx) => {{
      const el = document.getElementById("line-" + idx);
      if (!el) return;
      const adjStart = item.start + timeOffset;
      const adjEnd = item.end + timeOffset;
      const inRange = (adjEnd > rangeStart + 0.1) && (adjStart < rangeEnd - 0.1);
      el.classList.toggle("in-range", inRange);
    }});
  }}

  function renderCaptions() {{
    listEl.innerHTML = "";
    captions.forEach((item, idx) => {{
      const adjStart = item.start + timeOffset;
      const adjEnd = item.end + timeOffset;
      const div = document.createElement("div");
      div.className = "caption-line" + (isSynced && idx === activeCaptionIdx ? " active" : "");
      div.id = "line-" + idx;

      const mainDiv = document.createElement("div");
      mainDiv.className = "caption-main";
      mainDiv.innerHTML = `<span class="caption-time">${{fmtTime(adjStart)}}</span><span>${{item.text}}</span>`;
      mainDiv.onclick = () => {{
        if (player && player.seekTo) {{
          player.seekTo(Math.max(0, adjStart), true);
          player.playVideo();
        }}
      }};

      const actions = document.createElement("div");
      actions.className = "line-actions";

      if (!isSynced) {{
        const syncBtn = document.createElement("button");
        syncBtn.className = "tag-btn sync-line-btn";
        syncBtn.textContent = "Sync";
        syncBtn.onclick = (e) => {{
          e.stopPropagation();
          if (!player || typeof player.getCurrentTime !== "function") return;
          const now = player.getCurrentTime();
          timeOffset = Math.round((now - item.start) * 10) / 10;
          isSynced = true;
          renderSyncBar();
          renderCaptions();
        }};
        actions.appendChild(syncBtn);
      }} else {{
        const startBtn = document.createElement("button");
        startBtn.className = "tag-btn";
        startBtn.textContent = "S";
        startBtn.onclick = (e) => {{
          e.stopPropagation();
          rangeStart = Math.max(0, adjStart);
          if (rangeEnd <= rangeStart) rangeEnd = Math.max(rangeStart + 2.0, adjEnd);
          updateRangeUI();
        }};

        const endBtn = document.createElement("button");
        endBtn.className = "tag-btn";
        endBtn.textContent = "E";
        endBtn.onclick = (e) => {{
          e.stopPropagation();
          rangeEnd = Math.max(rangeStart + 0.5, adjEnd);
          updateRangeUI();
        }};

        actions.appendChild(startBtn);
        actions.appendChild(endBtn);
      }}

      div.appendChild(mainDiv);
      div.appendChild(actions);
      listEl.appendChild(div);
    }});
    highlightRangeCaptions();
  }}

  function renderStepsList() {{
    stepsListEl.innerHTML = "";
    document.getElementById("step-counter").textContent = `${{steps.length}} steps`;
    steps.forEach((stItem, idx) => {{
      const row = document.createElement("div");
      row.className = "step-item" + (isRunning && idx === currentStepIdx ? " current-step" : "");
      row.id = "step-row-" + idx;
      row.innerHTML = `
        <span class="step-num">${{idx + 1}}</span>
        <span class="step-speed">${{stItem.speed.toFixed(1)}}x</span>
        <span class="${{stItem.cc ? 'step-cc-on' : 'step-cc-off'}}">${{stItem.cc ? 'CC on' : 'CC off'}}</span>
        <span style="font-size:11px;color:#64748b;text-align:right;">Tap to jump</span>
      `;
      row.onclick = () => {{ runSequence(idx); }};
      stepsListEl.appendChild(row);
    }});
  }}

  function setCCVisibility(showCC) {{
    if (showCC) {{
      areaEl.classList.remove("mode-off");
    }} else {{
      areaEl.classList.add("mode-off");
      if (isRunning && currentStepIdx >= 0) {{
        const s = steps[currentStepIdx];
        blindStepLabel.textContent = `Step ${{currentStepIdx + 1}}/${{steps.length}} (${{s.speed.toFixed(1)}}x) — CC OFF`;
      }} else {{
        blindStepLabel.textContent = "CC OFF — Listen carefully";
      }}
    }}
  }}

  function markStartNow() {{
    if (!player || typeof player.getCurrentTime !== "function") return;
    rangeStart = player.getCurrentTime();
    if (rangeEnd <= rangeStart + 0.3) rangeEnd = rangeStart + 5.0;
    updateRangeUI();
  }}

  function markEndNow() {{
    if (!player || typeof player.getCurrentTime !== "function") return;
    const now = player.getCurrentTime();
    if (now > rangeStart + 0.3) {{
      rangeEnd = now;
      updateRangeUI();
    }}
  }}

  function moveToNextFragment() {{
    stopSequence();
    const prevEnd = rangeEnd;
    rangeStart = prevEnd;
    const nextCap = captions.find(c => (c.start + timeOffset) >= prevEnd - 0.2);
    if (nextCap) {{
      rangeEnd = Math.max(rangeStart + 2.0, nextCap.end + timeOffset);
    }} else {{
      rangeEnd = rangeStart + 5.0;
    }}
    updateRangeUI();
    if (player && player.seekTo) {{
      player.seekTo(rangeStart, true);
      player.playVideo();
    }}
  }}

  function runSequence(startIdx = 0) {{
    if (!player || steps.length === 0) return;
    if (rangeEnd <= rangeStart + 0.2) {{
      rangeEnd = rangeStart + 5.0;
      updateRangeUI();
    }}
    isRunning = true;
    applyStep(startIdx);
  }}

  function applyStep(idx) {{
    if (idx >= steps.length) {{
      isRunning = false;
      currentStepIdx = -1;
      player.pauseVideo();
      player.setPlaybackRate(1.0);
      setCCVisibility(true);
      statusBadge.textContent = "Completed!";
      renderStepsList();
      return;
    }}

    currentStepIdx = idx;
    const step = steps[idx];
    stepTransitionLock = true;

    player.setPlaybackRate(step.speed);
    setCCVisibility(step.cc);
    statusBadge.textContent = `Step ${{idx + 1}}/${{steps.length}} (${{step.speed.toFixed(1)}}x ${{step.cc ? 'CC ON' : 'CC OFF'}})`;

    renderStepsList();
    const activeRow = document.getElementById("step-row-" + idx);
    if (activeRow) activeRow.scrollIntoView({{ behavior: "smooth", block: "nearest" }});

    player.seekTo(rangeStart, true);
    player.playVideo();

    setTimeout(() => {{ stepTransitionLock = false; }}, 350);
  }}

  function stopSequence() {{
    isRunning = false;
    currentStepIdx = -1;
    if (player && typeof player.pauseVideo === "function") {{
      player.pauseVideo();
      player.setPlaybackRate(1.0);
    }}
    setCCVisibility(true);
    statusBadge.textContent = "Ready";
    renderStepsList();
  }}

  renderSyncBar();
  renderCaptions();
  renderStepsList();
  updateRangeUI();

  areaEl.addEventListener("touchstart", () => {{
    userScrolling = true;
    clearTimeout(scrollTimeout);
  }}, {{ passive: true }});
  areaEl.addEventListener("touchend", () => {{
    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(() => {{ userScrolling = false; }}, 3000);
  }}, {{ passive: true }});

  const tag = document.createElement("script");
  tag.src = "https://www.youtube.com/iframe_api";
  document.head.appendChild(tag);

  window.onYouTubeIframeAPIReady = function() {{
    player = new YT.Player("yt-player", {{
      videoId: videoId,
      playerVars: {{
        playsinline: 1,
        cc_load_policy: 0,
        rel: 0,
        modestbranding: 1
      }},
      events: {{
        onReady: () => {{
          fitParentIframe();
          if (captions.length > 0) {{
            rangeStart = captions[0].start;
            rangeEnd = captions[0].end;
            updateRangeUI();
          }}
          setInterval(mainLoop, 100);
        }}
      }}
    }});
  }};

  function mainLoop() {{
    if (!player || typeof player.getCurrentTime !== "function") return;
    const t = player.getCurrentTime();
    const d = player.getDuration();
    const timeEl = document.getElementById("time-display");
    if (timeEl) timeEl.textContent = `${{fmtTime(t)}} / ${{fmtTime(d)}}`;

    if (isRunning && !stepTransitionLock && player.getPlayerState() === YT.PlayerState.PLAYING) {{
      if (t >= rangeEnd) {{
        applyStep(currentStepIdx + 1);
        return;
      }}
    }}

    if (!isSynced) return;

    const effectiveT = t - timeOffset;
    let found = -1;
    for (let i = 0; i < captions.length; i++) {{
      if (effectiveT >= captions[i].start && effectiveT < captions[i].end) {{
        found = i;
        break;
      }}
    }}
    if (found === -1) {{
      for (let i = captions.length - 1; i >= 0; i--) {{
        if (effectiveT >= captions[i].start) {{
          found = i;
          break;
        }}
      }}
    }}

    if (found !== activeCaptionIdx && found !== -1) {{
      if (activeCaptionIdx !== -1) {{
        const prev = document.getElementById("line-" + activeCaptionIdx);
        if (prev) prev.classList.remove("active");
      }}
      activeCaptionIdx = found;
      const cur = document.getElementById("line-" + activeCaptionIdx);
      if (cur) {{
        cur.classList.add("active");
        if (!userScrolling && !areaEl.classList.contains("mode-off")) {{
          cur.scrollIntoView({{ behavior: "smooth", block: "center" }});
        }}
      }}
    }}
  }}

  let draftSteps = [];
  function openModal() {{
    draftSteps = steps.map(s => ({{ ...s }}));
    renderModalBody();
    document.getElementById("cfg-modal").classList.add("open");
  }}
  function closeModal() {{
    document.getElementById("cfg-modal").classList.remove("open");
  }}
  function renderModalBody() {{
    const body = document.getElementById("modal-steps-body");
    body.innerHTML = "";
    draftSteps.forEach((stItem, idx) => {{
      const r = document.createElement("div");
      r.className = "edit-row";
      r.innerHTML = `
        <span>${{idx + 1}}</span>
        <input type="number" step="0.1" min="0.25" max="2.0" value="${{stItem.speed}}"
               onchange="draftSteps[${{idx}}].speed = parseFloat(this.value) || 1.0" />
        <label><input type="checkbox" ${{stItem.cc ? "checked" : ""}}
               onchange="draftSteps[${{idx}}].cc = this.checked" /> CC</label>
        <div style="text-align:right;">
          <button class="nudge-btn" onclick="moveDraft(${{idx}}, -1)">↑</button>
          <button class="nudge-btn" onclick="moveDraft(${{idx}}, 1)">↓</button>
          <button class="nudge-btn" onclick="delDraft(${{idx}})">✕</button>
        </div>
      `;
      body.appendChild(r);
    }});
  }}
  function moveDraft(idx, dir) {{
    const target = idx + dir;
    if (target < 0 || target >= draftSteps.length) return;
    [draftSteps[idx], draftSteps[target]] = [draftSteps[target], draftSteps[idx]];
    renderModalBody();
  }}
  function delDraft(idx) {{
    draftSteps.splice(idx, 1);
    renderModalBody();
  }}
  function addStepRow() {{
    draftSteps.push({{ speed: 1.0, cc: false }});
    renderModalBody();
  }}
  function resetDefaultSteps() {{
    draftSteps = DEFAULT_STEPS.map(s => ({{ ...s }}));
    renderModalBody();
  }}
  function saveModalSteps() {{
    if (draftSteps.length === 0) return;
    steps = draftSteps;
    localStorage.setItem("ninja_steps_v1", JSON.stringify(steps));
    renderStepsList();
    closeModal();
  }}
</script>
</body>
</html>
"""


col_url, col_merge = st.columns([5, 1])
with col_url:
    url = st.text_input(
        "YouTube URL",
        placeholder="YouTube URL を貼り付け...",
        label_visibility="collapsed",
    )
with col_merge:
    merge_opt = st.checkbox("Merge", value=True, help="断片字幕を文単位に結合")

if url:
    vid = extract_video_id(url)
    if not vid:
        st.error("有効なYouTube URLではありません。")
    else:
        try:
            with st.spinner("字幕取得中..."):
                captions = fetch_transcript(vid, merge_sentences=merge_opt)
            components.html(build_player_html(vid, captions), height=720, scrolling=False)
        except Exception as e:
            st.error(f"字幕を取得できませんでした: {e}")