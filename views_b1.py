"""
views_b1.py: B1 歯擦音スペクトル重心スコープ (/si/ vs /ʃi/) Spike2風描画生成
"""
import json


def build_b1_scope_html(data: dict, auto_play: bool = False, export_name: str = "b1_scope", scope_height: int = 510) -> str:
    data["auto_play"] = auto_play
    data["export_name"] = export_name
    data_json = json.dumps(data)
    return f"""
<!DOCTYPE html>
<html>
<head>
<style>
  body {{
    margin: 0; padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #0B0F19; color: #E2E8F0;
    user-select: none; overflow: hidden;
  }}
  .toolbar {{
    display: flex; align-items: center; gap: 10px;
    padding: 8px 14px; background: #0F172A;
    border: 1px solid #1E293B; border-radius: 8px 8px 0 0;
  }}
  button {{
    font-family: inherit; font-size: 13px; font-weight: bold;
    padding: 6px 12px; border-radius: 6px;
    border: 1px solid #334155; cursor: pointer;
    background: #1E293B; color: #E2E8F0;
    transition: all 0.15s; white-space: nowrap;
  }}
  button:hover {{ background: #334155; color: #FFFFFF; }}
  button.btn-play-ready {{ background: #16A34A; color: #FFFFFF; border-color: #15803D; }}
  button.btn-play-ready:hover {{ background: #15803D; }}
  button.btn-play-active {{ background: #DC2626; color: #FFFFFF; border-color: #B91C1C; }}
  button.toggle-active {{ background: #334155; color: #F8FAFC; border-color: #64748B; }}
  select {{
    font-family: inherit; font-size: 13px; padding: 5px 8px;
    border-radius: 6px; border: 1px solid #334155;
    background: #1E293B; color: #E2E8F0; font-weight: bold;
  }}
  .readout {{
    font-family: inherit; font-size: 13px; font-weight: 500; margin-left: auto;
    font-variant-numeric: tabular-nums; color: #E2E8F0; white-space: nowrap;
  }}
  #scope-wrapper {{
    position: relative; width: 100%; height: {scope_height}px;
    border: 1px solid #1E293B; border-top: none; background: #090D16;
    border-radius: 0 0 8px 8px;
  }}
  canvas {{ position: absolute; left: 0; top: 0; width: 100%; height: 100%; }}
  #overlay-canvas {{ mix-blend-mode: screen; }}
</style>
</head>
<body>
<div class="toolbar">
  <button id="btn-play" class="btn-play-ready">▶ Play (Space)</button>
  <button id="btn-reset">⏮ 全体選択</button>
  <button id="btn-spec" class="toggle-active">1-10kHz Spec: ON</button>
  <button id="btn-phonemes" class="toggle-active">Phonemes: ON</button>
  <label style="font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 6px; color: #94A3B8;">
    Speed:
    <select id="sel-rate">
      <option value="1.0">1.0x</option>
      <option value="0.7">0.7x</option>
      <option value="0.5">0.5x</option>
    </select>
  </label>
  <button id="btn-dl-plot">💾 Plot (.png)</button>
  <button id="btn-dl-audio">🔊 Audio (.wav)</button>
  <div class="readout" id="time-readout">Cursor: 0.000 s</div>
</div>
<div id="scope-wrapper">
  <canvas id="bg-canvas"></canvas>
  <canvas id="overlay-canvas"></canvas>
</div>
<script>
const D = {data_json};
const wrapper = document.getElementById('scope-wrapper');
const bgCanvas = document.getElementById('bg-canvas');
const ovCanvas = document.getElementById('overlay-canvas');
const bgCtx = bgCanvas.getContext('2d');
const ovCtx = ovCanvas.getContext('2d');

const btnPlay = document.getElementById('btn-play');
const btnReset = document.getElementById('btn-reset');
const btnSpec = document.getElementById('btn-spec');
const btnPhonemes = document.getElementById('btn-phonemes');
const btnDlPlot = document.getElementById('btn-dl-plot');
const btnDlAudio = document.getElementById('btn-dl-audio');
const selRate = document.getElementById('sel-rate');
const readout = document.getElementById('time-readout');

const MARGIN = {{ left: 100, right: 30, top: 16, bottom: 38 }};
let W = 1000, H = {scope_height};
let xMin = D.x_min, xMax = D.x_max;
let selStart = xMin, selEnd = xMax;
let cursorT = (xMin + xMax) / 2;
let showSpec = true;
let showPhonemes = true;

let specCanvas = null;
if (D.spec_w > 0 && D.spec_h > 0 && D.spec_b64) {{
  specCanvas = document.createElement('canvas');
  specCanvas.width = D.spec_w; specCanvas.height = D.spec_h;
  const sCtx = specCanvas.getContext('2d');
  const imgData = sCtx.createImageData(D.spec_w, D.spec_h);
  const raw = atob(D.spec_b64);
  for (let i = 0; i < raw.length; i++) {{
    const val = raw.charCodeAt(i);
    const p = i * 4;
    const gray = Math.min(255, 10 + val * 0.88);
    imgData.data[p] = gray; imgData.data[p+1] = gray; imgData.data[p+2] = gray; imgData.data[p+3] = 255;
  }}
  sCtx.putImageData(imgData, 0, 0);
}}

let audioEl = new Audio();
let audioBlobUrl = null;
let isPlaying = false;
let animId = null;

function initAudio() {{
  const binary = atob(D.wav_b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], {{ type: "audio/wav" }});
  audioBlobUrl = URL.createObjectURL(blob);
  audioEl.src = audioBlobUrl;
  audioEl.preservesPitch = true;
  audioEl.mozPreservesPitch = true;
  audioEl.webkitPreservesPitch = true;
}}
initAudio();

function tToX(t) {{
  const plotW = W - MARGIN.left - MARGIN.right;
  return MARGIN.left + ((t - xMin) / (xMax - xMin)) * plotW;
}}
function xToT(x) {{
  const plotW = W - MARGIN.left - MARGIN.right;
  const t = xMin + ((x - MARGIN.left) / plotW) * (xMax - xMin);
  return Math.max(xMin, Math.min(xMax, t));
}}
function getPanels() {{
  const totalH = H - MARGIN.top - MARGIN.bottom;
  const gap = 20, h1 = 95;
  const remainH = totalH - h1 - (gap * 2);
  const h2 = remainH * 0.50, h3 = remainH * 0.50;
  const y1 = MARGIN.top, y2 = y1 + h1 + gap, y3 = y2 + h2 + gap;
  return [
    {{ top: y1, bottom: y1 + h1, height: h1 }},
    {{ top: y2, bottom: y2 + h2, height: h2 }},
    {{ top: y3, bottom: y3 + h3, height: h3 }}
  ];
}}
function valToY(val, vMin, vMax, panel) {{
  return panel.bottom - ((val - vMin) / (vMax - vMin)) * panel.height;
}}

function drawPhonemeAnnotations(panels, plotW, APP_FONT) {{
  if (!showPhonemes || !D.phonemes || D.phonemes.length === 0) return;
  const p2 = panels[1];
  const tierH = 24;

  bgCtx.save();
  // 全3パネルに境界縦破線を描画
  panels.forEach((p) => {{
    bgCtx.save();
    bgCtx.beginPath(); bgCtx.rect(MARGIN.left, p.top, plotW, p.height); bgCtx.clip();
    bgCtx.setLineDash([4, 4]);
    bgCtx.lineWidth = 1.15;
    bgCtx.strokeStyle = "rgba(148, 163, 184, 0.32)";

    const bounds = new Set();
    D.phonemes.forEach(seg => {{ bounds.add(seg.start); bounds.add(seg.end); }});
    bounds.forEach(bt => {{
      const bx = tToX(bt);
      if (bx >= MARGIN.left && bx <= W - MARGIN.right) {{
        bgCtx.beginPath(); bgCtx.moveTo(bx, p.top); bgCtx.lineTo(bx, p.bottom); bgCtx.stroke();
      }}
    }});
    bgCtx.restore();
  }});

  // 第2パネル上部に音素IPAラベル帯を描画
  bgCtx.save();
  bgCtx.beginPath(); bgCtx.rect(MARGIN.left, p2.top, plotW, p2.height); bgCtx.clip();

  D.phonemes.forEach((seg) => {{
    const sx = Math.max(MARGIN.left, tToX(seg.start));
    const ex = Math.min(W - MARGIN.right, tToX(seg.end));
    const segW = ex - sx;
    if (segW < 3) return;

    const isS = (seg.base === "S");
    const isSH = (seg.base === "SH");
    const bgFill = isS
      ? "rgba(6, 95, 70, 0.85)"
      : (isSH ? "rgba(3, 105, 161, 0.85)" : "rgba(15, 23, 42, 0.78)");
    const borderCol = isS
      ? "rgba(16, 185, 129, 0.9)"
      : (isSH ? "rgba(56, 189, 248, 0.9)" : "rgba(100, 116, 139, 0.55)");
    const txtCol = isS ? "#A7F3D0" : (isSH ? "#E0F2FE" : "#CBD5E1");

    bgCtx.fillStyle = bgFill;
    bgCtx.fillRect(sx, p2.top, segW, tierH);
    bgCtx.strokeStyle = borderCol;
    bgCtx.lineWidth = 1.1;
    bgCtx.strokeRect(sx, p2.top, segW, tierH);

    if (segW >= 10) {{
      bgCtx.fillStyle = txtCol;
      bgCtx.font = (segW > 22 ? "bold 13px " : "bold 10px ") + APP_FONT;
      bgCtx.textAlign = "center";
      bgCtx.textBaseline = "middle";
      bgCtx.fillText(seg.ipa, sx + segW / 2, p2.top + tierH / 2 + 0.5);
    }}
  }});

  bgCtx.restore();
  bgCtx.restore();
}}

function drawBackground() {{
  const dpr = window.devicePixelRatio || 1;
  W = wrapper.clientWidth; H = wrapper.clientHeight;
  bgCanvas.width = W * dpr; bgCanvas.height = H * dpr;
  ovCanvas.width = W * dpr; ovCanvas.height = H * dpr;
  bgCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ovCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  bgCtx.fillStyle = "#090D16"; bgCtx.fillRect(0, 0, W, H);
  const panels = getPanels();
  const plotW = W - MARGIN.left - MARGIN.right;
  const p1 = panels[0], p2 = panels[1], p3 = panels[2];
  const fMaxSpec = D.spec_max_hz || 10000;

  if (showSpec && specCanvas) {{
    bgCtx.save();
    bgCtx.beginPath(); bgCtx.rect(MARGIN.left, p2.top, plotW, p2.height); bgCtx.clip();
    bgCtx.imageSmoothingEnabled = true; bgCtx.imageSmoothingQuality = "high";
    bgCtx.drawImage(specCanvas, MARGIN.left, p2.top, plotW, p2.height);
    bgCtx.restore();
  }}

  const APP_FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
  bgCtx.font = "12px " + APP_FONT;
  const durationSpan = xMax - xMin;
  const stepT = durationSpan <= 0.8 ? 0.05 : (durationSpan <= 2.0 ? 0.1 : (durationSpan <= 4.5 ? 0.25 : 0.5));
  const firstTick = Math.ceil(xMin / stepT) * stepT;

  panels.forEach((p) => {{
    for (let t = firstTick; t <= xMax + 1e-6; t += stepT) {{
      const x = tToX(t);
      bgCtx.strokeStyle = "rgba(148, 163, 184, 0.12)"; bgCtx.lineWidth = 1.0;
      bgCtx.beginPath(); bgCtx.moveTo(x, p.top); bgCtx.lineTo(x, p.bottom); bgCtx.stroke();
      bgCtx.strokeStyle = "#475569"; bgCtx.lineWidth = 1.5;
      bgCtx.beginPath(); bgCtx.moveTo(x, p.bottom); bgCtx.lineTo(x, p.bottom + 4); bgCtx.stroke();
      bgCtx.fillStyle = "#94A3B8"; bgCtx.textAlign = "center"; bgCtx.textBaseline = "top";
      bgCtx.fillText(t.toFixed(2), x, p.bottom + 5);
    }}
  }});

  // Panel 1: Waveform
  const waveMid = (p1.top + p1.bottom) / 2;
  bgCtx.strokeStyle = "#1E293B";
  bgCtx.beginPath(); bgCtx.moveTo(MARGIN.left, waveMid); bgCtx.lineTo(W - MARGIN.right, waveMid); bgCtx.stroke();

  const maxAmp = Math.max(...D.wave_y.map(Math.abs), 0.05);
  [-1.0, 0.0, 1.0].forEach(relVal => {{
    const absVal = relVal * maxAmp;
    const y = valToY(absVal, -maxAmp * 1.1, maxAmp * 1.1, p1);
    bgCtx.strokeStyle = "#334155"; bgCtx.lineWidth = 1.5;
    bgCtx.beginPath(); bgCtx.moveTo(MARGIN.left - 5, y); bgCtx.lineTo(MARGIN.left, y); bgCtx.stroke();
    bgCtx.fillStyle = "#94A3B8"; bgCtx.textAlign = "right"; bgCtx.textBaseline = "middle";
    bgCtx.fillText(relVal.toFixed(1), MARGIN.left - 8, y);
  }});

  bgCtx.save();
  bgCtx.beginPath(); bgCtx.rect(MARGIN.left, p1.top, plotW, p1.height); bgCtx.clip();
  bgCtx.strokeStyle = "#94A3B8"; bgCtx.lineWidth = 1.4;
  bgCtx.beginPath();
  for (let i = 0; i < D.wave_t.length; i++) {{
    const x = tToX(D.wave_t[i]);
    const y = valToY(D.wave_y[i], -maxAmp * 1.1, maxAmp * 1.1, p1);
    if (i === 0) bgCtx.moveTo(x, y); else bgCtx.lineTo(x, y);
  }}
  bgCtx.stroke(); bgCtx.restore();

  // Panel 2: 1-10kHz Spectrogram + COG Overlay
  const fMin2 = 1000;
  [2000, 4000, 5500, 7000, 9000].forEach(hz => {{
    if (hz > fMaxSpec) return;
    const y = valToY(hz, fMin2, fMaxSpec, p2);
    bgCtx.strokeStyle = hz === 5500 ? "rgba(16, 185, 129, 0.35)" : "rgba(148, 163, 184, 0.14)";
    bgCtx.lineWidth = 1.0;
    bgCtx.beginPath(); bgCtx.moveTo(MARGIN.left, y); bgCtx.lineTo(W - MARGIN.right, y); bgCtx.stroke();
    bgCtx.strokeStyle = "#475569"; bgCtx.lineWidth = 1.5;
    bgCtx.beginPath(); bgCtx.moveTo(MARGIN.left - 5, y); bgCtx.lineTo(MARGIN.left, y); bgCtx.stroke();
    bgCtx.fillStyle = "#94A3B8"; bgCtx.textAlign = "right"; bgCtx.textBaseline = "middle";
    bgCtx.fillText((hz / 1000).toFixed(1) + "k", MARGIN.left - 8, y);
  }});

  bgCtx.save();
  bgCtx.beginPath(); bgCtx.rect(MARGIN.left, p2.top, plotW, p2.height); bgCtx.clip();
  drawSeries(D.times, D.cog, fMin2, fMaxSpec, p2, "#F59E0B", 2.8);
  bgCtx.restore();

  // Panel 3: Sibilant Strike-Zone Gauge (2000 - 9000 Hz)
  const cMin = 2000, cMax = 9000;
  [2000, 2300, 3500, 4600, 5500, 7000, 8500].forEach(hz => {{
    const y = valToY(hz, cMin, cMax, p3);
    bgCtx.strokeStyle = "rgba(148, 163, 184, 0.12)"; bgCtx.lineWidth = 1.0;
    bgCtx.beginPath(); bgCtx.moveTo(MARGIN.left, y); bgCtx.lineTo(W - MARGIN.right, y); bgCtx.stroke();
    bgCtx.strokeStyle = "#475569"; bgCtx.lineWidth = 1.5;
    bgCtx.beginPath(); bgCtx.moveTo(MARGIN.left - 5, y); bgCtx.lineTo(MARGIN.left, y); bgCtx.stroke();
    bgCtx.fillStyle = "#94A3B8"; bgCtx.textAlign = "right"; bgCtx.textBaseline = "middle";
    bgCtx.fillText((hz / 1000).toFixed(1) + "k", MARGIN.left - 8, y);
  }});

  // /s/ Strike Zone (>= 5500 Hz)
  const yS5500 = valToY(5500, cMin, cMax, p3);
  const yTop3 = valToY(cMax, cMin, cMax, p3);
  bgCtx.save();
  bgCtx.fillStyle = "rgba(16, 185, 129, 0.10)";
  bgCtx.fillRect(MARGIN.left, yTop3, plotW, yS5500 - yTop3);
  bgCtx.strokeStyle = "rgba(16, 185, 129, 0.70)"; bgCtx.lineWidth = 1.5; bgCtx.setLineDash([6, 5]);
  bgCtx.beginPath(); bgCtx.moveTo(MARGIN.left, yS5500); bgCtx.lineTo(W - MARGIN.right, yS5500); bgCtx.stroke();
  bgCtx.restore();

  bgCtx.font = "bold 11.5px " + APP_FONT;
  bgCtx.fillStyle = "rgba(16, 185, 129, 0.92)"; bgCtx.textAlign = "right"; bgCtx.textBaseline = "top";
  bgCtx.fillText("/s/ STRIKE ZONE (≥ 5.5 kHz)", W - MARGIN.right - 8, yTop3 + 5);

  // /ʃ/ & Japanese [ɕ] Zone (3200 - 4600 Hz)
  const yShHigh = valToY(4600, cMin, cMax, p3);
  const yShLow = valToY(2300, cMin, cMax, p3);
  bgCtx.save();
  bgCtx.fillStyle = "rgba(56, 189, 248, 0.09)";
  bgCtx.fillRect(MARGIN.left, yShHigh, plotW, yShLow - yShHigh);
  bgCtx.strokeStyle = "rgba(56, 189, 248, 0.55)"; bgCtx.lineWidth = 1.2; bgCtx.setLineDash([4, 4]);
  bgCtx.beginPath();
  bgCtx.moveTo(MARGIN.left, yShHigh); bgCtx.lineTo(W - MARGIN.right, yShHigh);
  bgCtx.moveTo(MARGIN.left, yShLow); bgCtx.lineTo(W - MARGIN.right, yShLow);
  bgCtx.stroke();
  bgCtx.restore();

  bgCtx.font = "bold 11px " + APP_FONT;
  bgCtx.fillStyle = "rgba(56, 189, 248, 0.88)"; bgCtx.textAlign = "right"; bgCtx.textBaseline = "middle";
  bgCtx.fillText("/ʃ/ & JP「シ」[ɕ] ZONE (2.3–4.6 kHz)", W - MARGIN.right - 8, (yShHigh + yShLow) / 2);

  bgCtx.save();
  bgCtx.beginPath(); bgCtx.rect(MARGIN.left, p3.top, plotW, p3.height); bgCtx.clip();
  drawSeries(D.times, D.cog, cMin, cMax, p3, "#F59E0B", 3.2);
  bgCtx.restore();

  // 音素ラベル帯・境界破線描画
  drawPhonemeAnnotations(panels, plotW, APP_FONT);

  panels.forEach(p => {{
    bgCtx.strokeStyle = "#334155"; bgCtx.lineWidth = 1.5;
    bgCtx.beginPath(); bgCtx.moveTo(MARGIN.left, p.top); bgCtx.lineTo(MARGIN.left, p.bottom); bgCtx.lineTo(W - MARGIN.right, p.bottom); bgCtx.stroke();
  }});

  bgCtx.font = "bold 13.5px " + APP_FONT; bgCtx.fillStyle = "#CBD5E1";
  drawRotatedLabel("Waveform", 28, (p1.top + p1.bottom) / 2);
  drawRotatedLabel("1–10 kHz Spec", 28, (p2.top + p2.bottom) / 2);
  drawRotatedLabel("COG Strike (Hz)", 28, (p3.top + p3.bottom) / 2);

  bgCtx.fillStyle = "#94A3B8"; bgCtx.textAlign = "center"; bgCtx.textBaseline = "bottom";
  bgCtx.fillText("Time (s)", MARGIN.left + plotW / 2, H - 2);
}}

function drawSeries(times, values, vMin, vMax, panel, color, width) {{
  bgCtx.strokeStyle = color; bgCtx.lineWidth = width; bgCtx.lineJoin = "round";
  bgCtx.beginPath(); let penDown = false;
  for (let i = 0; i < times.length; i++) {{
    const val = values[i];
    if (val === null || val === undefined) {{ penDown = false; continue; }}
    const x = tToX(times[i]); const y = valToY(val, vMin, vMax, panel);
    if (!penDown) {{ bgCtx.moveTo(x, y); penDown = true; }} else {{ bgCtx.lineTo(x, y); }}
  }}
  bgCtx.stroke();
}}
function drawRotatedLabel(text, x, y) {{
  bgCtx.save(); bgCtx.translate(x, y); bgCtx.rotate(-Math.PI / 2);
  bgCtx.textAlign = "center"; bgCtx.textBaseline = "middle"; bgCtx.fillText(text, 0, 0); bgCtx.restore();
}}

function drawOverlay() {{
  ovCtx.clearRect(0, 0, W, H);
  const panels = getPanels();
  const topY = panels[0].top, botY = panels[2].bottom;
  if (Math.abs(selEnd - selStart) > 0.005) {{
    const sx = tToX(Math.min(selStart, selEnd)), ex = tToX(Math.max(selStart, selEnd));
    ovCtx.fillStyle = "rgba(255, 255, 255, 0.08)"; ovCtx.fillRect(sx, topY, ex - sx, botY - topY);
    ovCtx.strokeStyle = "rgba(255, 255, 255, 0.4)"; ovCtx.lineWidth = 1.0;
    ovCtx.beginPath(); ovCtx.moveTo(sx, topY); ovCtx.lineTo(sx, botY); ovCtx.moveTo(ex, topY); ovCtx.lineTo(ex, botY); ovCtx.stroke();
  }}
  const cx = tToX(cursorT);
  ovCtx.strokeStyle = "#EF4444"; ovCtx.lineWidth = 2.0;
  ovCtx.beginPath(); ovCtx.moveTo(cx, topY); ovCtx.lineTo(cx, botY); ovCtx.stroke();
  ovCtx.fillStyle = "#EF4444";
  ovCtx.beginPath(); ovCtx.moveTo(cx - 6, topY); ovCtx.lineTo(cx + 6, topY); ovCtx.lineTo(cx, topY + 8); ovCtx.closePath(); ovCtx.fill();
  ovCtx.beginPath(); ovCtx.moveTo(cx - 6, botY); ovCtx.lineTo(cx + 6, botY); ovCtx.lineTo(cx, botY - 8); ovCtx.closePath(); ovCtx.fill();

  let activePh = null;
  if (D.phonemes && D.phonemes.length > 0) {{
    activePh = D.phonemes.find(s => cursorT >= s.start && cursorT <= s.end);
  }}

  let idx = D.times.findIndex(t => t >= cursorT);
  let html = `<span style="color:#94A3B8;">Cursor:</span> ${{cursorT.toFixed(3)}} s`;
  if (activePh) {{
    html += `  |  <span style="color:#BAE6FD; font-weight:700;">/${{activePh.ipa}}/</span>`;
  }}
  if (idx !== -1 && D.cog[idx] !== null) {{
    const cVal = D.cog[idx];
    const cCol = cVal >= 5500 ? "#10B981" : (cVal >= 3200 && cVal <= 4600 ? "#38BDF8" : "#F59E0B");
    html += `  |  <span style="color:${{cCol}}; font-weight:700;">COG: ${{cVal}} Hz</span>`;
  }}
  readout.innerHTML = html;
}}

btnSpec.addEventListener("click", () => {{
  showSpec = !showSpec;
  btnSpec.textContent = showSpec ? "1-10kHz Spec: ON" : "1-10kHz Spec: OFF";
  btnSpec.classList.toggle("toggle-active", showSpec);
  drawBackground();
}});

btnPhonemes.addEventListener("click", () => {{
  showPhonemes = !showPhonemes;
  btnPhonemes.textContent = showPhonemes ? "Phonemes: ON" : "Phonemes: OFF";
  btnPhonemes.classList.toggle("toggle-active", showPhonemes);
  drawBackground();
}});

function startPlayback() {{
  if (!audioEl.src) return; stopPlayback();
  const rate = parseFloat(selRate.value);
  audioEl.playbackRate = rate;
  audioEl.preservesPitch = true; audioEl.mozPreservesPitch = true; audioEl.webkitPreservesPitch = true;
  const s = Math.min(selStart, selEnd), e = Math.max(selStart, selEnd);
  const playFrom = (cursorT >= s && cursorT < e - 0.02) ? cursorT : s;
  audioEl.currentTime = playFrom;
  isPlaying = true; btnPlay.textContent = "⏹ Stop (Space)"; btnPlay.className = "btn-play-active";
  audioEl.play().catch(() => stopPlayback());

  function tick() {{
    if (!isPlaying) return;
    cursorT = audioEl.currentTime;
    if (cursorT >= e || audioEl.ended) {{
      audioEl.pause(); isPlaying = false; cursorT = e;
      btnPlay.textContent = "▶ Play (Space)"; btnPlay.className = "btn-play-ready";
      drawOverlay(); return;
    }}
    drawOverlay(); animId = requestAnimationFrame(tick);
  }}
  animId = requestAnimationFrame(tick);
}}
function stopPlayback() {{
  audioEl.pause(); if (animId) cancelAnimationFrame(animId);
  isPlaying = false; btnPlay.textContent = "▶ Play (Space)"; btnPlay.className = "btn-play-ready";
}}
selRate.addEventListener("change", () => {{
  audioEl.playbackRate = parseFloat(selRate.value);
  audioEl.preservesPitch = true;
}});
btnPlay.addEventListener("click", () => isPlaying ? stopPlayback() : startPlayback());
btnReset.addEventListener("click", () => {{ stopPlayback(); selStart = xMin; selEnd = xMax; cursorT = (xMin + xMax) / 2; drawOverlay(); }});
btnDlPlot.addEventListener("click", () => {{
  const expCanvas = document.createElement("canvas");
  expCanvas.width = bgCanvas.width; expCanvas.height = bgCanvas.height;
  const eCtx = expCanvas.getContext("2d");
  eCtx.drawImage(bgCanvas, 0, 0); eCtx.drawImage(ovCanvas, 0, 0);
  const link = document.createElement("a");
  link.download = `NinjaPhonetics_${{D.export_name}}.png`; link.href = expCanvas.toDataURL("image/png"); link.click();
}});
btnDlAudio.addEventListener("click", () => {{
  if (!audioBlobUrl) return;
  const link = document.createElement("a"); link.download = `NinjaPhonetics_${{D.export_name}}.wav`; link.href = audioBlobUrl; link.click();
}});
window.addEventListener("keydown", (e) => {{
  if (e.code === "Space" && e.target === document.body) {{ e.preventDefault(); isPlaying ? stopPlayback() : startPlayback(); }}
}});

let dragMode = "none";
ovCanvas.addEventListener("mousemove", (e) => {{
  const rect = ovCanvas.getBoundingClientRect(); const mouseX = e.clientX - rect.left;
  if (dragMode === "none") ovCanvas.style.cursor = Math.abs(mouseX - tToX(cursorT)) <= 12 ? "ew-resize" : "crosshair";
  else if (dragMode === "cursor") {{ cursorT = xToT(mouseX); drawOverlay(); }}
  else if (dragMode === "select") {{ selEnd = xToT(mouseX); cursorT = selEnd; drawOverlay(); }}
}});
ovCanvas.addEventListener("mousedown", (e) => {{
  stopPlayback();
  const rect = ovCanvas.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;
  const clickT = xToT(mouseX);
  const panels = getPanels();

  if (showPhonemes && D.phonemes && mouseY >= panels[1].top && mouseY <= panels[1].top + 24) {{
    const hitPh = D.phonemes.find(s => clickT >= s.start && clickT <= s.end);
    if (hitPh) {{
      selStart = hitPh.start;
      selEnd = hitPh.end;
      cursorT = hitPh.start;
      drawOverlay();
      return;
    }}
  }}

  if (Math.abs(mouseX - tToX(cursorT)) <= 12) dragMode = "cursor";
  else {{ dragMode = "select"; selStart = clickT; selEnd = clickT; cursorT = clickT; drawOverlay(); }}
}});
window.addEventListener("mouseup", () => {{
  if (dragMode === "select") {{
    if (Math.abs(selEnd - selStart) < 0.015) {{ selStart = xMin; selEnd = xMax; }}
    else cursorT = Math.min(selStart, selEnd);
  }}
  dragMode = "none"; drawOverlay();
}});
window.addEventListener("resize", () => {{ drawBackground(); drawOverlay(); }});
drawBackground(); drawOverlay();

if (D.auto_play) setTimeout(() => {{ cursorT = xMin; startPlayback(); }}, 600);
</script>
</body>
</html>
"""