# VOX-Radio — FM ラジオ → VRM アバターパイプライン 📻

JCBA FMラダリオのインターネット電波をリアルタイム受信 → 文字起こし → 要約＋感情分析 → VOICEVOX音声合成 → VRMアバターのリップシンク・表情・身振り表現 → ブラウザ表示

「放送を聴く」だけでなく、「キャラクターが喋る」体験をブラウザで構築する。

## エコシステム

```
┌─ HeartFM WS ──▶ ── faster-whisper ──▶ ── Gemma4要約 ──▶ ── VOICEVOX ──▶ ── VRMブラウザ ──┐
│        Ogg/Opus          large-v3-turbo        Gemma4e4b         AudioQuery          three-vrm      │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 機能

| 機能 | 説明 |
|------|------|
| **リアルタイム受信** | JCBA FMラダリオのDual-stream WSからOgg/Opusを取得 |
| **オプス→WAV** | ffmpegで16kHz mono PCMに変換 |
| **文字起こし** | faster-whisper large-v3-turbo (CUDA float16)＋重複削除 |
| **要約・感情分析** | Ollama/Gemma4で500文字以内要約＋感情スコア |
| **音声合成** | VOICEVOX ENGINEのAudioQuery→WAV |
| **VRM表示** | Three.js+three-vrmブラウザ3Dビューア（リップ・表情・身振り） |
| **全工程生成物保存** | raw, WAV, 文字起こしJSON, 要約JSON, TTS WAV, vrma_frames |

## 前提条件

- **Python 3.11-3.12**
- **ffmpeg**（libopus対応）
- **Ollama** — http://localhost:11434 で稼働中、`gemma4:e4b` モデルをpull済み
- **VOICEVOX ENGINE** — http://localhost:50021 で稼働中
- **faster-whisper** — CUDA対応torch推奨（CUDA未対応ならcpuでも動くが遅い）
- VRM GLBファイル — `assets/vrms/` に設置

## インストール

```bash
# 1. フォルダ準備
cd /path/to/vox-radio

# 2. 仮想環境作成（uv推奨）
uv sync

# 3. 設定ファイル
cp .env.example .env
# .env の OLLAMA_URL, VOICEVOX_URL を実際のアドレスに書き換え

# 4. VRMモデル設置
mkdir -p assets/vrms
# VRM GLBファイル を assets/vrms/ に配置（例: hrn0Hk8kxp.glb）
```

## 使い方

### パイプライン実行（標準）

```bash
# 無限ループ
uv run python -m src.main

# 10分だけ実行
RADIO_MINUTES=10 uv run python -m src.main

# 1回だけ
uv run python -m src.main --once
```

### VRMブラウザビューア

```bash
cd viz
uv run python -m http.server 8080
# → http://localhost:8080/index.html をブラウザで開く
```

### 文字起こしのみテスト

```bash
uv run python -c "
from src.transcription.transcriber import Transcriber
t = Transcriber()
from src.config import WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
t = Transcriber(model_size=WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
result = t.transcribe_file('path/to/audio.wav')
print(result.raw_transcript)
"
```

### VOICEVOX TTSテスト

```bash
uv run python -c "
from src.tts.vox_player import VoxSynthesizer
v = VoxSynthesizer()
wav = v.save_synthesis('こんにちは、VOX-Radioです！')
print('Wav saved:', wav)
"
```

### 要約テスト

```bash
uv run python -c "
from src.summarization.summarizer import Summarizer
s = Summarizer('gemma4:e4b')
result = s.summarize('テストの文字起こしテキストです。')
print(result.summary)
"
```

## 全工程の生成物ファイル

| 工程 | ファイル形式 | 保存先 |
|------|-------------|--------|
| 生音频 | `.ogg`, `.wav`, `_meta.json` | `output/raw/` |
| 文字起こし | `.json`（セグメント）, `.txt` | `output/transcripts/` |
| 要約＋感情 | `.json` | `output/summaries/` |
| 音声合成 | `.wav` | `output/wav/` |
| VRM frames | `vrma_frames.json` | `viz/` |
| パイプラインログ | `.log` | `logs/` |
| バッチ記録 | `batch_{id}.json` | `output/` |

## 設定項目

| 環境変数 | 既定 | 説明 |
|----------|------|------|
| `HEARTFM_STATION_ID` | `heartfm` | 放送局ID |
| `WHISPER_MODEL` | `large-v3-turbo` | Whisperモデル |
| `WHISPER_DEVICE` | `cuda` | 推論デバイス |
| `WHISPER_COMPUTE_TYPE` | `float16` | 演算精度 |
| `OLLAMA_MODEL` | `gemma4:e4b` | 要約モデル |
| `VOICEVOX_SPEAKER_ID` | `1` | デフォルトスピーカー |
| `RECORD_DURATION` | `60` | 1セッションの秒数 |
| `STREAM_SWITCH_OVERLAP` | `5` | スイッチ重複秒数 |
| `RADIO_MINUTES` | `0` | `0`=無限ループ |
| `RADIO_BATCH_SECONDS` | `10` | バッチ取得間隔 |
| `PIPELINE_LOOP` | `true` | ループ実行 |
| `EMOTION_ANALYSIS` | `true` | 感情分析ON/OFF |
| `USE_CONTEXT` | `true` | 継続要約ON/OFF |
| `VOICEVOX_SPEED` | `1.0` | 話速 |
| `VOICEVOX_PITCH` | `0.0` | 音高 |
| `VOICEVOX_VOLUME` | `1.0` | 音量 |
| `VOICEVOX_INTONATION` | `1.0` | 抑揚 |

## VRMブラウザビューア

`viz/index.html` — Three.js + three-vrm の3Dビューア:

- **OrbitControls** — マウスで3D回転
- **リップシンク** — AudioQuery音素→BlendShape同期
- **表情切替** — happy/sad/angry/neutral等（感情スコア自動）
- **身振り** — 呼吸・頭部傾斜スライダー制御
- **要約パネル** — 最新の要約結果＋感情バー表示
- **パイプライン制御** — 開始/停止ボタン

## アーキテクチャ

### 受信 (src/radio/receiver.py)
- **dual-stream**: 2つのWS交互切替で音声の抜けを防ぐ
- JWT 15秒期限 → 10秒毎にリフレッシュ
- Ogg/Opus payload → ffmpeg で 16kHz PCM WAV に変換

### 文字起こし (src/transcription/transcriber.py)
- faster-whisper `large-v3-turbo`（CUDA float16推奨）
- Overlap dedup（切り替え重複箇所を除去）
- rolling context（過去5バッチを要約に注入）

### 要約・感情 (src/summarization/summarizer.py)
- Ollama/Gemma4でJSON出力（summary + sentiment + emotions + keywords）
- `_fallback`: Ollama未接続時は簡易フォールバック

### TTS (src/tts/vox_player.py)
- VOICEVOX API: audio_query → synthesis_hack → WAV
- パラメータ: speed, pitch, volume, intonation

### VRM (src/vr_renderer/vrm_generator.py)
- Lip sync: phoneme → BlendShape
- Expression: emotion → VRM preset
- Idle: random blink + body sway + breathing

### ビジュアライザー (viz/audio_visualizer.py)
- WAVファイルからRMSエネルギー、スペクトル分析
- `viz/index.html` で表示

## サポート

### トラブルシューティング

- **JCBA FMラダリオのWebSocketが切れる**: JWT期限（15秒）問題。`_refresh_loop` が10秒毎に自動更新。外部から直接APIを叩くとタイムアウトする場合、プロキシ/ファイアウォールの確認
- **Ollama未接続**: Summarizerが `_fallback` モードに自動切り替え
- **VOICEVOXエラー**: `/initialize_speaker?speaker={id}` で204が返ることを確認
- **CUDA unavailable**: `WHISPER_DEVICE=cpu` に設定（推論時間は数十倍）
- **VRMモデルが見つからない**: `assets/vrms/` が空 → VRM GLBファイルをダウンロードして設置

### VRMモデルの入手

- **VRoid Hub** — https://hub.vroid.com/
- **VRMモデルライブラリ** — モデルデータを `.glb` または `.vrm` で入手し、`assets/vrms/` に置く

## 依存関係

```
requests          — HTTPクライアント
websockets        — JCBA FMラダリオWS接続
ffmpeg-python     — Ogg→WAV変換（ffmpeg必須）
faster-whisper    — 文字起こし
ollama            — Gemma4要約
torch             — Whisper GPU推論
numpy / scipy     — VRM計算
```

## ライセンス

MIT

## 将来の拡張

- [ ] 他JCBA局のサポート（142局以上）
- [ ] VRM身振りの高度化（WebXR対応）
- [ ] 音声可視化のリアルタイム表示
- [ ] Telegram/LINE連携でストリーム配信
- [ ] ストレージのアーカイブ化（S3へアップロード）
