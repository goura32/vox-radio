"""VRM Visualizer + blend-shape + idle animation system.

- Lip sync from phonemes
- Emotion expressions (controlled per-expression-slot)
- Idle animation: random blinks + body sway when no speech
- Generates vrma_frames.json for HTML viewer
"""
import json
import logging
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.config import (VRM_MODEL_PATH,
                        EXPRESSION_INTERVAL,
                        IDLE_BLINK_INTERVAL,
                        IDLE_BLINK_DURATION,
                        IDLE_BODY_SWAY_MIN, IDLE_BODY_SWAY_MAX,
                        IDLE_BLINK_SWAY_INTERVAL,
                        IDLE_RANDOM_BLINK_MIN, IDLE_RANDOM_BLINK_MAX,
                        paths)

log = logging.getLogger("vox-radio.vrm")

# ── phoneme → VRM blend-shape name ─────────
LIP_MAP = {
    "a":   "a",  "i":   "i",  "u":   "u",  "e":  "e", "o":  "o",
    "A":   "a",  "I":   "i",  "U":   "u",  "E":  "e", "O":  "o",
    "k":   "u",  "g":   "u",
    "t":   "u",  "d":   "u",  "n":   "u",
    "h":   "u",  "b":   "u",  "p":   "u",  "m":  "a",
    "r":   "e",  "l":   "e",
    "w":   "u",  "y":   "i",
    "q":   "i",
    "N":   "a",
}

EMOTION_MAP = {
    "happy":   ("happy",   0.8),
    "joy":     ("joy",     0.6),
    "surprised": ("surprised", 0.7),
    "sad":     ("sad",     0.6),
    "angry":   ("angry",   0.5),
    "funny":   ("funny",   0.4),
    "neutral": ("neutral", 1.0),
}


# ── frame data ──────────────────────────────
@dataclass
class BlendShapeFrame:
    """One frame of VRM blend-shape weights."""
    timestamp: float
    lips:      dict = field(default_factory=lambda: {"a":0,"i":0,"u":0,"e":0,"o":0})
    expr:      dict = field(default_factory=lambda: {"neutral":1.0})
    body:      dict = field(default_factory=dict)
    idle:      str = "none"        # none | blink | sway | breathe

    def to_dict(self) -> dict:
        return {"t": self.timestamp, "lips": self.lips, "expr": self.expr,
                "body": self.body, "idle": self.idle}

    def save(self):
        """Append to viz/vrma_frames.json."""
        viz_dir = Path(paths()["base"]) / "viz"
        viz_dir.mkdir(parents=True, exist_ok=True)
        path = viz_dir / "vrma_frames.json"
        frames = [self.to_dict()]
        if path.exists():
            with open(path) as f:
                frames = json.load(f) + frames
        with open(path, "w") as f:
            json.dump(frames, f, ensure_ascii=False, indent=2)


# ── VRM visualizer ──────────────────────────
class VRMVisualizer:
    """Lip-sync · expression · idle animation."""

    def __init__(self, model_path: str = VRM_MODEL_PATH):
        self.model_path = model_path
        self._expr_timer = time.time()
        self._expr_name  = "neutral"

        # idle timers
        self._blink_timer  = time.time()
        self._sway_timer   = time.time()
        self._sway_angles  = {"x": 0.0, "y": 0.0}

    # ── lip sync ──
    def phoneme_frame(self, phoneme: str, intensity: float = 1.0) -> BlendShapeFrame:
        frame = BlendShapeFrame(timestamp=time.time())
        frame.lips = {c: 0.0 for c in "aiueo"}
        lo = phoneme.lower()
        if lo in LIP_MAP:
            frame.lips[LIP_MAP[lo]] = min(intensity, 1.0)
        frame.expr = {"neutral": 1.0}
        return frame

    def lip_sync_from_phonemes(self, phonemes: list[str]) -> list[BlendShapeFrame]:
        return [self.phoneme_frame(p) for p in phonemes]

    def lip_sync_from_text(self, text: str) -> list[BlendShapeFrame]:
        """Naive → split text into phoneme-like chunks."""
        phs = []
        for ch in text.replace(" ", ""):
            if ch in "aiueoAIUEO":
                phs.append(ch)
        if not phs:
            phs = ["a"]
        return self.lip_sync_from_phonemes(phs)

    # ── expression (controlled per slot) ──
    def apply_expression(self, emotion: str, weight: float = 1.0) -> BlendShapeFrame:
        frame = BlendShapeFrame(timestamp=time.time())
        frame.expr = {"neutral": 0.0}
        preset, base_w = EMOTION_MAP.get(emotion, ("neutral", 1.0))
        frame.expr[preset] = min(base_w * weight, 1.0)
        self._expr_name = emotion
        return frame

    def auto_expression(self, emotion: str, weight: float) -> BlendShapeFrame | None:
        """Return frame only if expression slot has expired."""
        now = time.time()
        if now - self._expr_timer < EXPRESSION_INTERVAL:
            return None
        self._expr_timer = now
        self._expr_name = emotion
        return self.apply_expression(emotion, weight)

    @property
    def current_expression(self) -> str:
        return self._expr_name

    # ── body motion ──
    def body_frame(self, chest: float = 0.02, tilt: float = 0.0) -> BlendShapeFrame:
        frame = BlendShapeFrame(timestamp=time.time())
        frame.body = {"chest_breath": chest, "head_tilt": tilt}
        return frame

    # ── idle animation ────────────────────────────────────────
    def idle_frame(self) -> BlendShapeFrame:
        """Generate one idle frame with random blink + sway."""
        now = time.time()
        frame = BlendShapeFrame(timestamp=now)
        frame.lips = {c: 0.0 for c in "aiueo"}
        frame.expr = {"neutral": 1.0}
        frame.body = {"chest_breath": 0.02, "head_tilt": 0.0}

        # blink
        if now - self._blink_timer > random.uniform(IDLE_RANDOM_BLINK_MIN, IDLE_RANDOM_BLINK_MAX):
            self._blink_timer = now
            frame.idle = "blink"
            frame.expr["blink"] = 1.0
            log.debug("idle: blink")
            return frame

        # body sway (re-randomize at fixed interval)
        if now - self._sway_timer > IDLE_BLINK_SWAY_INTERVAL:
            self._sway_timer = now
            sx = random.uniform(IDLE_BODY_SWAY_MIN, IDLE_BODY_SWAY_MAX)
            sy = random.uniform(IDLE_BODY_SWAY_MIN, IDLE_BODY_SWAY_MAX)
            self._sway_angles = {"x": sx, "y": sy}
            frame.body.update({"head_tilt": sx, "body_rotation": sy})
            frame.idle = "sway"
            log.debug("idle: sway x=%.3f y=%.3f", sx, sy)
            return frame

        # gentle breathing
        breath = 0.02 + 0.01 * math.sin(now * 0.8)
        frame.body["chest_breath"] = breath

        return frame
