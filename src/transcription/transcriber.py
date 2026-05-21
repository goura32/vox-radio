"""Transcription module using faster-whisper (large-v3-turbo).

Takes WAV audio files and produces transcription segments + raw text.
Saves output to output/transcripts/ as JSON + TXT.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore

from src.config import (
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_LANG,
    WHISPER_MODEL,
    paths,
)

log = logging.getLogger("vox-radio.transcriber")


@dataclass
class SegmentInfo:
    start: float
    end: float
    text: str
    confidence: float
    speaker: Optional[str] = None


@dataclass
class TranscriptionResult:
    batch_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: Optional[float] = None
    segments: list[SegmentInfo] = field(default_factory=list)
    raw_transcript: str = ""
    language: str = "ja"
    silence_ratio: float = 0.0
    audio_file: str = ""

    def to_json(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "timestamp": self.timestamp and time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)),
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "confidence": s.confidence,
                    "speaker": s.speaker,
                }
                for s in self.segments
            ],
            "raw_transcript": self.raw_transcript,
            "language": self.language,
            "silence_ratio": self.silence_ratio,
            "audio_file": self.audio_file,
        }


class Transcriber:
    """Wrapper around faster-whisper for speech-to-text."""

    def __init__(
        self,
        model_size: str = WHISPER_MODEL,
        device: str = WHISPER_DEVICE,
        compute_type: str = WHISPER_COMPUTE_TYPE,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._initializing = False

    def _ensure_model(self):
        if self._model is not None:
            return
        if self._initializing:
            return
        self._initializing = True
        log.info("Loading %s on %s (%s)...", self.model_size, self.device, self.compute_type)
        if WhisperModel is None:
            raise ImportError("faster_whisper not installed")
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            num_workers=2,
        )
        log.info("Model loaded: %s@%s", self.model_size, self.device)
        self._initializing = False

    def transcribe_file(
        self,
        wav_path: str,
        language: str = WHISPER_LANG,
        min_silence_duration: float = 1.0,
    ) -> TranscriptionResult:
        """Transcribe a WAV file and return result."""
        self._ensure_model()

        segments, info = self._model.transcribe(
            wav_path,
            word_timestamps=False,
            batch_size=1,
            language=language,
            initial_prompt="日本語の会話。",
        )

        segs: list[SegmentInfo] = []
        for seg in segments:
            if seg.end - seg.start < 0.3:
                continue
            segs.append(SegmentInfo(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                confidence=seg.avg_logprob,
            ))

        raw = " ".join(s.text for s in segs)

        total_dur = sum(s.end - s.start for s in segs) + min_silence_duration * max(0, len(segs) - 1)
        silence_ratio = max(0.0, 1.0 - (total_dur / (info.duration or 1.0))) if info.duration else 0.0

        result = TranscriptionResult(
            timestamp=time.time(),
            segments=segs,
            raw_transcript=raw,
            language=info.language or "ja",
            silence_ratio=max(0.0, min(1.0, silence_ratio)),
            audio_file=wav_path,
        )

        self._save(result, wav_path)
        return result

    def _save(self, result: TranscriptionResult, audio_file: str):
        p = paths()
        trans_path = Path(p["trans_dir"]) / f"trans_{result.batch_id}.json"
        with open(trans_path, "w") as f:
            json.dump(result.to_json(), f, ensure_ascii=False, indent=2)
        txt_path = Path(p["trans_dir"]) / f"trans_{result.batch_id}.txt"
        with open(txt_path, "w") as f:
            f.write(result.raw_transcript)
        log.info("Transcription saved: %s (%d segments)", trans_path, len(result.segments))

    @property
    def model_info(self) -> dict:
        if self._model is None:
            return {"loaded": False}
        return {"loaded": True, "size": self.model_size, "device": self.device}
