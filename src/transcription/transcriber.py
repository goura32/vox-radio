"""Transcription module using faster-whisper (large-v3-turbo) with overlap-dedup.

Dedup: removes phrases from the beginning that match the end of the previous transcript
(overlap region between alternating streams).

Context: keeps last N transcripts for rolling context in summarization.
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

from src.config import (WHISPER_COMPUTE_TYPE, WHISPER_DEVICE,
                        WHISPER_LANG, WHISPER_MODEL, OVERLAP_DEDUP_WORDS)

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
    deduplicated: list[SegmentInfo] = field(default_factory=list)
    raw_transcript: str = ""
    language: str = "ja"
    silence_ratio: float = 0.0
    audio_file: str = ""

    def to_json(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "timestamp": self.timestamp and time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)),
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text,
                 "confidence": s.confidence, "speaker": s.speaker}
                for s in self.segments
            ],
            "deduplicated": [
                {"start": s.start, "end": s.end, "text": s.text,
                 "confidence": s.confidence}
                for s in self.deduplicated
            ],
            "raw_transcript": self.raw_transcript,
            "language": self.language,
            "silence_ratio": self.silence_ratio,
            "audio_file": self.audio_file,
        }


class Transcriber:
    """Transcribe with faster-whisper + overlap dedup + context."""
    def __init__(self, model_size: str = WHISPER_MODEL,
                 device: str = WHISPER_DEVICE, compute_type: str = WHISPER_COMPUTE_TYPE):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._initializing = False
        self._last_n_transcripts: list[str] = []
        self._dedup_last_n_words = 10  # match last N words from prev

    def _ensure_model(self):
        if self._model is not None:
            return
        if self._initializing:
            return
        self._initializing = True
        log.info("Loading %s on %s (%s)...",
                 self.model_size, self.device, self.compute_type)
        if WhisperModel is None:
            raise ImportError("faster_whisper not installed")
        self._model = WhisperModel(self.model_size, device=self.device,
                                   compute_type=self.compute_type, num_workers=2)
        log.info("Model loaded: %s@%s", self.model_size, self.device)
        self._initializing = False

    def get_context_text(self, depth: int = 5) -> str:
        """Return last N transcripts for context."""
        return "\n\n[---]\n".join(self._last_n_transcripts[-depth:])

    def transcribe_file(self, wav_path: str, prev_text: str = "",
                        language: str = WHISPER_LANG) -> TranscriptionResult:
        """Transcribe WAV → segments, dedup overlap, return result."""
        self._ensure_model()

        segments, info = self._model.transcribe(wav_path, word_timestamps=False,
                                                batch_size=1, language=language,
                                                initial_prompt="日本語の会話。")

        all_segs: list[SegmentInfo] = []
        for seg in segments:
            if seg.end - seg.start < 0.3:
                continue
            all_segs.append(SegmentInfo(start=seg.start, end=seg.end,
                                        text=seg.text.strip(), confidence=seg.avg_logprob))

        # Overlap dedup: remove segments at the start that match prev_text
        deduped_segs = self._dedup_overlap(all_segs, prev_text)

        raw = " ".join(s.text for s in deduped_segs)
        total_speech = sum(s.end - s.start for s in deduped_segs)
        silence_ratio = max(0.0, 1.0 - (total_speech / (info.duration or 1.0))) if info.duration else 0.0

        result = TranscriptionResult(
            timestamp=time.time(), segments=all_segs, deduplicated=deduped_segs,
            raw_transcript=raw, language=info.language or "ja",
            silence_ratio=max(0.0, min(1.0, silence_ratio)), audio_file=wav_path)

        self._save(result, wav_path)
        self._last_n_transcripts.append(raw)
        return result

    def _dedup_overlap(self, segs: list[SegmentInfo], prev_text: str) -> list[SegmentInfo]:
        """Strip N words from the start of the transcript that match prev_text end."""
        if not prev_text or not segs:
            return segs
        prev_words = prev_text.strip().split()[-min(self._dedup_last_n_words, 10):]
        if not prev_words:
            return segs

        result: list[SegmentInfo] = []
        skip = 0
        for seg in segs:
            words = seg.text.split()
            if skip < len(prev_words):
                # Compare current segment with remaining prev_words
                if words[:len(prev_words) - skip] == prev_words[skip:]:
                    skip += len(words)
                    continue
                elif seg.text.startswith(" ".join(prev_words[skip:min(skip + 1, len(prev_words))])):
                    skip += 1
                    continue
            result.append(seg)
        return result

    def _save(self, result: TranscriptionResult, audio_file: str):
        p = {"base": "output", "trans_dir": "output/transcripts"}
        trans_path = Path(p["trans_dir"]) / f"trans_{result.batch_id}.json"
        with open(trans_path, "w", encoding="utf-8") as f:
            json.dump(result.to_json(), f, ensure_ascii=False, indent=2)
        txt_path = Path(p["trans_dir"]) / f"trans_{result.batch_id}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(result.raw_transcript)
        log.info("Transcription: %d segs → %d deduped (%s)",
                 len(result.segments), len(result.deduplicated), trans_path)

    @property
    def model_info(self) -> dict:
        if self._model is None:
            return {"loaded": False}
        return {"loaded": True, "size": self.model_size, "device": self.device}
