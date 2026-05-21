"""VRM Visualizer & blend shape generator.

Generates VRM blend shape weights (lip-sync + expression + body motion)
from AudioQuery phoneme data. Saves as JSON frames for viz/index.html viewer.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.config import VRM_MODEL_PATH, paths

log = logging.getLogger("vox-radio.vrm")

# ── Lip sync phoneme → VRM blend shape name mappings ──
LIP_MAP = {
    "a":   "a",  "i":   "i",  "u":   "u",  "e":  "e", "o":  "o",
    "A":   "a",  "I":   "i",  "U":   "u",  "E":  "e", "O":  "o",
    "k":   "u",  "g":   "u",
    "t":   "u",  "d":   "u",  "n":   "u",
    "h":   "u",  "b":   "u",  "p":   "u",  "m":  "a",
    "r":   "e",  "l":   "e",
    "w":   "u",  "y":   "i",
    "q":   "i",
    "N":   "a",  # n (nasal)
}

# ── Emotion → (preset, base_weight) ──
EMOTION_MAP = {
    "happy":   ("happy",  0.8),
    "joy":     ("joy",    0.6),
    "surprised": ("surprised", 0.7),
    "sad":     ("sad",    0.6),
    "angry":   ("angry",  0.5),
    "funny":   ("funny",  0.4),
    "neutral": ("a", 0.0),
}


@dataclass
class BlendShapeFrame:
    """One frame of VRM blend shape weights."""
    timestamp: float
    lips: dict[str, float] = field(default_factory=dict)
    expressions: dict[str, float] = field(default_factory=dict)
    body: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "t": self.timestamp,
            "lips": self.lips,
            "expressions": self.expressions,
            "body": self.body,
        }

    def save_frame(self) -> str:
        """Append frame to viz/vrma_frames.json and return path."""
        viz_dir = Path(paths()["base"]) / "viz"
        viz_dir.mkdir(parents=True, exist_ok=True)
        viz_frames = viz_dir / "vrma_frames.json"

        all_frames = [self.to_dict()]
        if viz_frames.exists():
            with open(viz_frames) as f:
                existing = json.load(f)
            all_frames = existing + all_frames

        with open(viz_frames, "w") as f:
            json.dump(all_frames, f, ensure_ascii=False, indent=2)

        return str(viz_frames)


class VRMVisualizer:
    """Generate VRM blend shapes from AudioQuery phoneme data."""

    def __init__(self, vrm_model_path: str = VRM_MODEL_PATH):
        self.vrm_model_path = vrm_model_path

    def generate_from_phoneme(self, phoneme: str, intensity: float = 1.0) -> BlendShapeFrame:
        """Generate blend shape frame from a single phoneme."""
        frame = BlendShapeFrame(timestamp=time.time())
        frame.lips = {"a": 0.0, "i": 0.0, "u": 0.0, "e": 0.0, "o": 0.0}
        if phoneme.lower() in LIP_MAP:
            frame.lips[LIP_MAP[phoneme.lower()]] = min(intensity, 1.0)
        return frame

    def generate_from_audio_query(self, audio_query: dict) -> list[BlendShapeFrame]:
        """Generate blend shape frames from VOICEVOX AudioQuery."""
        frames = []
        for phrase in audio_query.get("accent_phrases", []):
            for mora in phrase.get("moras", []):
                frame = BlendShapeFrame(timestamp=time.time())
                consonant = mora.get("consonant")
                if consonant:
                    frame.lips = {"a": 0.0, "i": 0.0, "u": 0.0, "e": 0.0, "o": 0.0}
                    frame.lips[LIP_MAP.get(consonant, "a")] = 0.8
                else:
                    frame.lips["a"] = 0.7  # vowel only
                frame.expressions["neutral"] = 0.0
                frames.append(frame)
        return frames

    def set_expression(self, emotion: str = "neutral", weight: float = 1.0) -> BlendShapeFrame:
        """Set expression blend shape for an emotion."""
        if emotion in EMOTION_MAP:
            preset, base_w = EMOTION_MAP[emotion]
            frame = BlendShapeFrame(timestamp=time.time())
            frame.expressions[preset] = base_w * weight
            frame.expressions["neutral"] = 1.0 - weight
            return frame
        return BlendShapeFrame(timestamp=time.time())

    def set_body_motion(
        self,
        breath_scale: float = 0.02,
        head_tilt: float = 0.0,
        body_rotate: float = 0.0,
    ) -> BlendShapeFrame:
        """Set body motion parameters."""
        frame = BlendShapeFrame(timestamp=time.time())
        frame.body = {
            "chest_breath": breath_scale,
            "head_tilt": head_tilt,
            "body_rotation": body_rotate,
        }
        return frame
