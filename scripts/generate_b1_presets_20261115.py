"""
scripts/generate_b1_presets.py
B1 (/si/ vs /ʃi/ + 日本語カタカナ比較) プリセット音声一括生成＆COG検証スクリプト
"""
import os
import io
import json
import time
import dotenv
import requests
import numpy as np
import soundfile as sf
import parselmouth

dotenv.load_dotenv()
API_KEY = os.environ.get("ELEVENLABS_API_KEY")

OUT_DIR = os.path.join("presets", "b1")
os.makedirs(OUT_DIR, exist_ok=True)


def load_voice_ids():
    """benchmarks/voice_registry.json の 'uk' / 'us' / 'jp' リストから voice_id を取得"""
    reg_path = os.path.join("benchmarks", "voice_registry.json")
    with open(reg_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    # US[0]=Roger, UK[0]=Archer, JP[1]=Believe (Tokyo standard male)
    return {
        "US": registry["us"][0]["voice_id"],
        "UK": registry["uk"][0]["voice_id"],
        "JP": registry["jp"][1]["voice_id"],
    }


B1_TARGETS = [
    # US / UK ネイティブ基準
    {"file": "see_us.wav",    "text": "See.",   "cohort": "US", "lang": "en"},
    {"file": "see_uk.wav",    "text": "See.",   "cohort": "UK", "lang": "en"},
    {"file": "she_us.wav",    "text": "She.",   "cohort": "US", "lang": "en"},
    {"file": "she_uk.wav",    "text": "She.",   "cohort": "UK", "lang": "en"},
    {"file": "seat_us.wav",   "text": "Seat.",  "cohort": "US", "lang": "en"},
    {"file": "sheet_us.wav",  "text": "Sheet.", "cohort": "US", "lang": "en"},
    {"file": "sip_us.wav",    "text": "Sip.",   "cohort": "US", "lang": "en"},
    {"file": "ship_us.wav",   "text": "Ship.",  "cohort": "US", "lang": "en"},
    {"file": "city_us.wav",   "text": "City.",  "cohort": "US", "lang": "en"},
    # 日本語カタカナ比較（シー・シート・シップ・シティ）
    {"file": "shii_jp.wav",   "text": "シー",   "cohort": "JP", "lang": "ja"},
    {"file": "shiito_jp.wav", "text": "シート", "cohort": "JP", "lang": "ja"},
    {"file": "shippu_jp.wav", "text": "シップ", "cohort": "JP", "lang": "ja"},
    {"file": "shitii_jp.wav", "text": "シティ", "cohort": "JP", "lang": "ja"},
]


def synthesize_wav(text: str, voice_id: str, lang_code: str, out_path: str):
    if not API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY が .env から読み込めませんでした。")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "language_code": lang_code,
        "voice_settings": {
            "stability": 0.65,
            "similarity_boost": 0.80,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }
    params = {"output_format": "mp3_44100_128"}

    resp = requests.post(url, headers=headers, params=params, json=payload, timeout=30)
    resp.raise_for_status()

    try:
        data, sr = sf.read(io.BytesIO(resp.content), dtype="float32")
    except Exception:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(io.BytesIO(resp.content), format="mp3")
        sr = seg.frame_rate
        raw = np.array(seg.get_array_of_samples(), dtype=np.float32) / (1 << (seg.sample_width * 8 - 1))
        data = raw.reshape((-1, seg.channels)).mean(axis=1) if seg.channels > 1 else raw

    if data.ndim > 1:
        data = np.mean(data, axis=1)

    sf.write(out_path, data, sr, subtype="PCM_16", format="WAV")


def measure_initial_sibilant_cog(wav_path: str) -> float:
    """語頭の無声歯擦音区間を自動検出し、1kHzハイパス後のスペクトル重心(COG)を計測"""
    snd = parselmouth.Sound(wav_path)
    snd_hp = parselmouth.praat.call(snd, "Filter (pass Hann band)", 1000.0, 11000.0, 100.0)
    pitch = snd.to_pitch()
    intensity = snd_hp.to_intensity(minimum_pitch=100.0, time_step=0.005)

    times = intensity.xs()
    max_int = float(np.max(intensity.values))
    unvoiced_sib_times = []
    for t in times:
        f0 = pitch.get_value_at_time(t)
        inte = intensity.get_value(t)
        if (np.isnan(f0) or f0 <= 0) and inte >= (max_int - 22.0):
            unvoiced_sib_times.append(float(t))
        elif unvoiced_sib_times and not np.isnan(f0) and f0 > 0:
            break

    if len(unvoiced_sib_times) < 3:
        return 0.0

    t_start = unvoiced_sib_times[0]
    t_end = unvoiced_sib_times[-1]
    seg = snd_hp.extract_part(
        from_time=t_start,
        to_time=t_end,
        window_shape=parselmouth.WindowShape.HANNING,
    )
    spec = seg.to_spectrum(fast=True)
    cog = float(spec.get_centre_of_gravity(power=2.0))
    return round(cog, 1)


def main():
    voice_ids = load_voice_ids()
    print(f"Using Voice IDs: {voice_ids}\n")

    for item in B1_TARGETS:
        out_path = os.path.join(OUT_DIR, item["file"])
        vid = voice_ids[item["cohort"]]
        print(f"Generating {item['file']:16s} ('{item['text']}') ... ", end="", flush=True)
        if not os.path.exists(out_path):
            synthesize_wav(item["text"], vid, item["lang"], out_path)
            time.sleep(0.4)
        cog_hz = measure_initial_sibilant_cog(out_path)
        print(f"OK  | Initial Sibilant COG = {cog_hz:6.1f} Hz")
        time.sleep(0.4)

    print("\nAll 13 B1 presets generated in presets/b1/!")


if __name__ == "__main__":
    main()