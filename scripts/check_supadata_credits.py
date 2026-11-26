#!/usr/bin/env python3
"""
check_supadata_credits.py: .env から SUPADATA_API_KEY を読み込んで残クレジットを表示
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

# プロジェクトルートの .env を読み込み（scripts/ 配下から実行した場合も親ディレクトリを探索）
for env_candidate in [Path(".env"), Path(__file__).resolve().parent.parent / ".env"]:
    if env_candidate.exists():
        load_dotenv(env_candidate)
        break
else:
    load_dotenv()


def get_api_key() -> str:
    key = os.getenv("SUPADATA_API_KEY", "").strip()
    if key:
        return key

    # .env に無い場合は .streamlit/secrets.toml からも自動フォールバック
    for sec_candidate in [
        Path(".streamlit/secrets.toml"),
        Path(__file__).resolve().parent.parent / ".streamlit/secrets.toml",
    ]:
        if sec_candidate.exists():
            try:
                import tomllib
                data = tomllib.loads(sec_candidate.read_text(encoding="utf-8"))
                key = str(data.get("SUPADATA_API_KEY", "")).strip()
                if key:
                    return key
            except Exception:
                pass
    return ""


def main() -> None:
    api_key = get_api_key()
    if not api_key:
        print("❌ SUPADATA_API_KEY が見つかりません。.env に SUPADATA_API_KEY=sd_... を設定してください。", file=sys.stderr)
        sys.exit(1)

    req = urllib.request.Request(
        "https://api.supadata.ai/v1/me",
        headers={
            "x-api-key": api_key,
            "User-Agent": "NinjaPhonetics/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"❌ HTTP {e.code} Error: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    # レスポンス構造に応じた柔軟なフィールド抽出
    plan = data.get("plan") or data.get("tier") or "Unknown"
    limit = data.get("creditLimit") or data.get("creditsLimit") or data.get("limit")
    used = data.get("creditsUsed") or data.get("usedCredits") or data.get("used")
    remaining = data.get("creditsRemaining") or data.get("remainingCredits") or data.get("credits")

    if remaining is None and isinstance(limit, (int, float)) and isinstance(used, (int, float)):
        remaining = limit - used
    if used is None and isinstance(limit, (int, float)) and isinstance(remaining, (int, float)):
        used = limit - remaining

    reset_at = data.get("resetDate") or data.get("renewsAt") or data.get("periodEnd")

    print("=" * 48)
    print("  Supadata API Credit Status")
    print("=" * 48)
    print(f"  Plan         : {plan}")
    if isinstance(limit, (int, float)) and isinstance(remaining, (int, float)) and limit > 0:
        pct_rem = (remaining / limit) * 100
        bar_len = 24
        filled = max(0, min(bar_len, round((remaining / limit) * bar_len)))
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  Remaining    : {int(remaining):,} / {int(limit):,} credits ({pct_rem:.1f}%)")
        if isinstance(used, (int, float)):
            print(f"  Used         : {int(used):,} credits")
        print(f"  Gauge        : [{bar}]")
        print(f"  Est. Videos  : ~{int(remaining)} videos (with existing CC)")
    elif remaining is not None:
        print(f"  Remaining    : {remaining}")
    if reset_at:
        print(f"  Reset Date   : {reset_at}")
    print("-" * 48)
    print("  Raw JSON:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("=" * 48)


if __name__ == "__main__":
    main()