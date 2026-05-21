# VOX-Radio — 生放送 VRM パイプライン

## 概要

HeartFM（JCBA/FMラダリオ）のインターネット電波をリアルタイム受信 →
文字起こし → 要約＋感情分析 → VOICEVOX音声合成 → VRMアバターの
リップシンク・表情・身振り表現 → ブラウザ表示

「放送を聴く」だけでなく、「キャラクターが喋る」体験をブラウザで構築する。

## 全体フロー

```
┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│  HeartFM WS  │────▶│ faster-whisper│────▶│ Gemma4要約＋ │
│  Ogg/Opus    │     │ large-v3-turbo│     │ 感情分析      │
└──────────────┘     └──────────────┘     └───────┬───────┘
                                                   │
┌────── VRM表示 ──┐   ┌───────────────┐     ┌───────▼───────┐
│  ブラウザ/WebXR  │◀──│ VOICEVOX合成 │◀────│ AudioQuery    │
│  three-vrm       │   │ lip+bodymotion│     │ 生成          │
└─────────────────┘   └───────────────┘     └───────────────┘
         │
   file write (全工程生成物)
```

## サイクル（5秒バッチ）

```
[0s]   OGGPacket受信 → ffmpeg Ogg→WAV → faster-whisper
[1s]   文字起こし結果 → text → Ollama → 要約＋感情分析
[2s]   要約→AudioQuery → VOICEVOX → WAV
[3s]   AudioQuery→リップ→三木(身振り→three-vrm→ブラウザ→音声再生
[4s]   生成物ファイル保存
[5s]   次バッチへ
```

## 環境

- **Ollama**: http://ubuntu.local:11434 (Gemma4 e4b)
- **VOICEVOX**: http://ubuntu.local:50021 (音声合成エンジン)
- **faster-whisper**: large-v3-turbo (文字起こし)
- **three-vrm**: VRM3D表示

## 依存

- Python ≥3.10
- ffmpeg (libopus)
- Ollama
- VOICEVOX Engine
- Node.js (フロントエンドビルド)

## 技術的課題

1. **15秒JWT**: JCBA WebSocketのトークンは15秒で切れる。
   10秒間隔でのリフレッシュが必要。
2. **Ogg Opus→PCM→文字起こし**: ffmpegでPCMへの変換が必要。
3. **リアルタイム**: 5秒サイクルで回す必要がある。
4. **VRMリップ・身振り**: AudioQuery → 音素 → リップシェイプ → VRM BlendShape
   （身振りはテキスト解析から生成）
5. **同期**: 音声とVRMアニメの同期

## ファイル出力（output/ディレクトリ）

- `raw.ogg` — 受信RAW
- `raw.pcm` — PCM音声
- `transcription.json` — 文字起こし結果
- `summary.json` — 要約＋感情分析
- `audio_query.json` — VOICEVOXのAudioQuery
- `audio.wav` — 合成音声
- `vrm_bones.pkl` — VRMボーンデータ
- `vrm_blend_shapes.pkl` — VRM blend_shapes
- `vrm_emotions.json` — VRM表情アニメ
- `vrm_body_motion.json` — VRM身振り
- `logs/` — ログファイル
