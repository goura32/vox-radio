"""VOICEVOX TTS Synthesizer.

Connects to VOICEVOX ENGINE API to generate AudioQuery from text,
then synthesize audio to WAV.
"""
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from typing import Optional

import requests

from src.config import (
    VOICEVOX_URL,
    VOICEVOX_SPEAKER_ID,
    VOICEVOX_SPEED,
    VOICEVOX_PITCH,
    VOICEVOX_VOLUME,
    VOICEVOX_INTONATION,
    paths,
)

log = logging.getLogger("vox-radio.tts")


class VoxSynthesizer:
    """Wrapper around VOICEVOX ENGINE API."""

    def __init__(self, speaker_id: int = VOICEVOX_SPEAKER_ID):
        self.speaker_id = speaker_id

    def initialize_speaker(self, speaker_id: int) -> bool:
        """Initialize speaker on VOICEVOX engine (required before synthesis)."""
        try:
            resp = requests.post(
                f"{VOICEVOX_URL}/initialize_speaker?speaker={speaker_id}",
                timeout=30,
            )
            return resp.status_code == 204
        except Exception as e:
            log.error("Speaker init failed: %s", e)
            return False

    def get_available_speakers(self) -> list[dict]:
        """Get list of available speakers/styles."""
        try:
            resp = requests.get(f"{VOICEVOX_URL}/speakers", timeout=10)
            return resp.json()
        except Exception as e:
            log.error("Failed to get speakers: %s", e)
            return []

    def query_text_to_audio_query(self, text: str) -> Optional[dict]:
        """Generate AudioQuery from text."""
        if text.strip() == "":
            log.warning("Empty text — no AudioQuery generated")
            return None

        if not self.initialize_speaker(self.speaker_id):
            log.error("Failed to initialize speaker, cannot generate AudioQuery")
            return None

        try:
            resp = requests.post(
                f"{VOICEVOX_URL}/audio_query?text={quote(text)}&speaker={self.speaker_id}",
                timeout=10,
            )
            resp.raise_for_status()
            query = resp.json()

            # Apply defaults
            query["speedScale"] = VOICEVOX_SPEED
            query["pitchScale"] = VOICEVOX_PITCH
            query["intonationScale"] = VOICEVOX_INTONATION
            query["volumeScale"] = VOICEVOX_VOLUME

            return query

        except Exception as e:
            log.error("AudioQuery generation failed: %s", e)
            return None

    def synthesize(self, text: str, speaker_id: Optional[int] = None) -> Optional[bytes]:
        """Synthesize text → WAV bytes via VOICEVOX ENGINE."""
        target_speaker = speaker_id or self.speaker_id
        query = self.query_text_to_audio_query(text)
        if not query:
            return None

        try:
            resp = requests.post(
                f"{VOICEVOX_URL}/synthesis_hack?speaker={target_speaker}",
                json=query,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            log.error("Synthesis failed: %s", e)
            return None

    def save_synthesis(self, text: str, speaker_id: Optional[int] = None, output_dir: Optional[str] = None) -> str:
        """Synthesize and save to WAV file. Returns file path."""
        wav_bytes = self.synthesize(text, speaker_id)
        if not wav_bytes:
            return ""

        save_dir = output_dir or paths()["wav_dir"]
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        target_speaker = speaker_id or self.speaker_id
        out_path = Path(save_dir) / f"synth_{target_speaker}_{uuid.uuid4().hex[:8]}.wav"
        with open(out_path, "wb") as f:
            f.write(wav_bytes)

        log.info("Synthesized WAV saved: %s (%d bytes)", out_path, len(wav_bytes))
        return str(out_path)


# Convenience instance
synth = VoxSynthesizer()
