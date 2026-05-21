# VOX-Radio — Real-time Radio → VRM Avatar Pipeline

https://github.com/goura32/vox-radio

JCBA/FM ラダリオから HeartFM をリアルタイム受信 → 文字起こし → 要約+感情分析 → VOICEVOX 音声合成 → VRM アバターのリップシンク・表情・身振りをブラウザで表示するパイプライン。

## Features

- 🎙️ **HeartFM 受信** - JCBA WebSocket 経由で Ogg/Opus ストリームを受信
- 🤖 **文字起こし** - faster-whisper large-v3-turbo で高精度文字起こし
- 🧠 **要約＋感情** - Gemma4(e4b) による要約＋感情分析＋区間検出
- 🗣️ **音声合成** - VOICEVOX による自然な音声への変換
- 🎭 **VRM アバター** - リップシンク＋表情＋身振り表現
- 💻 **ブラウザ表示** - three-vrm で VRM モデルをブラウザ上にリアルタイム表示

## Architecture

```
[HeartFM WS]→[Ogg/Opus]→[faster-whisper]→[transcription.json]
                                              ↓
[VRM Browser]←[three-vrm]←[AudioQuery]←[VOICEVOX]←[summary.json]+[emotion.json]
     ↓                                              ↑
[fallback_text]  [Gemma4 Summary]←[Ollama:11434]
```

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Run

```bash
python src/app.py
```

## Directory Structure

```
vox-radio/
├── src/                    # Core application code
│   ├── radio/             # HeartFM receiver (WebSocket, Ogg/Opus)
│   ├── transcription/     # faster-whisper wrapper
│   ├── summarization/     # Gemma4 summary+emotion
│   ├── tts/               # VOICEVOX AudioQuery client
│   ├── vr_renderer/       # VRM browser display
│   ├── output/            # File save utilities
│   └── app.py             # Main orchestrator
├── frontend/               # Browser VRM viewer
│   ├── index.html
│   ├── main.js
│   └── package.json
├── config/                 # Configuration files
├── tests/                  # Test suite
├── utils/                  # Utilities
├── outputs/                # Generated output files
├── DESIGN_DOC.md           # Detailed design document
└── PROJECT.md              # Project overview
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Stream Receiver | python-websockets, ffmpeg |
| Transcription | faster-whisper (large-v3-turbo) |
| Summarization | Ollama API (Gemma4:e4b) |
| TTS | VOICEVOX Engine API |
| VRM Display | three.js + three-vrm + WebXR |
| Language | Python 3.11+, TypeScript |

## Development

```bash
# Run tests
pytest tests/

# Type check
mypy src/
```

## License

MIT
