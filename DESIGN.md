# VOX-Radio 設計書

## 概要

FMラジオ放送を受信 → 文字起こし → 要約(＋感情分析) → VOICEVOX音声合成 → VRMアバター表示 → ブラウザ

## アーキテクチャ

```
┌──────────────┐     ┌───────────────┐     ┌───────────────┐
│ JCBA FMラダ │────▶│ faster-whisper│────▶│   Ollama      │
│ RioAPI(Heart │  WS │ large-v3-turbo│  FF │ gemma4:e4b    │
│ FM) WebSocket│     │ (CUDA/float16)│     │ 要約+感情分析 │
└──────────────┘     └───────────────┘     └───────┬───────┘
       │                    │                       │
       ▼                    ▼                       ▼
┌──────────────┐     ┌───────────────┐     ┌───────────────┐
│   Raw Audio  │     │ Transcription │     │   Summary     │
│ .ogg/.wav    │     │ .json/.txt    │     │ +Sentiment    │
└──────────────┘     └───────────────┘     └───────┬───────┘
                                                    │
                         ┌───────────────┐          ▼
                         │   VOICEVOX    │     ┌───────────────┐
                         │   AudioQuery  │────▶│ AudioQuery    │
                         │   → WAV       │     │ JSON          │
                         └───────────────┘     └───────┬───────┘
                                                         │
                              ┌───────────────┐         ▼
                              │  VRM Blend    │◀──── AudioQuery
                              │  Shape Frames │         │
                              │  + Idle Anim  │   ┌──────▼───────┐
                              └───────────────┘   │  viz/        │
                                                   │  index.html  │
                                                   │  Three.js    │
                                                   │  + three-vrm │
                                                   │  + AudioVis  │
                                                   └───────────────┘
```

## 各工程の詳細

### 1. 受信 (src/radio/receiver.py)

- **API エンドポイント**: `POST https://radimo.smen.biz/api/v1/select_stream`
  - JSON body: `{"station": "heartfm"}`
  - query params: `channel=0`, `quality=high/dummy`, `burst=5`
  - 応答: `{ "location": "wss://<host>.radimo.smen.biz/socket", "token": "<jwt>" }`

- **WebSocket**: `wss://<host>.radimo.smen.biz:443/socket`
  - subprotocol: `listener.fmplapla.com`
  - ヘッダ: `Authorization: Bearer <token>`
  - 初回メッセージとして `token` を送信

- **コーデック**: Oggコンテナ内 Opus, 48kHzステレオ, ~12kbps
  - `quality=high/low`は実質ダミー（コーデックパラメータに違いなし）
  - `burst`は初期バッファ調整用

- **トークン管理**: JWTは発行から15秒で期限切れ → 10秒間隔で更新
- **デュアルストリーミング**: 2ストリーム交互切替で音声抜け防止
  - `RECORD_DURATION` (デフォルト60s): 1セッションの収録時間
  - `STREAM_SWITCH_OVERLAP` (デフォルト5s): 切り替え時の重複秒数

- 出力ファイル:
  - `output/raw/rec_{stream}_{uuid}.ogg` — 生Ogg/Opus
  - `output/raw/rec_{stream}_{uuid}.wav` — ffmpeg変換後WAV (16kHz モノラル PCM)
  - `output/raw/rec_{stream}_{uuid}_meta.json` — コーデック/サンプルレート情報

### 2. 文字起こし (src/transcription/transcriber.py)

- **モデル**: faster-whisper `large-v3-turbo` (CUDA float16)
- **言語**: 日本語 (`ja`)
- **初期プロンプト**: "日本語の会話。"
- **Overlapデdup**: 切り替え時に重複した先頭セグメントを除去
  - 直前の文字起こし末尾N語と一致する先頭から削除
- 出力ファイル:
  - `output/transcripts/trans_{batch_id}.json` — セグメント詳細（時刻付き）
  - `output/transcripts/trans_{batch_id}.txt` — テキストのみ

### 3. 要約・感情分析 (src/summarization/summarizer.py)

- **モデル**: Ollama `gemma4:e4b` @ http://ubuntu.local:11434
- **出力JSON形式**:
```json
{
  "summary": "500文字以内の要約",
  "sentiment": { "label": "positive/neutral/negative", "score": 0.0-1.0 },
  "emotions": { "joy": 0.0-1.0, "sadness": 0.0-1.0, "surprise": 0.0-1.0,
                "fear": 0.0-1.0, "anger": 0.0-1.0, "trust": 0.0-1.0,
                "anticipation": 0.0-1.0 },
  "keywords": ["キーワード1", "キーワード2"]
}
```
- **コンテキスト維持**: 直前の文字起こしを要約プロンプトに注入（rolling context）
- 出力ファイル:
  - `output/summaries/summ_{batch_id}.json`

### 4. 音声合成 (src/tts/vox_player.py)

- **API**: VOICEVOX ENGINE @ http://ubuntu.local:50021
- **フロー**: `text → audio_query → synthesis_hack → WAV`
- **AudioQuery生成時パラメータ**:
  - `speedScale`, `pitchScale`, `intonationScale`, `volumeScale`
- **初期化**: `/initialize_speaker?speaker={speaker_id}` (204)
- 出力ファイル:
  - `output/wav/synth_{uuid}.wav`

### 5. VRM視覚化 (src/vr_renderer/vrm_generator.py)

#### AudioQuery → VRM BlendShape マッピング

- **リップシンク (aiueo)**: AudioQueryのモーフィングターゲットをVRM presetに変換
  - `a`, `i`, `u`, `e`, `o` の5プリセット
  - AudioQueryの音素順にフェードイン/アウト
  - AudioQuery配列の各要素: `{ "name": "a", "weight": 0.0-1.0, "ms": start-end }`

- **表情**: 要約結果の感情スコアに基づき自動切替
  - `happy` (喜び) → VRM `happy` preset
  - `sad` (悲しみ) → VRM `sad` preset
  - `surprised` (驚き) → VRM `surprised` preset
  - `angry` (怒り) → VRM `angry` preset
  - `neutral` → VRM `neutral` preset

- **身振り**: `chest_breath`, `head_tilt`, `body_rotation`
  - 呼吸はAudioのRMSエネルギーに連動
  - 頭部傾斜は感情によって微調整

#### Idle Animation

- ランダムまばたき (3-7秒間隔)
- 体 sway (ランダムな傾斜角に6秒ごと更新)
- 緩い呼吸アニメーション (sin波で胸部起伏)

- 出力ファイル: `viz/vrma_frames.json`

### 6. VRMブラウザ表示 (viz/index.html)

- **Three.js 0.140.2** + **three-vrm 1.0.9**
- **VRMモデル**: `assets/vrms/hrn0Hk8kxp.glb` (デフォルト)
- **機能**:
  - WebGL 3Dビューア (OrbitControls対応)
  - リアルタイムリップシンク (vrma_frames.jsonからフェーズ同期)
  - 表情トランジション (スライダー制御)
  - 身振り制御 (breath/tilt滑らか)
  - パイプライン制御 (開始/停止)
  - 要約パネル表示
- **vrma_frames.json フォーマット**:
```json
[
  {
    "t": 1234567890.123,
    "lips": { "a": 1.0, "i": 0.0, "u": 0.0, "e": 0.0, "o": 0.0 },
    "expr": { "neutral": 1.0, "happy": 0.0 },
    "body": { "chest_breath": 0.02, "head_tilt": 0.0, "body_rotation": 0.0 },
    "idle": "none"
  }
]
```
- **音声同期**: バウンスバッファでvrma_framesを読み込み、lip syncをリアルタイム適用
- **音声可視化**: `viz/audio_visualizer.py` から波形/スペクトログラムの統計値を取得

## ファイル構成

```
vox-radio/
├── src/
│   ├── __init__.py
│   ├── config.py              # 環境変数・設定 (JCBA, Whisper, Ollama, VOICEVOX, VRM)
│   ├── main.py                # メインパイプライン (非同期)
│   ├── radio/
│   │   ├── __init__.py
│   │   └── receiver.py        # デュアルストリーム WebSocket 受信
│   ├── transcription/
│   │   ├── __init__.py
│   │   └── transcriber.py     # faster-whisper 文字起こし
│   ├── summarization/
│   │   ├── __init__.py
│   │   └── summarizer.py      # Ollama 要約+感情分析
│   ├── tts/
│   │   ├── __init__.py
│   │   └── vox_player.py      # VOICEVOX AudioQuery → WAV
│   ├── vr_renderer/
│   │   ├── __init__.py
│   │   └── vrm_generator.py   # VRM BlendShape + LipSync + Idle
│   └── output/
│       └── __init__.py
├── viz/
│   ├── index.html             # VRMブラウザビューア (Three.js+three-vrm)
│   └── audio_visualizer.py    # 波形/スペクトログラム統計
├── assets/
│   └── vrms/                  # VRM/GLBファイル
├── output/
│   ├── raw/                   # .ogg/.wav メタJSON
│   ├── transcripts/           # .json/.txt
│   ├── summaries/             # .json
│   ├── wav/                   # .wav
│   └── viz/                   # vrma_frames.json
├── config/
│   └── .env                   # 環境変数
├── logs/
│   └── pipeline.log
├── .env.example
├── .gitignore
├── DESIGN.md                  # このファイル
├── README.md
├── PROJECT.md
├── REPO_TREE.txt
├── pyproject.toml
└── requirements.txt
```

## インストール・セットアップ

```bash
cd vox-radio
uv sync
cp .env.example config/.env   # 必要に応じて編集
```

環境変数の主なもの:

| 変数 | デフォルト | 説明 |
|-----|---------|------|
| `HEARTFM_STATION_ID` | `heartfm` | 放送局ID |
| `WHISPER_MODEL` | `large-v3-turbo` | Whisperモデル |
| `WHISPER_DEVICE` | `cuda` | 推論デバイス |
| `OLLAMA_MODEL` | `gemma4:e4b` | 要約モデル |
| `OLLAMA_URL` | `http://ubuntu.local:11434` | Ollamaエンドポイント |
| `VOICEVOX_URL` | `http://ubuntu.local:50021` | VOICEVOXエンドポイント |
| `VOICEVOX_SPEAKER_ID` | `1` | デフォルトスピーカー |
| `RECORD_DURATION` | `60` | 1セッションの秒数 |
| `RADIO_MINUTES` | `0` | 0=無限ループ |

## 実行

```bash
# パイプライン実行 (無限ループ)
python -m src.main

# 指定時間だけ実行 (例: 10分)
RADIO_MINUTES=10 python -m src.main

# 単発実行 (1回だけ)
python -m src.main --once

# VRMブラウザ表示
cd viz
python -m http.server 8080
# → http://localhost:8080/index.html
```

## 全工程の生成物ファイル保存

| 工程 | ファイル形式 | 保存先 |
|-----|------------|--------|
| 生音频 | `.ogg`, `.wav`, `_meta.json` | `output/raw/` |
| 文字起こし | `.json` (セグメント), `.txt` | `output/transcripts/` |
| 要約+感情 | `.json` | `output/summaries/` |
| 音声合成 | `.wav` | `output/wav/` |
| VRM frames | `vrma_frames.json` | `viz/` |
| パイプラインログ | `.log` | `logs/` |
| バッチ記録 | `batch_{id}.json` | `output/` |

## 依存関係

- Python 3.10+
- faster-whisper (音声認識)
- ollama (LLM要約)
- torch (CUDA対応)
- websockets (JCBA API通信)
- requests (HTTP)
- ffmpeg (Ogg→WAV変換)
- three.js + three-vrm (ブラウザ3D表示)
