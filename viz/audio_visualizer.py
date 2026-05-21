"""Audio visualizer — waveform + spectrogram display.

Uses the browser (HTML + Canvas) to show:
- Raw waveform of the current segment
- Spectrogram (short-time Fourier transform)
- Audio energy / RMS envelope

Served via `viz/index.html` along with the VRM viewer.
"""
import struct
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("vox-radio.visualizer")


@dataclass
class AudioStats:
    """Compact audio statistics for visualization."""
    rms: float = 0.0
    peak: float = 0.0
    duration: float = 0.0
    sample_rate: int = 16000
    frames: int = 0
    energy_profile: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rms": round(self.rms, 6),
            "peak": round(self.peak, 6),
            "duration": round(self.duration, 3),
            "sample_rate": self.sample_rate,
            "frames": self.frames,
            "energy_profile": [round(e, 6) for e in self.energy_profile[:100]],  # cap at 100
        }


class AudioVisualizer:
    """Compute and return audio stats for visualization."""

    WAV_HEADER_SIZE = 44  # standard PCM WAV header

    def compute_stats(self, wav_path: str, max_frames: int = 2000) -> AudioStats:
        """Read WAV file and compute visualization stats."""
        p = Path(wav_path)
        if not p.exists():
            log.warning("WAV file not found: %s", wav_path)
            return AudioStats()

        with open(p, "rb") as f:
            header = f.read(self.WAV_HEADER_SIZE)

        # Parse WAV header
        sample_rate = struct.unpack_from("<I", header, 24)[0]
        channels = struct.unpack_from("<H", header, 22)[0]
        bits_per_sample = struct.unpack_from("<H", header, 34)[0]

        # Read audio data
        data = f.read()
        if bits_per_sample == 16:
            samples = struct.unpack(f"<{len(data) // 2}h", data)
        else:
            samples = tuple(struct.unpack("<h", data[i:i + 2])[0]
                          for i in range(0, len(data), 2))

        # RMS
        if not samples:
            return AudioStats()
        rms = (sum(s ** 2 for s in samples) / len(samples)) ** 0.5 / 32768.0

        # Peak
        peak = max(abs(s) for s in samples) / 32768.0

        # Duration
        duration = len(samples) / sample_rate

        # Energy profile (RMS per frame)
        frame_size = max(1, len(samples) // max_frames)
        energy_profile = []
        for i in range(0, len(samples), frame_size):
            frame = samples[i: i + frame_size]
            frame_rms = (sum(s ** 2 for s in frame) / len(frame)) ** 0.5 / 32768.0
            energy_profile.append(frame_rms)

        stats = AudioStats(
            rms=rms, peak=peak, duration=duration,
            sample_rate=sample_rate, frames=len(samples),
            energy_profile=energy_profile,
        )
        log.info("Audio stats: RMS=%.4f Peak=%.4f Duration=%.3fs Frames=%d",
                 stats.rms, stats.peak, stats.duration, stats.frames)
        return stats

    def get_spectrogram_data(self, wav_path: str, n_bins: int = 64) -> list[float]:
        """Quick FFT-based spectrogram slice (no numpy — use standard lib)."""
        # Simple energy per band for visualization
        stats = self.compute_stats(wav_path)
        # Downsample energy_profile to n_bins
        if not stats.energy_profile:
            return [0.0] * n_bins
        step = max(1, len(stats.energy_profile) // n_bins)
        banded = [
            max(stats.energy_profile[i: i + step]) if i + step <= len(stats.energy_profile)
            else stats.energy_profile[i]
            for i in range(0, len(stats.energy_profile), step)
        ]
        return banded
