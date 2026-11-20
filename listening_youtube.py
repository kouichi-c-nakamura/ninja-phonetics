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


def extract_video_id(url: str) -> str | None:
    """YouTubeの各種URLから11文字の動画IDを抽出"""
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
    """youtube-transcript-api のバージョン差異を吸収して字幕を取得"""
    # v1.x 系 (インスタンスメソッド)
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
    # v0.6.x 系 (クラスメソッド)
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
    --active-bg: #1d4ed8;
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

  /* 上部：極小YouTubeプレイヤー */
  .video-bar {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    background: #020617;
    border-bottom: 1px solid #334155;
    flex-shrink: 0;
  }}
  .player-wrap {{
    width: 160px;
    height: 90px;
    flex-shrink: 0;
    border-radius: 6px;
    overflow: hidden;
    background: #000;
  }}
  .player-wrap iframe {{
    width: 100%;
    height: 100%;
  }}
  .status-panel {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }}
  .time-display {{
    font-size: 13px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }}
  .speed-row {{
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }}
  .speed-btn {{
    background: var(--card);
    color: var(--text);
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    cursor: pointer;
  }}
  .speed-btn.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
    font-weight: 700;
  }}

  /* 中央：大きめスクロール字幕エリア */
  .transcript-area {{
    flex: 1;
    overflow-y: auto;
    padding: 14px 12px 24px;
    scroll-behavior: smooth;
    position: relative;
  }}
  .caption-line {{
    padding: 12px 14px;
    margin-bottom: 8px;
    border-radius: 10px;
    background: var(--card);
    font-size: 18px;
    line-height: 1.5;
    cursor: pointer;
    transition: background 0.15s, filter 0.15s, opacity 0.15s;
    border-left: 4px solid transparent;
  }}
  .caption-line.active {{
    background: rgba(43, 162, 189, 0.22);
    border-left-color: var(--accent);
    font-weight: 600;
  }}
  .caption-time {{
    display: inline-block;
    font-size: 11px;
    color: var(--muted);
    margin-right: 6px;
    font-variant-numeric: tabular-nums;
  }}

  /* 字幕モード制御 */
  .mode-mask .caption-text {{
    filter: blur(7px);
    user-select: none;
  }}
  .mode-mask .caption-line:active .caption-text {{
    filter: none; /* 長押し・タップ中だけ覗き見可能 */
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
    font-size: 15px;
    gap: 8px;
  }}
  .mode-off .blind-notice {{
    display: flex;
  }}

  /* 下部：親指コントロールバー */
  .controls {{
    background: #020617;
    border-top: 1px solid #334155;
    padding: 10px 10px 14px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
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
    border-radius: 10px;
    padding: 12px 6px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
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

  <div class="video-bar">
    <div class="player-wrap">
      <div id="yt-player"></div>
    </div>
    <div class="status-panel">
      <div class="time-display" id="time-display">00:00 / 00:00</div>
      <div class="speed-row">
        <button class="speed-btn" onclick="setRate(0.7, this)">0.7x</button>
        <button class="speed-btn active" onclick="setRate(1.0, this)">1.0x</button>
        <button class="speed-btn" onclick="setRate(1.25, this)">1.25x</button>
        <button class="speed-btn" onclick="setRate(1.5, this)">1.5x</button>
      </div>
    </div>
  </div>

  <div class="transcript-area" id="transcript-area">
    <div class="blind-notice">
      <div style="font-size: 28px;">🎧</div>
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
      <button class="ctrl-btn" onclick="repeatCurrentLine()">↻ 1文リピート</button>
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
  let userScrolling = false;
  let scrollTimeout = null;

  const listEl = document.getElementById("caption-list");
  const areaEl = document.getElementById("transcript-area");
  const timeEl = document.getElementById("time-display");
  const playBtn = document.getElementById("btn-play");

  function fmtTime(sec) {{
    if (!sec || isNaN(sec)) return "00:00";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }}

  // 字幕リスト描画
  captions.forEach((item, idx) => {{
    const div = document.createElement("div");
    div.className = "caption-line";
    div.id = "line-" + idx;
    div.innerHTML = `<span class="caption-time">${{fmtTime(item.start)}}</span><span class="caption-text">${{item.text}}</span>`;
    div.onclick = () => {{
      if (player && player.seekTo) {{
        player.seekTo(item.start, true);
        player.playVideo();
      }}
    }};
    listEl.appendChild(div);
  }});

  // 手動スクロール中は自動追従を一時停止（スクロールのケンカ防止）
  areaEl.addEventListener("touchstart", () => {{
    userScrolling = true;
    clearTimeout(scrollTimeout);
  }}, {{ passive: true }});
  areaEl.addEventListener("touchend", () => {{
    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(() => {{ userScrolling = false; }}, 3000);
  }}, {{ passive: true }});

  // YouTube IFrame API 読み込み
  const tag = document.createElement("script");
  tag.src = "https://www.youtube.com/iframe_api";
  document.head.appendChild(tag);

  window.onYouTubeIframeAPIReady = function() {{
    player = new YT.Player("yt-player", {{
      videoId: videoId,
      playerVars: {{
        playsinline: 1,       // iOS Safari で全画面に飛ぶのを防ぐ
        cc_load_policy: 0,    // YouTube側の字幕は極力出さない
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

    let found = -1;
    for (let i = 0; i < captions.length; i++) {{
      if (t >= captions[i].start && t < captions[i].end) {{
        found = i;
        break;
      }}
    }}
    // 隙間時間は直前の行を維持
    if (found === -1) {{
      for (let i = captions.length - 1; i >= 0; i--) {{
        if (t >= captions[i].start) {{
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
    player.seekTo(captions[idx].start, true);
    player.playVideo();
  }}

  function jumpLine(delta) {{
    if (!player || captions.length === 0) return;
    const next = Math.min(captions.length - 1, Math.max(0, activeIndex + delta));
    player.seekTo(captions[next].start, true);
    player.playVideo();
  }}

  function setRate(rate, btn) {{
    if (!player) return;
    player.setPlaybackRate(rate);
    document.querySelectorAll(".speed-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
  }}
</script>
</body>
</html>
"""


# --- Streamlit UI ---
st.markdown("### 🎧 Ninja Listening (YouTube)")

url = st.text_input(
    "YouTube URL または Video ID",
    placeholder="https://www.youtube.com/watch?v=...",
    label_visibility="collapsed",
)

if url:
    vid = extract_video_id(url)
    if not vid:
        st.error("有効なYouTube URLではありません。")
    else:
        try:
            with st.spinner("英語字幕を取得中..."):
                captions = fetch_transcript(vid)
            st.caption(f"字幕取得完了: {len(captions)} 行（MASKモード時は行を長押しで一時表示）")
            components.html(build_player_html(vid, captions), height=640, scrolling=False)
        except Exception as e:
            st.error(f"字幕を取得できませんでした: {e}")
            st.info("英語字幕がない動画、またはクラウド環境からのIP制限の可能性があります。")