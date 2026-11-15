"""
constants.py: NinjaPhonetics の共通定数・辞書定義
"""
import numpy as np

# A1 プリセット一覧
PRESET_DIR = "presets"
PRESETS = [
    {
        "label": "Right (US)",
        "file": "right_us.wav",
        "target_word": "right",
        "title": "Right /raɪt/ (US)",
        "phonetics": "/r/ のくびれ (谷)",
        "desc": "語頭でF3が急降下してF2に接近し、差分ライン(Δ)が1000Hz破線より深く潜り込みます。舌の両側面を上顎の奥歯に密着させることでこの深い谷が生まれます。"
    },
    {
        "label": "Right (UK)",
        "file": "right_uk.wav",
        "target_word": "right",
        "title": "Right /raɪt/ (UK)",
        "phonetics": "/r/ の狭窄",
        "desc": "語頭でF3が急降下して1000Hz基準線を下回ります。その後の二重母音 /aɪ/ への移行部でF2が右肩上がりに上昇します。"
    },
    {
        "label": "Light (US)",
        "file": "light_us.wav",
        "target_word": "light",
        "title": "Light /laɪt/ (US)",
        "phonetics": "Dark L（軟口蓋化）による低F2・高Δ",
        "desc": "米語の語頭 /l/ は奥舌が引かれるため（Dark L傾向）、開始部で F2（緑）が 1200Hz 付近と低く、F3（青）との差分（Δ）が 2500Hz 以上に大きく開くのが特徴です。"
    },
    {
        "label": "Light (UK)",
        "file": "light_uk.wav",
        "target_word": "light",
        "title": "Light /laɪt/ (UK)",
        "phonetics": "F3高域維持 (Clear L)",
        "desc": "語頭の /l/ でF3は2700〜2800Hzの高域にとどまり、差分(Δ)は1000Hzを割らずに推移します。"
    },
    {
        "label": "White (UK)",
        "file": "white_uk.wav",
        "target_word": "white",
        "title": "White /waɪt/ (UK)",
        "phonetics": "円唇によるF2低下",
        "desc": "語頭で唇を丸めるためF2が一時的に下がりますが、F3は下がらないため、差分ラインはRのようなくびれになりません。"
    },
    {
        "label": "ライト (JP)",
        "file": "raito_jp.wav",
        "target_word": "raito",
        "title": "日本語「ライト」/ɾaɪto/",
        "phonetics": "タップ破裂と語尾母音付加",
        "desc": "「ラ」で瞬間的な弾き音（破裂）が起き、語尾には英語の /t/ にはない母音「オ」のホルマントが明瞭に残ります。"
    },
    {
        "label": "Really (US)",
        "file": "really_us.wav",
        "target_word": "really",
        "title": "Really /ˈrɪli/ ~ /ˈriːli/ (US)",
        "phonetics": "/r/ の深谷から /l/ の天井へのジャンプ",
        "desc": "語頭の /r/ で青（F3）が緑（F2）へ沈み込み、黄色（Δ）が 500Hz 前後まで深く潜ります。そこから後半の /l/ に向かって F3 が 3000Hz 超へ跳ね上がるコントラストが特徴です。"
    },
    {
        "label": "Really (UK)",
        "file": "really_uk.wav",
        "target_word": "really",
        "title": "Really /ˈrɪəli/ (UK)",
        "phonetics": "センタリング二重母音を経由する滑らかな渡り",
        "desc": "前半の /r/ でしっかり 1000Hz 破線を潜る谷を作った後、イギリス英語特有の曖昧母音 /ə/ を挟みながら、後半の /l/ に向かって滑らかに F3 が立ち上がります。"
    },
    {
        "label": "Very (US)",
        "file": "very_us.wav",
        "target_word": "very",
        "title": "Very /ˈveri/ (US)",
        "phonetics": "有声摩擦 /v/ の振動持続 ＋ r-colored母音のくびれ",
        "desc": "語頭は有声摩擦 /v/ の規則的な声帯振動が続き、破裂音（b）のようなスパイクがありません。続く母音〜/r/ で F3 が引きずり下ろされ、Δ が 500Hz 未満の深い谷を作ります。"
    },
    {
        "label": "Very (UK)",
        "file": "very_uk.wav",
        "target_word": "very",
        "phonetics": "/v/ から短母音を経て短く鋭い /r/ へ",
        "desc": "米語に比べて母音のR音性化が少なく、谷の幅（持続時間）がコンパクトで引き締まっています。"
    }
]

ARPABET_TO_IPA = {
    "AA": "ɑ", "AE": "æ", "AH0": "ə", "AH": "ʌ", "AO": "ɔ",
    "AW": "aʊ", "AY": "aɪ", "EH": "e", "ER": "ɚ", "EY": "eɪ",
    "IH": "ɪ", "IY": "i", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ", "UW": "u",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ",
    "HH": "h", "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n",
    "NG": "ŋ", "P": "p", "R": "r", "S": "s", "SH": "ʃ", "T": "t",
    "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ"
}

# B1 プリセット定義 (/si/ vs /ʃi/ 歯擦音スペクトル重心 COG)
B1_PRESET_DIR = "presets/b1"
B1_WORD_PRESETS = [
    {
        "label": "See (US)",
        "file": "see_us.wav",
        "target_word": "see",
        "expected_sib": "S",
        "title": "See /siː/ (US)",
        "phonetics": "高域歯茎摩擦 /s/ (COG ≥ 5,500 Hz)",
        "desc": "舌先を下前歯の裏に固定し、前歯の狭い隙間へ気流を集中させることで、スペクトル重心（COG）が 5,500〜7,500 Hz の緑色ストライクゾーンに高く維持されます。"
    },
    {
        "label": "See (UK)",
        "file": "see_uk.wav",
        "target_word": "see",
        "expected_sib": "S",
        "title": "See /siː/ (UK)",
        "phonetics": "RP 鋭利歯擦音 /s/ (COG ≥ 5,500 Hz)",
        "desc": "口角を横に引き、硬口蓋化（舌背の盛り上がり）を防いで鋭い高周波乱流を生成します。"
    },
    {
        "label": "She (US)",
        "file": "she_us.wav",
        "target_word": "she",
        "expected_sib": "SH",
        "title": "She /ʃiː/ (US)",
        "phonetics": "後部歯茎摩擦 /ʃ/ (COG 3,200〜4,600 Hz)",
        "desc": "舌端を歯茎の後ろへ引き、唇を軽く突き出すことで前口腔共鳴腔が広がり、COG が 3,200〜4,600 Hz の青色ゾーンへ低下します。"
    },
    {
        "label": "She (UK)",
        "file": "she_uk.wav",
        "target_word": "she",
        "expected_sib": "SH",
        "title": "She /ʃiː/ (UK)",
        "phonetics": "RP 後部歯茎摩擦 /ʃ/ (COG 3,200〜4,600 Hz)",
        "desc": "低い周波数帯に厚みのあるノイズエネルギーが集中し、/s/ との明確なコントラストを作ります。"
    },
    {
        "label": "Seat (US)",
        "file": "seat_us.wav",
        "target_word": "seat",
        "expected_sib": "S",
        "title": "Seat /siːt/ (US)",
        "phonetics": "閉音節 /s/ + 無声閉鎖 /t/",
        "desc": "後続の狭母音 /iː/ に引っ張られて舌の中央が盛り上がると「シート」化して COG が急落します。/s/ 区間全体で 5,500 Hz 以上をキープします。"
    },
    {
        "label": "Sheet (US)",
        "file": "sheet_us.wav",
        "target_word": "sheet",
        "expected_sib": "SH",
        "title": "Sheet /ʃiːt/ (US)",
        "phonetics": "閉音節 /ʃ/ + 無声閉鎖 /t/",
        "desc": "舌先を引いて唇を丸めることで /ʃ/ ゾーン（3,200〜4,600 Hz）に安定して収まります。"
    },
    {
        "label": "Sip (US)",
        "file": "sip_us.wav",
        "target_word": "sip",
        "expected_sib": "S",
        "title": "Sip /sɪp/ (US)",
        "phonetics": "高COG /s/ + 弛緩母音 /ɪ/",
        "desc": "英語の /ɪ/ は舌位置がやや低いため口蓋化が起きにくく、/s/ の鋭い高周波が保ちやすい基準語です。"
    },
    {
        "label": "Ship (US)",
        "file": "ship_us.wav",
        "target_word": "ship",
        "expected_sib": "SH",
        "title": "Ship /ʃɪp/ (US)",
        "phonetics": "低COG /ʃ/ + 弛緩母音 /ɪ/",
        "desc": "Sip とのミニマルペア比較。子音部の COG だけで 2,000 Hz 以上の落差が生じます。"
    },
    {
        "label": "City (US)",
        "file": "city_us.wav",
        "target_word": "city",
        "expected_sib": "S",
        "title": "City /ˈsɪti/ (US)",
        "phonetics": "高頻度トラップ語（shitty 混同回避）",
        "desc": "語頭の /s/ が口蓋化すると「シティー (shitty)」に聞こえる危険な単語です。語頭で確実に 5,500 Hz 以上へ打ち上げます。"
    },
    {
        "label": "シー (JP)",
        "file": "shii_jp.wav",
        "target_word": "shii",
        "expected_sib": "JP_TRAP",
        "title": "日本語「シー」[ɕiː] (口蓋化トラップ)",
        "phonetics": "歯茎硬口蓋音 [ɕ] (COG 3,500〜4,400 Hz)",
        "desc": "日本語のサ行「シ」は舌背が硬口蓋に近づく [ɕ] で発音されるため、See を狙っても She 側の 3,500〜4,400 Hz 帯に落ち込む典型的な干渉パターンです。"
    },
    {
        "label": "シート (JP)",
        "file": "shiito_jp.wav",
        "target_word": "shiito",
        "expected_sib": "JP_TRAP",
        "title": "日本語「シート」[ɕiːto]",
        "phonetics": "[ɕ] 口蓋化 ＋ 語尾母音 [o] 付加",
        "desc": "語頭が /s/ ではなく [ɕ] の低COG帯に入り、さらに語末に不要な母音「ト」が付加されています。"
    },
    {
        "label": "シップ (JP)",
        "file": "shippu_jp.wav",
        "target_word": "shippu",
        "expected_sib": "JP_TRAP",
        "title": "日本語「シップ」[ɕipːɯ]",
        "phonetics": "[ɕ] 口蓋化 ＋ 促音・語尾 [ɯ]",
        "desc": "Sip を狙う際も日本語の「シ」の構えのまま発音すると 4,000 Hz 前後のトラップゾーンに沈みます。"
    },
    {
        "label": "シティ (JP)",
        "file": "shitii_jp.wav",
        "target_word": "shitii",
        "expected_sib": "JP_TRAP",
        "title": "日本語「シティ」[ɕiti]",
        "phonetics": "[ɕ] 口蓋化トラップ",
        "desc": "語頭の [ɕ] が低COG帯（〜4,000 Hz）に落ち込むため、英語母語話者には shitty と知覚されやすくなります。"
    }
]

B1_PASSAGE_BENCHMARK = {
    "title": "早口言葉コアーティキュレーション検証: She sells seashells",
    "target_text": "She sells seashells by the seashore. The shells that she sells are seashells, I'm sure.",
    "ipa_guide": "/ʃiː sɛlz ˈsiːʃɛlz baɪ ðə ˈsiːʃɔːr | ðə ʃɛlz ðæt ʃiː sɛlz ɑːr ˈsiːʃɛlz aɪm ʃʊr/",
    "us_audio": "presets/b1/seashells_us.wav",
    "uk_audio": "presets/b1/seashells_uk.wav",
    "jp_audio": "presets/b1/seashells_jp.wav",
}

# E2 ベンチマーク定義（長文標準パッセージ専用）
E2_PASSAGE_BENCHMARKS = {
    "P1_northwind": {
        "category": "passage",
        "x_metric": "rcf",
        "title": "総合アセスメント 1: 北風と太陽 (The North Wind and the Sun 全文113語)",
        "target_text": "The North Wind and the Sun were disputing which was the stronger, when a traveler came along wrapped in a warm cloak. They agreed that the one who first succeeded in making the traveler take his cloak off should be considered stronger than the other. Then the North Wind blew with all his might, but the more he blew, the more closely did the traveler fold his cloak around him, and at last the North Wind gave up the attempt. Then the Sun shone out warmly, and immediately the traveler took off his cloak. And so the North Wind was obliged to confess that the Sun was the stronger of the two.",
        "phonetics_desc": "ポーズ非感受性の2D軸 (内容語/機能語母音比 R_CF × 弱母音持続時間 Schwa P75) により、客観的なストレス拍を評価します。",
        "mu": np.array([1.45, 52.26]),
        "cov": np.array([[0.0068, -0.165], [-0.165, 16.50]]),
        "x_range": (0.7, 1.85),
        "y_range": (35.0, 105.0),
        "ref_audio": "benchmarks/P1_northwind/UK-Native/UK-Native_01_Archer.wav",
        "bm_csv": "benchmarks/P1_northwind/northwind_benchmark_results.csv"
    }
}

DIAGNOSTIC_FUNCTION_WORDS = {
    "to", "for", "at", "of", "in", "from", "with", "into", "through", "about",
    "and", "that", "than", "but", "as", "if", "or", "so",
    "was", "were", "should", "could", "would", "can", "his", "him", "them", "us"
}

ALL_FUNCTION_WORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "from", "with", "by", "about", "as",
    "into", "like", "through", "after", "over", "between", "out", "against", "during", "without",
    "before", "under", "around", "among", "i", "you", "he", "she", "it", "we", "they", "me", "him",
    "her", "us", "them", "my", "your", "his", "its", "our", "their", "this", "that", "these",
    "those", "who", "whom", "whose", "which", "what", "where", "when", "why", "how", "am", "is",
    "are", "was", "were", "be", "been", "being", "have", "has", "had", "will", "would", "shall",
    "should", "can", "could", "may", "might", "must", "and", "but", "or", "so", "than", "off", "along"
}

VOWEL_SET = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}