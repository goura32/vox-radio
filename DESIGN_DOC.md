# VOX-Radio データ設計書 v1.0

## 1. 用語定義

| 用語 | 説明 |
|------|------|
| AudioFrame | Ogg/Opus 1フレーム(20ms@48kHz)、800バイト (stereo/8bit/12kbps) |
| AudioFrameSet | 5秒分のフレーム群、150 frames |
| TranscriptionBatch | faster-whisper 1バッチの結果 |
| SummaryResult | Gemma4の出力(要約,感情,キーワード) |
| AudioQuery | VOICEVOXの音声合成パラメータ |
| SynthesisResult | VOICEVOXによる音声WAVファイル |
| VMParam | VRM Animationパラメータ(リップ,表情,身振り) |
| VRMFrame | 1/60秒分のVRMモデル状態 |

## 2. データモデル

### 2.1 HeartFM Stream Frame

```json
{
  "frame_id": "string (UUID)",
  "timestamp": "ISO 8601",
  "raw_data": "base64",
  "ogg_packet_type": "int (OpusHead/OpusTags/payload)",
  "opus_tags": "dict | null",
  "stream_serial": "int"
}
```

### 2.2 Transcription Result

```json
{
  "batch_id": "string (UUID)",
  "timestamp": "ISO 8601",
  "segments": [
    {
      "start": "float (秒)",
      "end": "float (秒)",
      "text": "string",
      "confidence": "float",
      "speaker": "string | null"
    }
  ],
  "raw_transcript": "string",
  "language": "string (ja, en, ...)",
  "silence_ratio": "float (0～1)"
}
```

### 2.3 Summary Result (Gemma4 出力)

```json
{
  "model": "string (gemma4:e4b)",
  "timestamp": "ISO 8601",
  "summary": "string",                          // 500字以内要約
  "sentiment": {                                 // 感情分析
    "label": "string (positive/neutral/negative)",
    "score": "float (0～1)",
    "emotions": {
      "joy": "float",
      "sadness": "float",
      "surprise": "float",
      "fear": "float",
      "anger": "float",
      "curiosity": "float"
    }
  },
  "keywords": ["string"],                        // キーワード抽出
  "speaker_intent": {                            // 話者意図推定
    "type": "string (explain/emerge/promise/express)",
    "tone": "string"
  },
  "broadcast_segment": {                         // 放送区間検出
    "section": "string (コーナー名/内容)",
    "description": "string",
    "is_anthropomorphic": "bool"               // ヒューマニズム的表現か
  }
}
```

### 2.4 VRM Animation Parameters

```json
{
  "animation_id": "string (UUID)",
  "timestamp": "ISO 8601",
  "source_audio": {                              // 元音声情報
    "duration_sec": "float",
    "sample_rate": "int",
    "channels": "int"
  },
  "phrases": [                                   // 音素分解
    {
      "phoneme": "string",
      "duration_ms": "float",
      "volume": "float (0～1)",
      "lip_shape": {                             // リップシェイプ
        "a": "float (0～1)",
        "i": "float (0～1)",
        "u": "float (0～1)",
        "e": "float (0～1)",
        "o": "float (0～1)",
        "sil": "float (0～1)"
      }
    }
  ],
  "expressions": [                               // 表情
    {
      "name": "string (happy/sad/surprised/angry/neutral/blink/wink)",
      "weight": "float (0～1)",
      "duration_sec": "float",
      "trigger": "string (emotion/silence/emphasis)"
    }
  ],
  "body_motion": [                               // 身振り
    {
      "type": "string (nod/head_tilt/arm_wave/dance/lean/hand_gesture)",
      "weight": "float (0～1)",
      "duration_sec": "float",
      "body_parts": ["string"],                  // affected bones
      "trigger": "string (emotion/emphasis/emergence)"
    }
  ]
}
```

## 3. 転送プロトコル

### 3.1 WebSocket (JCBA/FMラダリオ)

- **URL**: `wss://{cdn-node}/socket` (select_stream APIで取得)
- **Subprotocol**: `listener.fmplapla.com`
- **認証**: ヘッダー `Authorization: Bearer <JWT>`
- **payload**: `Ogg/Opus` バイナリ
- **トークン期限**: 15秒 (10秒毎にリフレッシュ必要)

### 3.2 faster-whisper 入力

- **input**: PCM WAV (16-bit, 16kHz, mono)
- **出力**: transcription JSON
- **推論モデル**: openai/whisper-large-v3-turbo (CTranslate2)

### 3.3 Ollama (Gemma4)

- **URL**: `http://ubuntu.local:11434/v1/chat/completions`
- **model**: `gemma4:e4b`
- **body**:
```json
{
  "model": "gemma4:e4b",
  "messages": [
    {"role": "system", "content": "..." },
    {"role": "user", "content": "..." }
  ],
  "temperature": 0.2,
  "format": "json"
}
```

### 3.4 VOICEVOX

- **URL**: `http://ubuntu.local:50021`
- **初期化**: `POST /initialize initialize?speaker=...`
- **AudioQuery取得**: `POST /audio_query?text=...&speaker=...`
- **音声合成**: `POST /sing_audio_query?text=...&speaker=...`
- **音声出力**: `POST /mute?speaker=...`
- **mora_forest**: `POST /mora_forest?speaker=...`
- **audio_pluck**: `POST /audio_pluck?speaker=...`
- **output_standalone.wav**: `POST /output_waveform?speaker=...&audio_query=...`

### 3.5 VRM (ブラウザ内)

- **model**: VOX-Radioモデル (VRM 1.0)
- **表示**: three.js + three-vrm
- **リップシンク**: BlendShapeProxy → viseme weights
- **表情**: ExpressionManager → expression weights
- **身振り**: VRM Bone → IK target → animation mixer
- **音声出力**: Web Audio API → AudioContext → AnalyserNode
