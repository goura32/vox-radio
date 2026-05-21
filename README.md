# VOX-Radio 🎙️🤖

FMラジオ → 文字起こし → 要約 → VOICEVOX音声合成 → VRMアバター表示パイプライン

## パイプラインフロー

```
HeartFM (JCBA FMラダリオ)
    │ WebSocket (Ogg/Opus 48kHz)
    ▼
リアルタイム受信 [DualStreamReceiver]
    │ Ogg → WAV (ffmpeg, 16kHz)
    ▼
faster-whisper [large-v3-turbo]
    │ 文字起こし (JSON/TXT)
    ▼
要約+感情分析 [Ollama gemma4:e4b]
    │要約 + 感情スコア + Keywords
    ▼
VOICEVOX ENGINE [AudioQuery → WAV]
    │ 音声合成
    ▼
VRMレンダラー [BlendShape + IdleAnim]
    │ LipSync + 表情 + 身振り
    ▼
ブラウザ表示 [Three.js + three-vrm]
```

## 機能一覧

- **ラジオ受信**: JCBA FMラダリオAPI経由でHeartFMをWebSocket受信
  - デュアルストリーミングで音声抜け防止
  - トークン自動更新 (15秒期限)
  - Ogg/Opus → WAV (16kHz モノラル) 変換

- **文字起こし**: faster-whisper large-v3-turbo
  - CUDA float16推論
  - オーバーラップ重複除去
  - スegment別保存 (.json + .txt)

- **要約・感情分析**: Ollama gemma4:e4b
  - JSON出力: 要約 + 感情スコア + 7感情要素 + キーワード
  - コンテキスト維持 (rolling window)

- **音声合成**: VOICEVOX ENGINE
  - AudioQuery生成 → 音声合成 → WAV出力
  - speaker/pitch/speed スケール調整

- **VRM視覚化**: リアルタイムリップシンク + 表情 + 身振り
  - AudioQueryからVRM BlendShapeへマッピング
  - Idleアニメーション (まばたき + sway + 呼吸)
  - 感情に基づく表情切替

- **ブラウザビューア**: Three.js + three-vrm
  - WebGL 3D VRM表示
  - リアルタイムリップシンク
  - 要約パネル表示
  - オーディオビジュアライザー

- **全工程の生成物をファイル保存**

## 依存関係

- Python 3.10+
- Ollama (gemma4:e4b) @ ubuntu.local:11434
- VOICEVOX ENGINE @ ubuntu.local:50021
- faster-whisper (CUDA対応推奨)
- ffmpeg (Ogg→WAV変換)
- three.js + three-vrm (ブラウザ表示)

## セットアップ

```bash
cd vox-radio
uv sync
cp .env.example config/.env   # 必要に応じて編集
```

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

## フォーマット

| 工程 | ファイル | 保存先 |
|-----|---------|--------|
| 生音频 | `.ogg`, `.wav`, `_meta.json` | `output/raw/` |
| 文字起こし | `.json`, `.txt` | `output/transcripts/` |
| 要約+感情 | `.json` | `output/summaries/` |
| 合成音声 | `.wav` | `output/wav/` |
| VRM frames | `vrma_frames.json` | `viz/` |
| バッチ記録 | `batch_{id}.json` | `output/` |
| パイプラインログ | `.log` | `logs/` |

## アーキテクチャ詳細

→ [DESIGN.md](DESIGN.md) を参照

## プロジェクト構造

→ [REPO_TREE.txt](REPO_TREE.txt) もしくは [PROJECT.md](PROJECT.md) を参照
