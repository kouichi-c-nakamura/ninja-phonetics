import json
import re
import streamlit as st
import streamlit.components.v1 as components
from youtube_transcript_api import YouTubeTranscriptApi

st.set_page_config(
    page_title="Ninja Listening (YouTube)",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Streamlit上部の余白を詰めてスマホ画面を有効活用
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
    }
    header[data-testid="stHeader"] { display: none; }
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


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_transcript(video_id: str, languages: tuple = ("en", "en-US", "en-GB")) -> list[dict]:
    if hasattr(YouTubeTranscriptApi, "fetch") or not hasattr(YouTubeTranscriptApi, "get_transcript"):
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=list(languages))
        return [
            {
                "start": float(item.start),
                "duration": float(item.duration),
                "end": float(item.start + item.duration),
                "text": item.text.replace("\n", " ").strip(),
            }
            for item in fetched
        ]
    raw = YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
    return [
        {
            "start": float(item["start"]),
            "duration": float(item["duration"]),
            "end": float(item["start"] + item["duration"]),
            "text": item["text"].replace("\n", " ").strip(),
        }
        for item in raw
    ]


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
    --card: #1e293b;
    --accent: #2ba2bd;
    --text: #f8fafc;
    --muted: #94a3b8;
  }}
  * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
  body {{
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", Arial, sans-serif;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }}

  /* 上部：大きめYouTube映像スペース（16:9フル幅） */
  .video-section {{
    background: #020617;
    border-bottom: 1px solid #334155;
    flex-shrink: 0;
  }}
  .player-wrap {{
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    max-height: 230px;
    background: #000;
  }}
  .player-wrap iframe {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }}

  /* ステータス＆速度＆タイムスタンプズレ補正バー */
  .meta-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 8px;
    gap: 4px;
    background: #0b1120;
    border-bottom: 1px solid #1e293b;
    flex-shrink: 0;
    flex-wrap: wrap;
  }}
  .time-display {{
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }}
  .speed-row, .sync-row {{
    display: flex;
    align-items: center;
    gap: 3px;
  }}
  .mini-btn {{
    background: var(--card);
    color: var(--text);
    border: 1px solid #334155;
    border-radius: 5px;
    padding: 3px 6px;
    font-size: 11px;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
  }}
  .mini-btn.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
    font-weight: 700;
  }}
  .offset-label {{
    font-size: 11px;
    color: #38bdf8;
    min-width: 44px;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }}

  /* 中央：コンパクトな字幕スクロールエリア */
  .transcript-area {{
    flex: 1;
    overflow-y: auto;
    padding: 8px 8px 16px;
    scroll-behavior: smooth;
    position: relative;
  }}
  .caption-line {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    padding: 7px 10px;
    margin-bottom: 5px;
    border-radius: 7px;
    background: var(--card);
    font-size: 14.5px;
    line-height: 1.4;
    cursor: pointer;
    border-left: 3px solid transparent;
  }}
  .caption-line.active {{
    background: rgba(43, 162, 189, 0.24);
    border-left-color: var(--accent);
    font-weight: 600;
  }}
  .caption-main {{
    flex: 1;
    min-width: 0;
  }}
  .caption-time {{
    display: inline-block;
    font-size: 11px;
    color: var(--muted);
    margin-right: 6px;
    font-variant-numeric: tabular-nums;
  }}
  .sync-here-btn {{
    background: rgba(56, 189, 248, 0.12);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 5px;
    padding: 2px 6px;
    font-size: 10px;
    flex-shrink: 0;
    cursor: pointer;
  }}
  .sync-here-btn:active {{
    background: var(--accent);
    color: #fff;
  }}

  /* 字幕モード制御 */
  .mode-mask .caption-text {{
    filter: blur(6px);
    user-select: none;
  }}
  .mode-mask .caption-line:active .caption-text {{
    filter: none;
  }}
  .mode-off .caption-list {{
    display: none;
  }}
  .blind-notice {{
    display: none;
    height: 100%;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    color: var(--muted);
    text-align: center;
    font-size: 14px;
    gap: 6px;
  }}
  .mode-off .blind-notice {{
    display: flex;
  }}

  /* 下部：親指コントロールバー（1行スッキリ配置） */
  .controls {{
    background: #020617;
    border-top: 1px solid #334155;
    padding: 8px 8px 10px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .mode-row {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
  }}
  .nav-row {{
    display: grid;
    grid-template-columns: 1fr 1.2fr 1.2fr 1fr;
    gap: 6px;
  }}
  .ctrl-btn {{
    background: var(--card);
    color: var(--text);
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px 4px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
    white-space: nowrap;
  }}
  .ctrl-btn:active {{
    transform: scale(0.97);
    background: #334155;
  }}
  .ctrl-btn.primary {{
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }}
  .ctrl-btn.mode-active {{
    background: #334155;
    border-color: var(--accent);
    color: #38bdf8;
  }}
</style>
</head>
<body>

  <div class="video-section">
    <div class="player-wrap">
      <div id="yt-player"></div>
    </div>
    <div class="meta-bar">
      <div class="time-display" id="time-display">00:00 / 00:00</div>
      <div class="speed-row">
        <button class="mini-btn" onclick="setRate(0.7, this)">0.7x</button>
        <button class="mini-btn active" onclick="setRate(1.0, this)">1.0x</button>
        <button class="mini-btn" onclick="setRate(1.25, this)">1.25x</button>
        <button class="mini-btn" onclick="setRate(1.5, this)">1.5x</button>
      </div>
      <div class="sync-row" title="字幕のタイミングズレ補正">
        <button class="mini-btn" onclick="adjustOffset(-1.0)">-1s</button>
        <span class="offset-label" id="offset-label">+0.0s</span>
        <button class="mini-btn" onclick="adjustOffset(1.0)">+1s</button>
      </div>
    </div>
  </div>

  <div class="transcript-area" id="transcript-area">
    <div class="blind-notice">
      <div style="font-size: 24px;">🎧</div>
      <div>Subtitle OFF — Focus on the sound</div>
    </div>
    <div class="caption-list" id="caption-list"></div>
  </div>

  <div class="controls">
    <div class="mode-row">
      <button class="ctrl-btn" id="btn-mode-off" onclick="setSubMode('off')">OFF</button>
      <button class="ctrl-btn" id="btn-mode-mask" onclick="setSubMode('mask')">MASK</button>
      <button class="ctrl-btn mode-active" id="btn-mode-on" onclick="setSubMode('on')">ON</button>
    </div>
    <div class="nav-row">
      <button class="ctrl-btn" onclick="jumpLine(-1)">◀ 前文</button>
      <button class="ctrl-btn" onclick="repeatCurrentLine()">↻ リピート</button>
      <button class="ctrl-btn primary" id="btn-play" onclick="togglePlay()">▶ 再生</button>
      <button class="ctrl-btn" onclick="jumpLine(1)">次文 ▶</button>
    </div>
  </div>

<script>
  const captions = {captions_json};
  const videoId = "{video_id}";
  let player = null;
  let activeIndex = -1;
  let subMode = "on";
  let timeOffset = 0.0; // 動画時間 - 字幕時間 の補正値（秒）
  let userScrolling = false;
  let scrollTimeout = null;

  const listEl = document.getElementById("caption-list");
  const areaEl = document.getElementById("transcript-area");
  const timeEl = document.getElementById("time-display");
  const playBtn = document.getElementById("btn-play");
  const offsetLabel = document.getElementById("offset-label");

  function fmtTime(sec) {{
    if (sec === undefined || sec === null || isNaN(sec)) return "00:00";
    const sTotal = Math.max(0, Math.floor(sec));
    const m = Math.floor(sTotal / 60);
    const s = sTotal % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }}

  function renderCaptions() {{
    listEl.innerHTML = "";
    captions.forEach((item, idx) => {{
      const adjStart = item.start + timeOffset;
      const div = document.createElement("div");
      div.className = "caption-line" + (idx === activeIndex ? " active" : "");
      div.id = "line-" + idx;

      const mainDiv = document.createElement("div");
      mainDiv.className = "caption-main";
      mainDiv.innerHTML = `<span class="caption-time">${{fmtTime(adjStart)}}</span><span class="caption-text">${{item.text}}</span>`;
      mainDiv.onclick = () => {{
        if (player && player.seekTo) {{
          player.seekTo(Math.max(0, item.start + timeOffset), true);
          player.playVideo();
        }}
      }};

      // この行を現在の再生時間に合わせるSyncボタン
      const syncBtn = document.createElement("button");
      syncBtn.className = "sync-here-btn";
      syncBtn.textContent = "Sync";
      syncBtn.title = "今聞こえた音声にこの行の時間を合わせる";
      syncBtn.onclick = (e) => {{
        e.stopPropagation();
        if (!player || typeof player.getCurrentTime !== "function") return;
        const now = player.getCurrentTime();
        timeOffset = now - item.start;
        updateOffsetUI();
      }};

      div.appendChild(mainDiv);
      div.appendChild(syncBtn);
      listEl.appendChild(div);
    }});
  }}

  function updateOffsetUI() {{
    const sign = timeOffset >= 0 ? "+" : "";
    offsetLabel.textContent = `${{sign}}${{timeOffset.toFixed(1)}}s`;
    renderCaptions();
  }}

  function adjustOffset(delta) {{
    timeOffset += delta;
    updateOffsetUI();
  }}

  renderCaptions();

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
          setInterval(syncLoop, 200);
        }},
        onStateChange: (e) => {{
          playBtn.textContent = (e.data === YT.PlayerState.PLAYING) ? "❚❚ 停止" : "▶ 再生";
        }}
      }}
    }});
  }};

  function syncLoop() {{
    if (!player || typeof player.getCurrentTime !== "function") return;
    const t = player.getCurrentTime();
    const d = player.getDuration();
    timeEl.textContent = `${{fmtTime(t)}} / ${{fmtTime(d)}}`;

    // オフセット補正済みの時間で判定
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

    if (found !== activeIndex && found !== -1) {{
      if (activeIndex !== -1) {{
        const prev = document.getElementById("line-" + activeIndex);
        if (prev) prev.classList.remove("active");
      }}
      activeIndex = found;
      const cur = document.getElementById("line-" + activeIndex);
      if (cur) {{
        cur.classList.add("active");
        if (!userScrolling && subMode !== "off") {{
          cur.scrollIntoView({{ behavior: "smooth", block: "center" }});
        }}
      }}
    }}
  }}

  function setSubMode(mode) {{
    subMode = mode;
    areaEl.classList.remove("mode-mask", "mode-off");
    if (mode === "mask") areaEl.classList.add("mode-mask");
    if (mode === "off") areaEl.classList.add("mode-off");

    ["off", "mask", "on"].forEach(m => {{
      document.getElementById("btn-mode-" + m).classList.toggle("mode-active", m === mode);
    }});
  }}

  function togglePlay() {{
    if (!player) return;
    const state = player.getPlayerState();
    if (state === YT.PlayerState.PLAYING) {{
      player.pauseVideo();
    }} else {{
      player.playVideo();
    }}
  }}

  function repeatCurrentLine() {{
    if (!player || captions.length === 0) return;
    const idx = Math.max(0, activeIndex);
    player.seekTo(Math.max(0, captions[idx].start + timeOffset), true);
    player.playVideo();
  }}

  function jumpLine(delta) {{
    if (!player || captions.length === 0) return;
    const next = Math.min(captions.length - 1, Math.max(0, activeIndex + delta));
    player.seekTo(Math.max(0, captions[next].start + timeOffset), true);
    player.playVideo();
  }}

  function setRate(rate, btn) {{
    if (!player) return;
    player.setPlaybackRate(rate);
    document.querySelectorAll(".speed-row .mini-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
  }}
</script>
</body>
</html>
"""


# --- Streamlit UI ---
url = st.text_input(
    "YouTube URL",
    placeholder="YouTube URL を貼り付け...",
    label_visibility="collapsed",
)

if url:
    vid = extract_video_id(url)
    if not vid:
        st.error("有効なYouTube URLではありません。")
    else:
        try:
            with st.spinner("字幕取得中..."):
                captions = fetch_transcript(vid)
            components.html(build_player_html(vid, captions), height=680, scrolling=False)
        except Exception as e:
            st.error(f"字幕を取得できませんでした: {e}")