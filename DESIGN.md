# VOX-Radio 設計書

## 概要

FMラジオ放送を受信 → 文字起こし → 要約 → VOICEVOX音声合成 → VRMアバター表示

## アーキテクチャ

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  JCBA API    │     │ fater-whisper│     │   Ollama     │
│ (HeartFM)    │────▶│ large-v3-    │────▶│ gemma4:e4b   │
│ WebSocket    │     │ turbo        │     │              │
└──────────────┘     └──────────────┘     └──────────┬───┘
         │                │                          │
         ▼                ▼                          ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Raw Audio  │     │ Transcription│     │   Summary    │
│ (.wav/.ogg)  │     │  (.json/.txt)│     │ (+Sentiment) │
└──────────────┘     └──────────────┘     └──────────────┘
                                                    │
                    ┌──────────────┐                ▼
                    │   VOICEVOX   │         ┌──────────────┐
                    │   Synthesis  │         │ AudioQuery   │
                    └──────────────┘         └──────────────┘
                                                │
                    ┌──────────────┐           ▼
                    │    VRM       │     ┌──────────────┐
                    │ Blend Shapes│────▶│  VRM Visual  │
                    └──────────────┘     └──────────────┘
                                                │
                                         ┌──────────────┐
                                         │  Browser     │
                                         │  (Three.js   │
                                         │   VRM.js)   │
                                         └──────────────┘
```

## 工程詳細

### 1. 受信 (src/radio/receiver.py)

- JCBA FMラダリオAPIからJWTトークンを取得
- WebSocket接続 (subprotocol: listener.fmplapla.com)
- Ogg/Opusオーディオストリームを受信
- 毎10秒ごとにトークン更新
- 生データをoutput/raw/に保存 (.ogg + .wav)

### 2. 文字起こし (src/transcription/transcriber.py)

- faster-whisper large-v3-turboモデル使用
- CUDA推論 (float16)
- 日本語特化の初期プロンプト
- 出力: output/transcripts/trans_{batch_id}.json + .txt

### 3. 要約・感情分析 (src/summarization/summarizer.py)

- Ollama via gemma4:e4b
- JSON出力: 要約 + 感情 (positive/neutral/negative) + 感情スコア + キーワード
- フォールバック: キーワードベース感情分析
- 出力: output/summaries/summ_{batch_id}.json

### 4. 音声合成 (src/tts/vox_player.py)

- VOICEVOX ENGINE API via HTTP
- Text → AudioQuery → WAV
- デフォルトスピーカーID: 1
- 出力: output/wav/synth_{speaker_id}_{id}.wav

### 5. VRMレンダリング (src/vr_renderer/vrm_generator.py)

- AudioQuery → VRM BlendShape
- リップシンク: 母音(a,i,u,e,o) → VRM preset
- 表情: happy/sad/angry/surprised/funny/neutral
- 身振り: 呼吸、頭部傾斜、体回転
- 出力: viz/vrma_frames.json

### 6. VRMブラウザ表示 (viz/index.html)

- Three.js + three-vrm
- WebGL 3Dビューア
- リアルタイムリップシンク
- 表情トランジション
- 身振り制御

## ファイル構成

```
vox-radio/
├── src/
│   ├── config.py              # 設定
│   ├── main.py                # メインエントリ
│   ├── radio/
│   │   └── receiver.py        # 受信モジュール
│   ├── transcription/
│   │   └── transcriber.py     # 文字起こし
│   ├── summarization/
│   │   └── summarizer.py      # 要約・感情
│   ├── tts/
│   │   └── vox_player.py      # VOICEVOX合成
│   └── vr_renderer/
│       └── vrm_generator.py   # VRM表情・身振り
├── viz/
│   ├── index.html             # VRMブラウザ表示
│   └── audio_visualizer.py    # 音声可視化
├── output/
│   ├── raw/                   # 生音频 (.ogg, .wav)
│   ├── transcripts/           # 文字起こし結果
│   ├── summaries/             # 要約結果
│   ├── wav/                   # 合成音声
│   └── viz/                   # VRMデータ
├── .env.example               # 環境変数_template
├── .gitignore
├── DESIGN.md                  # このファイル
├── README.md
└── pyproject.toml
```

## インストール

```bash
cd vox-radio
uv sync
cp .env.example .env   # 必要に応じて編集
```

## 実行

```bash
# 連続ループ実行
python -m src.main

# 単発実行
python -m src.main --once

# VRMブラウザ表示
cd viz
python -m http.server 8080
# http://localhost:8080/index.html
```

## 依存関係

- Python 3.10+
- faster-whisper (whisper推論)
- ollama (LLM)
- torch (CUDA対応)
- wepsockets (JCBA API通信)
- requests (HTTP)
- three.js + three-vrm (ブラウザ3D)
