# VOX-Radio 🎙️

FMラジオ → 文字起こし → 要約 → VOICEVOX → VRMアバター表示パイプライン

## 概要

HeartFMなどのFMラジオ放送をリアルタイムで受信し、AIによる文字起こし・要約・感情分析を行い、VOICEVOXで音声合成、3Dアバター(VRM)で表現するパイプライン

## 機能

- **ラジオ受信**: JCBA FMラダリオAPI経由でHeartFMをWebSocket受信
- **文字起こし**: faster-whisper large-v3-turboで高精度音声認識
- **要約+感情分析**: Ollama (gemma4:e4b)でテキスト要約、感情スコア、キーワード抽出
- **音声合成**: VOICEVOX ENGINEで要約テキストを読み上げ
- **VRM視覚化**: リップシンク・表情・身振りを持つ3Dアバター表示
- **全工程ファイル保存**: raw audio, transcript, summary, synth audio, vrma frames

## 依存関係

- Python 3.10+
- Ollama (gemma4:e4b)
- VOICEVOX ENGINE
- faster-whisper (CUDA対応推奨)
- ffmpeg
- three.js + three-vrm (ブラウザ表示)

## セットアップ

```bash
cd vox-radio
uv sync
cp .env.example .env
# .env を必要に応じて編集
```

## 実行

```bash
# パイプライン実行 (5分ループ)
python -m src.main

# 単発実行
python -m src.main --once

# VRMブラウザ表示
cd vis
python -m http.server 8080
```

## フォーマット

- 生音频: `output/raw/batch_{timestamp}.ogg/.wav`
- 文字起こし: `output/transcripts/trans_{batch_id}.json/.txt`
- 要約: `output/summaries/summ_{batch_id}.json`
- 合成音声: `output/wav/synth_{speaker_id}_{id}.wav`
- VRM frames: `output/viz/vrma_frames.json`

## アーキテクチャ

DESIGN.md 参照
