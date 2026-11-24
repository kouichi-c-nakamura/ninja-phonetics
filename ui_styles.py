"""
ui_styles.py: ブランドアイコン & 包括的ダークテーマCSS定義
"""
import base64
from pathlib import Path

_ICE_SHURIKEN_PATH = Path("assets/shuriken_ice.png")
_ICE_SHURIKEN_B64 = (
    base64.b64encode(_ICE_SHURIKEN_PATH.read_bytes()).decode("ascii")
    if _ICE_SHURIKEN_PATH.exists()
    else ""
)


def get_ice_shuriken_img_tag(size_px: int = 22, extra_class: str = "ninja-spin-hover") -> str:
    if _ICE_SHURIKEN_B64:
        return (
            f'<img src="data:image/png;base64,{_ICE_SHURIKEN_B64}" class="{extra_class}" '
            f'style="width:{size_px}px;height:{size_px}px;vertical-align:middle;'
            f'display:inline-block;flex-shrink:0;" />'
        )
    return (
        f'<svg class="{extra_class}" width="{size_px}" height="{size_px}" viewBox="0 0 64 64" '
        f'style="filter: drop-shadow(0 0 5px rgba(186, 230, 253, 0.5)); vertical-align: middle; flex-shrink: 0;">'
        f'<defs><linearGradient id="iceBlade" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="#F8FAFC"/><stop offset="55%" stop-color="#BAE6FD"/><stop offset="100%" stop-color="#38BDF8"/>'
        f'</linearGradient></defs>'
        f'<path d="M32 2 C36 18 46 24 62 32 C46 36 40 46 32 62 C28 46 18 40 2 32 C18 28 24 18 32 2 Z" fill="url(#iceBlade)" stroke="#E0F2FE" stroke-width="1.5"/>'
        f'<circle cx="32" cy="32" r="7" fill="#090D16" stroke="#BAE6FD" stroke-width="2"/>'
        f'</svg>'
    )


SHURIKEN_ICON_MAIN = get_ice_shuriken_img_tag(28, "ninja-spin-hover")
SHURIKEN_ICON_SM = get_ice_shuriken_img_tag(18, "ninja-spin-hover")

_ACTIVE_BTN_ICON_RULE = (
    f'background-image: url("data:image/png;base64,{_ICE_SHURIKEN_B64}");'
    f'background-size: contain;'
    f'background-repeat: no-repeat;'
    f'background-position: center;'
    if _ICE_SHURIKEN_B64
    else (
        'background-color: #BAE6FD;'
        '-webkit-mask-image: url(\'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill-rule="evenodd" d="M50 0 C50 30 70 50 100 50 C70 50 50 70 50 100 C50 70 30 50 0 50 C30 50 50 30 50 0 Z M50 42 A8 8 0 1 0 50 58 A8 8 0 1 0 50 42 Z"/></svg>\');'
        'mask-image: url(\'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill-rule="evenodd" d="M50 0 C50 30 70 50 100 50 C70 50 50 70 50 100 C50 70 30 50 0 50 C30 50 50 30 50 0 Z M50 42 A8 8 0 1 0 50 58 A8 8 0 1 0 50 42 Z"/></svg>\');'
        '-webkit-mask-size: contain; mask-size: contain;'
        '-webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;'
        '-webkit-mask-position: center; mask-position: center;'
    )
)

APP_CUSTOM_CSS = f"""<style>
:root {{
    --ice-white: #F0F9FF;
    --ice-cyan: #BAE6FD;
    --accent-blue: #38BDF8;
    --bg-dark: #090D16;
    --bg-card: #0F172A;
    --border-muted: #1E293B;
}}
html, body, [data-testid="stAppViewContainer"], .stApp {{
    background-color: #090D16 !important;
    color: #F8FAFC !important;
}}
header[data-testid="stHeader"] {{
    height: 1.8rem !important;
    background: transparent !important;
}}
.block-container {{
    padding-top: 1.2rem !important;
    padding-bottom: 0.8rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
}}
.brand-bar {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 0 10px 0;
    margin-bottom: 8px;
    border-bottom: 1px solid #1E293B;
}}
.brand-title {{
    font-size: 1.4rem;
    font-weight: 800;
    color: #F8FAFC;
    letter-spacing: -0.02em;
    margin: 0;
}}
.brand-sub {{
    font-size: 0.72rem;
    font-weight: 700;
    color: #BAE6FD;
    background: rgba(56, 189, 248, 0.12);
    border: 1px solid rgba(186, 230, 253, 0.35);
    padding: 2px 8px;
    border-radius: 4px;
    letter-spacing: 0.05em;
}}
.stButton button {{
    background-color: #0F172A !important;
    color: #94A3B8 !important;
    border: 1px solid #1E293B !important;
    border-bottom: 2px solid #1E293B !important;
    font-weight: 600 !important;
    padding: 6px 10px !important;
    border-radius: 6px 6px 2px 2px !important;
    font-size: 0.86rem !important;
    transition: all 0.15s ease !important;
}}
.stButton button:hover {{
    background-color: #1E293B !important;
    color: #F0F9FF !important;
    border-color: #334155 !important;
}}
.stButton button[kind="primary"],
.stButton button[data-testid="baseButton-primary"],
.stButton button[data-testid="stBaseButton-primary"] {{
    background-color: #172554 !important;
    color: #F0F9FF !important;
    border-color: #1E3A8A !important;
    border-bottom: 2.5px solid #BAE6FD !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 8px rgba(56, 189, 248, 0.15) !important;
}}

/* アクティブボタンの文字列 (<p>) の直前にだけ青白い手裏剣を1つ表示 */
div.stButton > button[kind="primary"] p,
div.stButton > button[data-testid="baseButton-primary"] p,
div.stButton > button[data-testid="stBaseButton-primary"] p {{
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 7px !important;
}}
div.stButton > button[kind="primary"] p::before,
div.stButton > button[data-testid="baseButton-primary"] p::before,
div.stButton > button[data-testid="stBaseButton-primary"] p::before {{
    content: "";
    display: inline-block;
    width: 18px;
    height: 18px;
    flex-shrink: 0;
    {_ACTIVE_BTN_ICON_RULE}
}}

/* ホバー時に手裏剣をクルクル回転 */
div.stButton > button[kind="primary"]:hover p::before,
div.stButton > button[data-testid="baseButton-primary"]:hover p::before,
div.stButton > button[data-testid="stBaseButton-primary"]:hover p::before {{
    animation: ninja-shuriken-spin 0.85s linear infinite;
}}

div[data-testid="stAudioInput"] {{
    background: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 8px;
    padding: 4px 12px;
    margin-bottom: 0.4rem;
}}
div[data-testid="stFileUploader"] {{
    background: #0F172A !important;
    border: 1px dashed #334155 !important;
    border-radius: 8px !important;
    padding: 6px !important;
    margin-bottom: 0.4rem !important;
}}
div[data-testid="stTextArea"] textarea {{
    background-color: #090D16 !important;
    color: #F8FAFC !important;
    border: 1px solid #1E293B !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    border-radius: 6px !important;
    line-height: 1.5 !important;
}}
.sec-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.92rem;
    font-weight: 700;
    color: #F0F9FF;
    margin-bottom: 8px;
}}

@keyframes ninja-shuriken-spin {{
    from {{ transform: rotate(0deg); }}
    to   {{ transform: rotate(360deg); }}
}}

/* ブランドバーや見出し内の手裏剣もホバーで回転 */
.ninja-spin-hover {{
    transition: transform 0.2s ease;
}}
.brand-bar:hover .ninja-spin-hover,
.sec-header:hover .ninja-spin-hover,
.ninja-spin-hover:hover {{
    animation: ninja-shuriken-spin 0.85s linear infinite;
}}

.ninja-spin-always {{
    animation: ninja-shuriken-spin 2.4s linear infinite;
}}
</style>"""