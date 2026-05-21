"""Summarizer using Ollama (Gemma4 e4b) with sentiment + context-aware prompts.

Context mode: appends the last N transcripts as context so summaries flow naturally.
Emotion tracking: returns emotion scores per-batch.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import ollama
except ImportError:
    ollama = None

from src.config import (
    OLLAMA_MODEL,
    OLLAMA_URL,
    SUMMARY_MAX_TOKENS,
    EMOTION_ANALYSIS,
    USE_CONTEXT,
    CONTEXT_ROLLBACK_DEPTH,
    paths,
)

log = logging.getLogger("vox-radio.summarizer")


@dataclass
class EmotionScores:
    joy: float = 0.0
    sadness: float = 0.0
    surprise: float = 0.0
    fear: float = 0.0
    anger: float = 0.0
    trust: float = 0.0
    anticipation: float = 0.0

    def dominant(self) -> str:
        return max(vars(self).items(), key=lambda x: x[1])[0]


@dataclass
class SummaryResult:
    batch_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: Optional[float] = None
    model: str = OLLAMA_MODEL
    summary: str = ""
    sentiment: dict = field(default_factory=lambda: {"label": "neutral", "score": 0.5})
    emotions: Optional[EmotionScores] = None
    keywords: list[str] = field(default_factory=list)
    context_used: bool = False
    raw_response: str = ""

    def to_json(self) -> dict:
        emotions_dict = None
        if self.emotions:
            emotions_dict = vars(self.emotions)
        return {
            "batch_id": self.batch_id,
            "timestamp": self.timestamp and time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)),
            "model": self.model,
            "summary": self.summary,
            "sentiment": self.sentiment,
            "emotions": emotions_dict,
            "keywords": self.keywords,
            "context_used": self.context_used,
        }


class Summarizer:
    PROMPT = """あなたは、日本のFMラジオ放送を要約するアシスタントです。
以下の文字起こしテキストを受けて、以下のJSON形式で出力してください。
出力は必ずJSON形式のみとしてください。

{{
  "summary": "500文字以内の要約",
  "sentiment": {{"label": "positive/neutral/negative", "score": 0.0-1.0}},
  "emotions": {{"joy": 0.0-1.0, "sadness": 0.0-1.0, "surprise": 0.0-1.0, "fear": 0.0-1.0, "anger": 0.0-1.0, "trust": 0.0-1.0, "anticipation": 0.0-1.0}},
  "keywords": ["キーワード1", "キーワード2", "キーワード3"]
}}

文字起こしテキスト:
"""

    def __init__(self, model: str = OLLAMA_MODEL):
        self.model = model

    def summarize(self, text: str, context: str = "") -> SummaryResult:
        """Summarize and analyze emotion. Context is appended if USE_CONTEXT=True."""
        log.info("Summarizing with %s (max=%d)...", self.model, SUMMARY_MAX_TOKENS)

        prompt = self.PROMPT + text[:4000]
        if USE_CONTEXT and context:
            prompt = (
                "直前の放送からの文字起こし（継続した内容として要約してください）:\n"
                f"{context}\n\n"
                "現在の放送:\n" + text[:4000]
            )
            prompt += "\n\n直前の内容も踏まえて要約してください。"

        if ollama is None:
            log.warning("ollama not installed, using fallback")
            return self._fallback(text)

        resp = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system",
                 "content": "You summarize Japanese FM radio transcripts as continuous content. "
                            "Output ONLY valid JSON — no markdown, no code fences."},
                {"role": "user", "content": prompt},
            ],
            options={"num_predict": SUMMARY_MAX_TOKENS, "temperature": 0.3},
        )

        raw = resp["message"]["content"]
        log.debug("Raw Ollama response: %s", raw[:500])
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> SummaryResult:
        cleaned = raw
        for marker in ["```json", "```"]:
            if marker in cleaned:
                start = cleaned.index(marker) + len(marker)
                cleaned = cleaned[start:]
                break

        brace_start = cleaned.find("{")
        brace_end = cleaned.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            cleaned = cleaned[brace_start:brace_end + 1]

        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            log.warning("Failed to parse summary JSON, fallback")
            data = {"summary": cleaned[:500], "sentiment": {"label": "neutral", "score": 0.5},
                    "emotions": {}, "keywords": []}

        emotions_data = data.get("emotions", {})
        result = SummaryResult(
            timestamp=time.time(), model=self.model,
            summary=data.get("summary", raw[:500]),
            sentiment=data.get("sentiment", {"label": "neutral", "score": 0.5}),
            emotions=EmotionScores(**emotions_data) if EMOTION_ANALYSIS and emotions_data else None,
            keywords=data.get("keywords", []),
            raw_response=raw,
        )
        self._save(result)
        return result

    def _save(self, result):
        p = paths()
        summ_path = Path(p["summ_dir"]) / f"summ_{result.batch_id}.json"
        with open(summ_path, "w") as f:
            json.dump(result.to_json(), f, ensure_ascii=False, indent=2)
        log.info("Summary saved: %s (context_used=%s)", summ_path, result.context_used)

    def _fallback(self, text: str) -> SummaryResult:
        return SummaryResult(
            timestamp=time.time(), model=self.model,
            summary=text[:500] + " (Ollama未接続)",
            sentiment={"label": "neutral", "score": 0.5},
            emotions=EmotionScores() if EMOTION_ANALYSIS else None,
            keywords=[], raw_response=text,
        )
