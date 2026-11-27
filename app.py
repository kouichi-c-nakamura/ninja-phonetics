"""
app.py: NinjaPhonetics Biofeedback Scope
"""
import os
import re
import soundfile as sf
import streamlit as st
import streamlit.components.v1 as components

from constants import (
    PRESETS,
    PRESET_DIR,
    B1_PRESET_DIR,
    B1_WORD_PRESETS,
    B1_PASSAGE_BENCHMARK,
    E2_PASSAGE_BENCHMARKS,
)
from ui_styles import SHURIKEN_ICON_MAIN, SHURIKEN_ICON_SM, APP_CUSTOM_CSS
from audio_processing import (
    decode_audio_bytes,
    extract_scope_data_from_bytes,
    extract_b1_sibilant_data_from_bytes,
    evaluate_user_rhythm,
    get_benchmark_word_raw_distributions,
)
from views_a1 import build_spike2_html
from views_b1 import build_b1_scope_html
from views_e2 import build_e2_multiview_canvas_html, build_clickable_word_map_html
from views_listening import render_ninja_listening

st.set_page_config(
    page_title="NinjaPhonetics",
    page_icon="assets/favicon.png",
    layout="wide",
    initial_sidebar_state="collapsed"
)
st.markdown(APP_CUSTOM_CSS, unsafe_allow_html=True)

VALID_MODES = {"RL", "SIBILANT", "RHYTHM", "LISTENING"}

if "app_mode" not in st.session_state:
    qp_mode = st.query_params.get("mode", "")
    st.session_state.app_mode = qp_mode if qp_mode in VALID_MODES else "RL"

if "nav_selected" not in st.session_state:
    # URLに ?mode=... が付いていれば選択済み、なければ初期状態（未選択）
    st.session_state.nav_selected = (st.query_params.get("mode", "") in VALID_MODES)

# セッション状態初期化
if "current_label" not in st.session_state: st.session_state.current_label = "お手本: Right (US)"
if "a1_target_word" not in st.session_state: st.session_state.a1_target_word = "right"
if "current_audio_bytes" not in st.session_state:
    init_path = os.path.join("presets", "right_us.wav")
    st.session_state.current_audio_bytes = open(init_path, "rb").read() if os.path.exists(init_path) else None
if "last_recorded_bytes" not in st.session_state: st.session_state.last_recorded_bytes = None
if "auto_play" not in st.session_state: st.session_state.auto_play = False

# B1 セッション状態初期化
if "a1_presets_open" not in st.session_state: st.session_state.a1_presets_open = True
if "b1_presets_open" not in st.session_state: st.session_state.b1_presets_open = True
if "b1_word_label" not in st.session_state: st.session_state.b1_word_label = "お手本: See (US)"
if "b1_target_word" not in st.session_state: st.session_state.b1_target_word = "see"
if "b1_word_audio_bytes" not in st.session_state:
    b1_init_w = os.path.join(B1_PRESET_DIR, "see_us.wav")
    st.session_state.b1_word_audio_bytes = open(b1_init_w, "rb").read() if os.path.exists(b1_init_w) else None
if "b1_word_last_rec" not in st.session_state: st.session_state.b1_word_last_rec = None
if "b1_word_auto_play" not in st.session_state: st.session_state.b1_word_auto_play = False

if "b1_twister_label" not in st.session_state: st.session_state.b1_twister_label = "お手本: US Native (Roger)"
if "b1_twister_audio_bytes" not in st.session_state:
    b1_init_t = B1_PASSAGE_BENCHMARK["us_audio"]
    st.session_state.b1_twister_audio_bytes = open(b1_init_t, "rb").read() if os.path.exists(b1_init_t) else None
if "b1_twister_last_rec" not in st.session_state: st.session_state.b1_twister_last_rec = None
if "b1_twister_auto_play" not in st.session_state: st.session_state.b1_twister_auto_play = False

# E2 セッション状態初期化
if "e2_selected_passage" not in st.session_state: st.session_state.e2_selected_passage = "P1_northwind"
if "e2_custom_text" not in st.session_state:
    st.session_state.e2_custom_text = E2_PASSAGE_BENCHMARKS["P1_northwind"]["target_text"]
if "e2_last_analyzed_text" not in st.session_state:
    st.session_state.e2_last_analyzed_text = st.session_state.e2_custom_text
if "e2_audio_bytes" not in st.session_state: st.session_state.e2_audio_bytes = None
if "e2_eval_history" not in st.session_state: st.session_state.e2_eval_history = []
if "e2_plot_view" not in st.session_state: st.session_state.e2_plot_view = "scatter2d"

# スマホ選択済み状態のときだけ、639px以下で上部ブランドヘッダーと4タブを非表示にする
# スマホ選択済み状態のときだけ、639px以下で上部ブランドヘッダーと4タブを非表示にする
hide_mobile_nav_css = """
    @media (max-width: 639px) {
        .brand-bar { display: none !important; }
        div[data-testid="stElementContainer"]:has(#top-nav-anchor),
        div[data-testid="stElementContainer"]:has(#top-nav-anchor) + div {
            display: none !important;
        }
    }
""" if st.session_state.nav_selected else """
    @media (max-width: 639px) {
        div[data-testid="stElementContainer"]:has(#mode-body-anchor) ~ div {
            display: none !important;
        }
    }
"""

st.markdown(
    f"""
    <style>
    header[data-testid="stHeader"] {{ display: none; }}
    .block-container {{
        padding-top: 0.35rem !important;
        padding-bottom: 0.2rem !important;
    }}
    /* PC (>=640px) ではスマホ用プルダウンハンドルを隠す */
    @media (min-width: 640px) {{
        div[data-testid="stElementContainer"]:has(#a1-preset-drawer-handle),
        div[data-testid="stElementContainer"]:has(#a1-preset-drawer-handle) + div,
        div[data-testid="stElementContainer"]:has(#b1-preset-drawer-handle),
        div[data-testid="stElementContainer"]:has(#b1-preset-drawer-handle) + div {{
            display: none !important;
        }}
    }}
    @media (max-width: 639px) {{
        div[data-testid="stElementContainer"]:has(#a1-preset-drawer-handle),
        div[data-testid="stElementContainer"]:has(#b1-preset-drawer-handle) {{
            display: none !important;
        }}
        div[data-testid="stElementContainer"]:has(#a1-preset-drawer-handle) + div button,
        div[data-testid="stElementContainer"]:has(#b1-preset-drawer-handle) + div button {{
            min-height: 28px !important;
            height: 28px !important;
            padding: 0 12px !important;
            font-size: 16px !important;
            line-height: 1 !important;
            color: #38bdf8 !important;
            background: rgba(15, 23, 42, 0.85) !important;
            border: 1px solid #1e293b !important;
            border-radius: 6px !important;
            margin: 2px 0 !important;
        }}
    }}
    {hide_mobile_nav_css}
    </style>
    """,
    unsafe_allow_html=True,
)

# スマホ用プルダウンハンドル（選択済みなら ▾ で開く、開いている間は ▴ で閉じる）
st.markdown('<span id="mobile-drawer-handle" style="display:none;"></span>', unsafe_allow_html=True)
handle_icon = "▼" if st.session_state.nav_selected else "▲"
if st.button(handle_icon, key="mob_nav_drawer_btn", use_container_width=True):
    st.session_state.nav_selected = not st.session_state.nav_selected
    st.rerun()

# =============================================================
# トップレベルナビゲーション (1セットのみ: PCは横4列 / スマホ初期は縦4列)
# =============================================================
st.markdown(
    f'<div class="brand-bar">{SHURIKEN_ICON_MAIN}'
    f'<span class="brand-title">NinjaPhonetics: Biofeedback Scope</span>'
    f'<span class="brand-sub">ACOUSTIC & PROSODY DIAGNOSTICS</span></div>'
    f'<span id="top-nav-anchor" style="display:none;"></span>',
    unsafe_allow_html=True,
)

tab_m1, tab_m2, tab_m3, tab_m4 = st.columns([1.45, 1.55, 1.55, 1.45])
with tab_m1:
    if st.button("A1: 音素ホルマント (R / L)", key="nav_a1", type="primary" if st.session_state.app_mode == "RL" else "secondary", use_container_width=True):
        st.session_state.app_mode = "RL"
        st.session_state.nav_selected = True
        st.query_params["mode"] = "RL"
        st.rerun()
with tab_m2:
    if st.button("B1: 歯擦音スコープ (/si/ vs /ʃi/)", key="nav_b1", type="primary" if st.session_state.app_mode == "SIBILANT" else "secondary", use_container_width=True):
        st.session_state.app_mode = "SIBILANT"
        st.session_state.nav_selected = True
        st.query_params["mode"] = "SIBILANT"
        st.rerun()
with tab_m3:
    if st.button("E2: プロソディ＆ストレス拍診断", key="nav_e2", type="primary" if st.session_state.app_mode == "RHYTHM" else "secondary", use_container_width=True):
        st.session_state.app_mode = "RHYTHM"
        st.session_state.nav_selected = True
        st.query_params["mode"] = "RHYTHM"
        st.rerun()
with tab_m4:
    if st.button("L1: Ninja Listening (YouTube)", key="nav_l1", type="primary" if st.session_state.app_mode == "LISTENING" else "secondary", use_container_width=True):
        st.session_state.app_mode = "LISTENING"
        st.session_state.nav_selected = True
        st.query_params["mode"] = "LISTENING"
        st.rerun()
st.markdown('<span id="mode-body-anchor" style="display:none;"></span>', unsafe_allow_html=True)

# -------------------------------------------------------------
# A1 モード
# -------------------------------------------------------------
if st.session_state.app_mode == "RL":
    st.markdown('<span id="a1-preset-drawer-handle" style="display:none;"></span>', unsafe_allow_html=True)
    a1_drawer_label = f"▲ 単語プリセットを隠す ({st.session_state.current_label})" if st.session_state.a1_presets_open else f"▼ 単語プリセットを選択 ({st.session_state.current_label})"
    if st.button(a1_drawer_label, key="a1_preset_drawer_btn", use_container_width=True):
        st.session_state.a1_presets_open = not st.session_state.a1_presets_open
        st.rerun()

    active_preset_info = next(
        (p for p in PRESETS if st.session_state.current_label == f"お手本: {p['label']}"),
        None,
    )
    preset_clicked = False

    if st.session_state.a1_presets_open:
        cols = st.columns(len(PRESETS))
        for idx, col in enumerate(cols):
            p_info = PRESETS[idx]
            is_active = (st.session_state.current_label == f"お手本: {p_info['label']}")
            if col.button(p_info["label"], type="primary" if is_active else "secondary", use_container_width=True):
                fpath = os.path.join(PRESET_DIR, p_info["file"])
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        st.session_state.current_audio_bytes = f.read()
                        st.session_state.current_label = f"お手本: {p_info['label']}"
                        st.session_state.a1_target_word = p_info.get("target_word", "right")
                        st.session_state["a1_word_input"] = st.session_state.a1_target_word
                        st.session_state.auto_play = True
                        st.session_state.a1_presets_open = False
                    preset_clicked = True
                    st.rerun()

    in_col1, in_col2 = st.columns([1.3, 2.7], vertical_alignment="bottom")
    with in_col1:
        typed_word = st.text_input(
            "1. 発音する英単語を入力 (音素境界を自動検出)",
            value=st.session_state.a1_target_word,
            placeholder="例: right, light, really, very...",
            key="a1_word_input"
        )
        st.session_state.a1_target_word = typed_word.strip()

    has_target_word = bool(st.session_state.a1_target_word)
    with in_col2:
        rec_label = (
            f"2. 「{st.session_state.a1_target_word}」を録音して解析 (R / L)"
            if has_target_word
            else "2. ⬅ 先に左欄へ発音する英単語を入力すると録音可能になります"
        )
        audio_input = st.audio_input(rec_label, disabled=not has_target_word, key="a1_audio_in")

    if not preset_clicked and audio_input is not None and has_target_word:
        new_bytes = audio_input.read()
        if new_bytes != st.session_state.last_recorded_bytes:
            st.session_state.last_recorded_bytes = new_bytes
            st.session_state.current_audio_bytes = new_bytes
            st.session_state.current_label = f"あなたの発音録音: {st.session_state.a1_target_word}"
            st.session_state.auto_play = False

    if st.session_state.current_audio_bytes is not None:
        if st.session_state.current_label:
            st.markdown(f"<div class='sec-header'>{SHURIKEN_ICON_SM} 表示中: <span style='color: #F8FAFC;'>{st.session_state.current_label}</span></div>", unsafe_allow_html=True)

        clean_name = re.sub(r'[^a-zA-Z0-9_\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', '_', st.session_state.current_label).strip('_')
        scope_data = extract_scope_data_from_bytes(
            st.session_state.current_audio_bytes,
            target_text=st.session_state.a1_target_word
        )
        html_code = build_spike2_html(scope_data, auto_play=st.session_state.auto_play, export_name=clean_name or "sample")
        st.session_state.auto_play = False
        components.html(html_code, height=590, scrolling=False)

        if active_preset_info and active_preset_info.get("desc"):
            st.markdown(f"""
            <div style="background: #0F172A; border: 1px solid #1E293B; border-left: 4px solid #38BDF8; border-radius: 8px; padding: 12px 18px; margin-top: 6px;">
              <div style="font-size: 0.82rem; font-weight: 700; color: #38BDF8; text-transform: uppercase; margin-bottom: 2px;">
                {active_preset_info.get('phonetics', '')}
              </div>
              <div style="font-size: 1.15rem; font-weight: 800; color: #F8FAFC; margin-bottom: 4px;">
                {active_preset_info.get('title', '')}
              </div>
              <div style="font-size: 0.88rem; color: #94A3B8; line-height: 1.5;">
                {active_preset_info.get('desc', '')}
              </div>
            </div>
            """, unsafe_allow_html=True)

# -------------------------------------------------------------
# B1 モード (/si/ vs /ʃi/ 歯擦音スペクトル重心スコープ)
# -------------------------------------------------------------
elif st.session_state.app_mode == "SIBILANT":
    sub_word, sub_twister = st.tabs([
        "1. 単語キャリブレーション (/si/ vs /ʃi/ 単音比較)",
        "2. 早口言葉チャレンジ (She sells seashells)"
    ])

    # === Subtab 1: 単語キャリブレーション ===
    with sub_word:
        row1_presets = B1_WORD_PRESETS[:9]   # US / UK 英語 9種
        row2_presets = B1_WORD_PRESETS[9:]   # JP カタカナトラップ 4種

        st.markdown('<span id="b1-preset-drawer-handle" style="display:none;"></span>', unsafe_allow_html=True)
        b1_drawer_label = f"▲ 単語プリセットを隠す ({st.session_state.b1_word_label})" if st.session_state.b1_presets_open else f"▼ 単語プリセットを選択 ({st.session_state.b1_word_label})"
        if st.button(b1_drawer_label, key="b1_preset_drawer_btn", use_container_width=True):
            st.session_state.b1_presets_open = not st.session_state.b1_presets_open
            st.rerun()

        b1_preset_clicked = False
        active_b1_info = next(
            (p for p in B1_WORD_PRESETS if st.session_state.b1_word_label == f"お手本: {p['label']}"),
            None,
        )

        if st.session_state.b1_presets_open:
            cols_r1 = st.columns(len(row1_presets))
        for idx, col in enumerate(cols_r1):
            p_info = row1_presets[idx]
            is_act = (st.session_state.b1_word_label == f"お手本: {p_info['label']}")
            if is_act:
                active_b1_info = p_info
            if col.button(p_info["label"], key=f"b1_r1_{idx}", type="primary" if is_act else "secondary", use_container_width=True):
                fpath = os.path.join(B1_PRESET_DIR, p_info["file"])
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        st.session_state.b1_word_audio_bytes = f.read()
                        st.session_state.b1_word_label = f"お手本: {p_info['label']}"
                        st.session_state.b1_target_word = p_info["target_word"]
                        st.session_state["b1_word_input"] = p_info["target_word"]
                        st.session_state.b1_word_auto_play = True
                    b1_preset_clicked = True
                    st.rerun()

        cols_r2 = st.columns([1.2, 1.2, 1.2, 1.2, 4.2])
        for idx, p_info in enumerate(row2_presets):
            is_act = (st.session_state.b1_word_label == f"お手本: {p_info['label']}")
            if is_act:
                active_b1_info = p_info
            if cols_r2[idx].button(p_info["label"], key=f"b1_r2_{idx}", type="primary" if is_act else "secondary", use_container_width=True):
                fpath = os.path.join(B1_PRESET_DIR, p_info["file"])
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        st.session_state.b1_word_audio_bytes = f.read()
                        st.session_state.b1_word_label = f"お手本: {p_info['label']}"
                        st.session_state.b1_target_word = p_info["target_word"]
                        st.session_state["b1_word_input"] = p_info["target_word"]
                        st.session_state.b1_word_auto_play = True
                    b1_preset_clicked = True
                    st.rerun()

        b1_in1, b1_in2 = st.columns([1.3, 2.7], vertical_alignment="bottom")
        with b1_in1:
            b1_typed = st.text_input(
                "1. 発音する単語を入力 (see, she, seat, sheet, sip, ship, city...)",
                value=st.session_state.b1_target_word,
                placeholder="例: see, she, seat, sheet, city...",
                key="b1_word_input"
            )
            st.session_state.b1_target_word = b1_typed.strip()

        has_b1_word = bool(st.session_state.b1_target_word)
        with b1_in2:
            b1_rec_label = (
                f"2. 「{st.session_state.b1_target_word}」を録音してCOG解析"
                if has_b1_word
                else "2. ⬅ 先に左欄へ発音する英単語を入力すると録音可能になります"
            )
            b1_audio_in = st.audio_input(b1_rec_label, disabled=not has_b1_word, key="b1_word_audio_in")

        if not b1_preset_clicked and b1_audio_in is not None and has_b1_word:
            new_b1_bytes = b1_audio_in.read()
            if new_b1_bytes != st.session_state.b1_word_last_rec:
                st.session_state.b1_word_last_rec = new_b1_bytes
                st.session_state.b1_word_audio_bytes = new_b1_bytes
                st.session_state.b1_word_label = f"あなたの発音録音: {st.session_state.b1_target_word}"
                st.session_state.b1_word_auto_play = False

        if st.session_state.b1_word_audio_bytes is not None:
            b1_data = extract_b1_sibilant_data_from_bytes(
                st.session_state.b1_word_audio_bytes,
                target_text=st.session_state.b1_target_word,
                is_passage=False
            )
            b1_sum = b1_data["summary"]

            hdr_c1, hdr_c2 = st.columns([2.2, 1.8])
            with hdr_c1:
                st.markdown(f"<div class='sec-header'>{SHURIKEN_ICON_SM} 表示中: <span style='color: #F8FAFC;'>{st.session_state.b1_word_label}</span></div>", unsafe_allow_html=True)
            with hdr_c2:
                st.markdown(
                    f"<div style='text-align:right; padding-top:4px;'>"
                    f"<span style='background:#0F172A; border:1px solid {b1_sum['color']}; color:{b1_sum['color']}; "
                    f"padding:3px 10px; border-radius:6px; font-weight:800; font-size:0.88rem;'>"
                    f"{b1_sum['verdict']} ({b1_sum['mean_s_cog']:.0f} Hz)</span></div>",
                    unsafe_allow_html=True
                )

            clean_b1_name = re.sub(r'[^a-zA-Z0-9_\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', '_', st.session_state.b1_word_label).strip('_')
            b1_html = build_b1_scope_html(b1_data, auto_play=st.session_state.b1_word_auto_play, export_name=clean_b1_name or "b1_word", scope_height=510)
            st.session_state.b1_word_auto_play = False
            components.html(b1_html, height=570, scrolling=False)

            st.markdown(f"""
            <div style="background: #0F172A; border: 1px solid #1E293B; border-left: 4px solid {b1_sum['color']}; border-radius: 8px; padding: 12px 18px; margin-top: 4px;">
              <div style="font-size: 0.90rem; color: #F8FAFC; font-weight: 700; margin-bottom: 4px;">
                💡 音響診断: {b1_sum['advice']}
              </div>
              <div style="font-size: 0.85rem; color: #94A3B8; line-height: 1.45;">
                {active_b1_info.get('desc', '') if active_b1_info else '目標: /s/ は 5,500 Hz 以上の緑色ゾーン、/ʃ/ は 3,200〜4,600 Hz の青色ゾーンへ明確に分離します。'}
              </div>
            </div>
            """, unsafe_allow_html=True)

    # === Subtab 2: 早口言葉チャレンジ (She sells seashells) ===
    with sub_twister:
        st.markdown(f"""
        <div style="background: #0F172A; border: 1px solid #1E293B; border-left: 4px solid #10B981; border-radius: 8px; padding: 12px 18px; margin-bottom: 10px;">
          <div style="font-size: 0.78rem; font-weight: 700; color: #10B981; text-transform: uppercase; letter-spacing: 0.05em;">
            COARTICULATION STRESS TEST (/s/ ↔ /ʃ/ ALTERNATION)
          </div>
          <div style="font-size: 1.18rem; font-weight: 800; color: #F8FAFC; margin: 4px 0;">
            “{B1_PASSAGE_BENCHMARK['target_text']}”
          </div>
          <div style="font-size: 0.85rem; color: #94A3B8; font-family: monospace;">
            {B1_PASSAGE_BENCHMARK['ipa_guide']}
          </div>
        </div>
        """, unsafe_allow_html=True)

        tw_b1, tw_b2, tw_b3, tw_rec_col = st.columns([1.0, 1.0, 1.1, 2.9], vertical_alignment="bottom")
        tw_clicked = False
        with tw_b1:
            if st.button("US お手本", key="b1_tw_us", type="primary" if "US Native" in st.session_state.b1_twister_label else "secondary", use_container_width=True):
                if os.path.exists(B1_PASSAGE_BENCHMARK["us_audio"]):
                    st.session_state.b1_twister_audio_bytes = open(B1_PASSAGE_BENCHMARK["us_audio"], "rb").read()
                    st.session_state.b1_twister_label = "お手本: US Native (Roger)"
                    st.session_state.b1_twister_auto_play = True
                    tw_clicked = True
                    st.rerun()
        with tw_b2:
            if st.button("UK お手本", key="b1_tw_uk", type="primary" if "UK Native" in st.session_state.b1_twister_label else "secondary", use_container_width=True):
                if os.path.exists(B1_PASSAGE_BENCHMARK["uk_audio"]):
                    st.session_state.b1_twister_audio_bytes = open(B1_PASSAGE_BENCHMARK["uk_audio"], "rb").read()
                    st.session_state.b1_twister_label = "お手本: UK Native (Archer)"
                    st.session_state.b1_twister_auto_play = True
                    tw_clicked = True
                    st.rerun()
        with tw_b3:
            if st.button("JP カタカナ比較", key="b1_tw_jp", type="primary" if "JP Katakana" in st.session_state.b1_twister_label else "secondary", use_container_width=True):
                if os.path.exists(B1_PASSAGE_BENCHMARK["jp_audio"]):
                    st.session_state.b1_twister_audio_bytes = open(B1_PASSAGE_BENCHMARK["jp_audio"], "rb").read()
                    st.session_state.b1_twister_label = "比較: JP Katakana (シー・セルズ...)"
                    st.session_state.b1_twister_auto_play = True
                    tw_clicked = True
                    st.rerun()
        with tw_rec_col:
            tw_audio_in = st.audio_input("上の2文を読み上げて /s/ ↔ /ʃ/ の分離落差を計測", key="b1_twister_audio_in")

        if not tw_clicked and tw_audio_in is not None:
            new_tw_bytes = tw_audio_in.read()
            if new_tw_bytes != st.session_state.b1_twister_last_rec:
                st.session_state.b1_twister_last_rec = new_tw_bytes
                st.session_state.b1_twister_audio_bytes = new_tw_bytes
                st.session_state.b1_twister_label = "あなたの早口言葉録音"
                st.session_state.b1_twister_auto_play = False

        if st.session_state.b1_twister_audio_bytes is not None:
            tw_data = extract_b1_sibilant_data_from_bytes(
                st.session_state.b1_twister_audio_bytes,
                target_text=B1_PASSAGE_BENCHMARK["target_text"],
                is_passage=True
            )
            tw_sum = tw_data["summary"]

            m_c1, m_c2, m_c3, m_c4 = st.columns(4)
            m_c1.metric("総合判定", tw_sum["verdict"])
            m_c2.metric("平均 /s/ COG (目標 ≥5.5k)", f"{tw_sum['mean_s_cog']:.0f} Hz")
            m_c3.metric("平均 /ʃ/ COG (目標 3.2-4.6k)", f"{tw_sum['mean_sh_cog']:.0f} Hz")
            m_c4.metric("分離落差 ΔCOG (目標 ≥1.6k)", f"+{tw_sum['sep_delta']:.0f} Hz")

            tw_html = build_b1_scope_html(tw_data, auto_play=st.session_state.b1_twister_auto_play, export_name="b1_seashells", scope_height=480)
            st.session_state.b1_twister_auto_play = False
            components.html(tw_html, height=540, scrolling=False)

            st.markdown(f"""
            <div style="background: #0F172A; border: 1px solid #1E293B; border-left: 4px solid {tw_sum['color']}; border-radius: 8px; padding: 10px 16px; margin-bottom: 10px; font-size: 0.90rem; color: #F8FAFC;">
              💡 <b>鋸歯状（ノコギリ波）COG 診断:</b> {tw_sum['advice']}
            </div>
            """, unsafe_allow_html=True)

            # 全歯擦音トークンの個別実測カード
            tokens = tw_data.get("sibilant_tokens", [])
            if tokens:
                st.markdown("<div style='font-size:0.9rem; font-weight:700; color:#BAE6FD; margin-bottom:6px;'>全歯擦音トークン別 COG スコアカード (/s/ vs /ʃ/ の切り替え精度)</div>", unsafe_allow_html=True)
                cards_html = '<div style="display:flex; flex-wrap:wrap; gap:8px;">'
                for tk in tokens:
                    cards_html += (
                        f'<div style="background:#0F172A; border:1px solid {tk["color"]}; border-radius:6px; padding:6px 10px; min-width:115px;">'
                        f'<div style="font-size:11px; color:#94A3B8;">{tk["word"]} <span style="color:#E2E8F0; font-weight:700;">/{tk["ipa"]}/</span></div>'
                        f'<div style="font-size:14px; font-weight:800; color:{tk["color"]}; font-variant-numeric:tabular-nums;">{tk["cog_hz"]:.0f} Hz</div>'
                        f'<div style="font-size:10px; font-weight:700; color:{tk["color"]};">{tk["status"]}</div>'
                        f'</div>'
                    )
                cards_html += "</div>"
                st.markdown(cards_html, unsafe_allow_html=True)

# -------------------------------------------------------------
# E2 モード (長文ベンチマーク専用)
# -------------------------------------------------------------
elif st.session_state.app_mode == "RHYTHM":
    p_col1, p_col2, p_col3, _ = st.columns([1.3, 1.3, 1.3, 2.1])
    with p_col1:
        if st.button("P1: 北風と太陽 (113語)", type="primary" if st.session_state.e2_selected_passage == "P1_northwind" else "secondary", use_container_width=True):
            st.session_state.e2_selected_passage = "P1_northwind"
            t_txt = E2_PASSAGE_BENCHMARKS["P1_northwind"]["target_text"]
            st.session_state.e2_custom_text = st.session_state.e2_last_analyzed_text = st.session_state["e2_text_input_widget"] = t_txt
            st.session_state.e2_eval_history = []
            st.rerun()
    with p_col2: st.button("P2: 虹のパッセージ", disabled=True, use_container_width=True)
    with p_col3: st.button("P3: 祖父のパッセージ", disabled=True, use_container_width=True)

    active_bm = E2_PASSAGE_BENCHMARKS[st.session_state.e2_selected_passage]

    txt_col1, txt_col2 = st.columns([4.8, 1.0], vertical_alignment="bottom")
    with txt_col1:
        user_target_text = st.text_area(
            "課題テキスト (自由に書き換え可能)", 
            value=st.session_state.e2_custom_text, 
            height=170, 
            key="e2_text_input_widget"
        )
    with txt_col2:
        if st.button("例文に戻す", use_container_width=True):
            t_txt = active_bm["target_text"]
            st.session_state.e2_custom_text = st.session_state.e2_last_analyzed_text = st.session_state["e2_text_input_widget"] = t_txt
            st.session_state.e2_eval_history, st.session_state.e2_audio_bytes = [], None
            st.rerun()

    if user_target_text.strip() != st.session_state.e2_last_analyzed_text.strip():
        st.session_state.e2_custom_text = st.session_state.e2_last_analyzed_text = user_target_text.strip()
        st.session_state.e2_eval_history, st.session_state.e2_audio_bytes = [], None

    is_custom_now = (" ".join(st.session_state.e2_custom_text.lower().split()) != " ".join(active_bm["target_text"].lower().split()))

    card_col1, card_col2 = st.columns([1.45, 1.05])
    with card_col1:
        e2_input = st.audio_input("この英文を録音してプロソディ診断を実行", key="e2_audio_in")
        e2_uploaded_file = st.file_uploader("または音声ファイルをアップロード (WAV / MP3 / M4A)", type=["wav", "mp3", "m4a"], key="e2_file_in")

        active_bytes = None
        if e2_input is not None:
            active_bytes = e2_input.getvalue()
        elif e2_uploaded_file is not None:
            active_bytes = e2_uploaded_file.getvalue()

        if active_bytes and active_bytes != st.session_state.get("e2_last_seen_bytes"):
            st.session_state["e2_last_seen_bytes"] = active_bytes
            st.session_state.e2_audio_bytes = active_bytes

            audio_arr, sr = decode_audio_bytes(active_bytes)
            tmp_wav = "tmp_e2_active.wav"
            sf.write(tmp_wav, audio_arr, sr, format="WAV")

            eval_res = evaluate_user_rhythm(tmp_wav, st.session_state.e2_selected_passage, st.session_state.e2_custom_text)
            if os.path.exists(tmp_wav):
                try: os.remove(tmp_wav)
                except Exception: pass

            st.session_state.e2_eval_history.append(eval_res)

        if st.session_state.e2_audio_bytes is not None:
            _, dl_col2 = st.columns([1.8, 1.2])
            with dl_col2:
                st.download_button(label="録音音声を保存 (.wav)", data=st.session_state.e2_audio_bytes, file_name=f"NinjaPhonetics_{st.session_state.e2_selected_passage}_recording.wav", mime="audio/wav", use_container_width=True)

        word_bench_dist = get_benchmark_word_raw_distributions(st.session_state.e2_selected_passage) if not is_custom_now else {}
        radar_html = build_e2_multiview_canvas_html(
            st.session_state.e2_selected_passage, st.session_state.e2_eval_history,
            is_custom_mode=is_custom_now, view_mode=st.session_state.e2_plot_view, word_bench_dist=word_bench_dist
        )
        components.html(radar_html, height=465, scrolling=False)

    with card_col2:
        st.markdown(f"<div class='sec-header'>{SHURIKEN_ICON_SM} 多次元プロソディ診断結果 (プロット表示切替)</div>", unsafe_allow_html=True)
        v_btn1, v_btn2, v_btn3 = st.columns(3)
        with v_btn1:
            if st.button("1. 2D 総合楕円", type="primary" if st.session_state.e2_plot_view == "scatter2d" else "secondary", use_container_width=True):
                st.session_state.e2_plot_view = "scatter2d"; st.rerun()
        with v_btn2:
            if st.button("2. 指標 1D 分布", type="primary" if st.session_state.e2_plot_view == "metrics_1d" else "secondary", use_container_width=True):
                st.session_state.e2_plot_view = "metrics_1d"; st.rerun()
        with v_btn3:
            if st.button("3. 機能語 Swarm", type="primary" if st.session_state.e2_plot_view == "word_swarm" else "secondary", use_container_width=True):
                st.session_state.e2_plot_view = "word_swarm"; st.rerun()

        if st.session_state.e2_eval_history:
            latest_ev = st.session_state.e2_eval_history[-1]
            trial_no = len(st.session_state.e2_eval_history)
            dm_str = f"{latest_ev.get('d_m_sq', 'N/A')} (≤9.21 合格)" if latest_ev.get("d_m_sq") is not None else "自由文判定"
            c_diag = "#10B981" if latest_ev.get("diag_median_ms", 99) <= 48.0 else ("#F59E0B" if latest_ev.get("diag_median_ms", 99) <= 65.0 else "#EF4444")
            c_schwa = "#10B981" if latest_ev.get("schwa_p75_ms", 99) <= 65.0 else "#EF4444"
            c_rcf = "#10B981" if latest_ev.get("r_cf", 0) >= 1.30 else "#EF4444"
            c_npvi = "#10B981" if 40.0 <= latest_ev.get("npvi_clipped", 0) <= 62.0 else "#F59E0B"

            summary_html = (
                f'<div style="background: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 12px; margin-top: 6px; margin-bottom: 10px;">'
                f'<div style="display: flex; justify-content: space-between; align-items: baseline;">'
                f'<span style="font-size: 0.82rem; color: #94A3B8; font-weight: 600;">VERDICT (Trial #{trial_no})</span>'
                f'<span style="font-size: 0.78rem; color: #64748B;">蓄積データ: {trial_no} 件</span></div>'
                f'<div style="font-size: 1.45rem; font-weight: 800; color: {latest_ev.get("status_color", "#EF4444")}; margin-bottom: 8px;">{latest_ev.get("verdict", "OFF TARGET")}</div>'
                f'<div style="display: flex; justify-content: space-between; border-bottom: 1px solid #1E293B; padding-bottom: 4px; margin-bottom: 4px;">'
                f'<span style="color: #BAE6FD; font-size: 0.86rem; font-weight: 700;">弱化必須語 中央値 (V<sub>diag</sub>):</span>'
                f'<span style="font-weight: 800; color: {c_diag};">{latest_ev.get("diag_median_ms", 0)} ms <small style="font-size:0.75rem; color:#94A3B8;">(目標 ≤45ms)</small></span></div>'
                f'<div style="display: flex; justify-content: space-between; border-bottom: 1px solid #1E293B; padding-bottom: 4px; margin-bottom: 4px;">'
                f'<span style="color: #94A3B8; font-size: 0.86rem;">弱母音持続時間 (Schwa P75):</span>'
                f'<span style="font-weight: bold; color: {c_schwa};">{latest_ev.get("schwa_p75_ms", 0):.1f} ms <small style="font-size:0.75rem; color:#94A3B8;">(目標 ≤65ms)</small></span></div>'
                f'<div style="display: flex; justify-content: space-between; border-bottom: 1px solid #1E293B; padding-bottom: 4px; margin-bottom: 4px;">'
                f'<span style="color: #94A3B8; font-size: 0.86rem;">内容語/機能語比 (R<sub>CF</sub>):</span>'
                f'<span style="font-weight: bold; color: {c_rcf};">{latest_ev.get("r_cf", 0)}x <small style="font-size:0.75rem; color:#94A3B8;">(内容 {latest_ev.get("mean_c_ms", 0)}ms / 機能 {latest_ev.get("mean_f_ms", 0)}ms)</small></span></div>'
                f'<div style="display: flex; justify-content: space-between; border-bottom: 1px solid #1E293B; padding-bottom: 4px; margin-bottom: 4px;">'
                f'<span style="color: #94A3B8; font-size: 0.86rem;">リズム伸縮指数 (nPVI-V):</span>'
                f'<span style="font-weight: bold; color: {c_npvi};">{latest_ev.get("npvi_clipped", 0)} <small style="font-size:0.75rem; color:#94A3B8;">(適正 40〜60)</small></span></div>'
                f'<div style="display: flex; justify-content: space-between; margin-bottom: 8px;">'
                f'<span style="color: #94A3B8; font-size: 0.86rem;">2D Mahalanobis (D<sub>M</sub><sup>2</sup>):</span>'
                f'<span style="font-weight: bold; color: #F8FAFC;">{dm_str}</span></div>'
                f'<div style="background: #090D16; border-radius: 6px; padding: 8px; font-size: 0.83rem; color: #E2E8F0; line-height: 1.4;">'
                f'💡 <b>フィードバック:</b> {latest_ev.get("feedback", "")}</div></div>'
            )
            st.markdown(summary_html, unsafe_allow_html=True)

            wb_list = latest_ev.get("word_breakdown", [])
            diag_words_meas = [w for w in wb_list if w.get("is_diag")]
            if diag_words_meas:
                st.markdown("<div style='font-size: 0.88rem; font-weight: bold; color: #BAE6FD; margin-top: 2px; margin-bottom: 4px;'>弱化必須語 (冠詞除く) の実測母音長一覧</div>", unsafe_allow_html=True)
                rows_html = ""
                for idx_w, dw in enumerate(diag_words_meas):
                    v_val = dw["vowel_ms"]
                    if v_val <= 48.0: status_txt, bar_c, badge_style = "合格", "#10B981", "background:#064E3B; color:#A7F3D0; border:1px solid #10B981;"
                    elif v_val <= 65.0: status_txt, bar_c, badge_style = "やや長", "#F59E0B", "background:#78350F; color:#FDE68A; border:1px solid #F59E0B;"
                    else: status_txt, bar_c, badge_style = "引き伸ばし", "#EF4444", "background:#7F1D1D; color:#FECACA; border:1px solid #EF4444;"
                    bar_w = min(100, int((v_val / 130.0) * 100))
                    rows_html += (
                        f'<tr style="border-bottom: 1px solid #1E293B; font-size: 12px;">'
                        f'<td style="padding: 4px 6px; color: #64748B;">#{idx_w+1}</td>'
                        f'<td style="padding: 4px 6px; font-weight: 700; color: #F8FAFC;">{dw["word"]}</td>'
                        f'<td style="padding: 4px 6px; font-weight: 700; color: {bar_c}; font-variant-numeric: tabular-nums;">{v_val:.0f} ms</td>'
                        f'<td style="padding: 4px 6px; width: 34%;"><div style="background:#1E293B; height:7px; border-radius:4px; overflow:hidden;"><div style="width:{bar_w}%; background:{bar_c}; height:100%;"></div></div></td>'
                        f'<td style="padding: 4px 6px; text-align: right;"><span style="{badge_style} padding: 1px 5px; border-radius: 4px; font-size: 10.5px; font-weight: bold;">{status_txt}</span></td></tr>'
                    )
                table_html = f"""<!DOCTYPE html><html><head><style>
body {{ margin: 0; padding: 0; background: #0F172A; color: #E2E8F0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", sans-serif; }}
.tbl-box {{ max-height: 175px; overflow-y: auto; border: 1px solid #1E293B; border-radius: 6px; padding: 2px 6px; background: #0F172A; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ position: sticky; top: 0; background: #0F172A; color: #94A3B8; font-size: 11px; text-align: left; padding: 4px 6px; border-bottom: 1px solid #334155; }}
</style></head><body>
<div class="tbl-box"><table><thead><tr><th>順</th><th>単語</th><th>母音長</th><th>ゲージ (目標≤45ms)</th><th style="text-align:right;">判定</th></tr></thead><tbody>{rows_html}</tbody></table></div></body></html>"""
                components.html(table_html, height=185, scrolling=False)

            if st.button("この課題の試行履歴をクリア", use_container_width=True):
                st.session_state.e2_eval_history, st.session_state.e2_audio_bytes, st.session_state["e2_last_seen_bytes"] = [], None, None; st.rerun()
        else:
            st.markdown("""<div style="background: #0F172A; border: 1px dashed #334155; border-radius: 8px; padding: 24px; text-align: center; color: #94A3B8;">
左側のマイクボタンを押して、英文を読み上げてください。<br><br>
2D ストライクゾーン (R_CF × Schwa P75) による客観的な判定が行われます。
</div>""", unsafe_allow_html=True)

        if not is_custom_now and os.path.exists(active_bm["ref_audio"]):
            st.markdown("<div style='font-size: 0.9rem; font-weight: bold; color: #94A3B8; margin-top: 8px; margin-bottom: 4px;'>ネイティブお手本音声</div>", unsafe_allow_html=True)
            with open(active_bm["ref_audio"], "rb") as rf: st.audio(rf.read(), format="audio/wav")

    if st.session_state.e2_eval_history and st.session_state.e2_audio_bytes:
        latest_wb = st.session_state.e2_eval_history[-1].get("word_breakdown", [])
        trial_num = len(st.session_state.e2_eval_history)
        map_html = build_clickable_word_map_html(latest_wb, st.session_state.e2_audio_bytes, trial_num)
        components.html(map_html, height=155, scrolling=False)

# -------------------------------------------------------------
# L1 モード (Ninja Listening Trainer - YouTube)
# -------------------------------------------------------------
elif st.session_state.app_mode == "LISTENING":
    render_ninja_listening()