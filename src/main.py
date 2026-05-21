"""Async VOX-Radio pipeline: Capture → Transcribe → Summarize → TTS → VRM.

Architecture
============
    ┌──────────┐   ┌──────────────┐   ┌──────────┐
    │ Dual     │──▶│ Transcribe   │──▶│ Summarize│
    │ Stream   │   │ + dedup      │   │ + expr   │
    │ Receiver │   └──────┬───────┘   └────┬─────┘
    └──────────┘          │                 │
                          ▼                 ▼
                    ┌──────────────┐   ┌──────────┐
                    ├──▶ Audio     │   │ VOICEVOX │
                    │   Context    │   │ TTS      │
                    └──────────────┘   └────┬─────┘
                                            ▼
                                     ┌──────────────┐
                                     │ VRM Visual   │
                                     │ + idle anim  │
                                     └──────────────┘

- Capture runs in the background as a stream of AudioSegment items
- Each segment is processed independently (transcribe → summarize → TTS → VRM)
- Idle animation runs continuously
- Context rolls: previous transcript text is injected into the summarizer prompt
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from src.config import (HEARTFM_STATION_ID, PIPELINE_LOOP, RADIO_MINUTES, paths)
from src.radio.receiver import DualStreamReceiver, AudioSegment
from src.transcription.transcriber import Transcriber
from src.summarization.summarizer import Summarizer
from src.tts.vox_player import VoxSynthesizer
from src.vr_renderer.vrm_generator import VRMVisualizer, BlendShapeFrame

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler("output/pipeline.log")])
log = logging.getLogger("vox-radio.pipeline")


class VOXRadioPipeline:
    """Main pipeline orchestrator."""

    # ── init ────────────────────────────────────
    def __init__(self):
        self.receiver: DualStreamReceiver | None = None
        self.transcriber: Transcriber | None = None
        self.summarizer: Summarizer | None = None
        self.synthesizer: VoxSynthesizer | None = None
        self.vrm: VRMVisualizer | None = None

        self._prev_context: str = ""       # last N raw transcripts
        self._context_buffer: list[str] = []  # rolling context
        self._ctx_depth: int = 5

        self._running = False
        self._idle_task: asyncio.Task | None = None
        self._idle_count = 0

    # ── lifecycle ────────────────────────────────
    async def start(self):
        self._running = True

        # create components
        self.receiver = DualStreamReceiver(HEARTFM_STATION_ID)
        self.transcriber = Transcriber()
        self.summarizer = Summarizer()
        self.synthesizer = VoxSynthesizer()
        self.vrm = VRMVisualizer()

        # start capture stream
        await self.receiver.start()

        # kick off background tasks
        self._capture_task = asyncio.create_task(self._capture_loop())
        self._idle_task  = asyncio.create_task(self._idle_loop())

        log.info("=== VOX-Radio Pipeline started (station=%s) ===", HEARTFM_STATION_ID)

    async def stop(self):
        self._running = False
        for t in (self._idle_task, getattr(self, "_capture_task", None)):
            if t:
                t.cancel()
        if self.receiver:
            await self.receiver.stop()
        log.info("Pipeline stopped  (handled %d segments)", self._idle_count)

    # ── capture loop ─────────────────────────────
    async def _capture_loop(self):
        """Pull segments from the receiver and dispatch async work."""
        while self._running:
            try:
                seg = await asyncio.wait_for(self.receiver.get_segment(), timeout=5.0)
            except asyncio.TimeoutError:
                continue

            log.info("Segment ready: %s (%.1fs, dup=%s)",
                     seg.segment_id, seg.duration_sec, seg.is_duplicate)
            asyncio.create_task(self._process_segment(seg))

    # ── idle loop ────────────────────────────────
    async def _idle_loop(self):
        """Continuously generate idle frames when there is no speech."""
        while self._running:
            frame = self.vrm.idle_frame()
            frame.save()
            self._idle_count += 1
            await asyncio.sleep(4.0)

    # ── process one segment ──────────────────────
    async def _process_segment(self, seg: AudioSegment):
        """Transcribe → Summarize → TTS → VRM (one segment)."""
        log.info("▶ process %s", seg.segment_id)

        # ── 1. transcribe (with previous context) ──
        prev_ctx = "\n\n>>>  ".join(self._context_buffer[-self._ctx_depth:])
        result = self.transcriber.transcribe_file(seg.wav_path, prev_ctx)

        # update rolling context
        self._context_buffer.append(result.raw_transcript)
        if len(self._context_buffer) > self._ctx_depth:
            self._context_buffer = self._context_buffer[-self._ctx_depth:]

        # ── 2. summarize (with context) ───────────
        context_text = self.transcriber.get_context_text()
        summary = self.summarizer.summarize(result.raw_transcript, context_text)
        log.info("Summary: %s", summary.summary[:80])
        log.info("Sentiment: %s (%.2f)", summary.sentiment.get("label", ""),
                 summary.sentiment.get("score", 0))

        # ── 3. update expression (periodic) ───────
        emotion = "happy" if summary.sentiment.get("score", 0.5) > 0.6 else "neutral"
        expr_frame = self.vrm.auto_expression(emotion,
                                              min(1.0, summary.sentiment.get("score", 0.5)))
        if expr_frame:
            expr_frame.save()
            log.info("Expression → %s", self.vrm.current_expression)

        # ── 4. VOICEVOX synthesis ─────────────────
        wav_file = ""
        if summary.summary and len(summary.summary) > 0:
            # generate lip-sync frames from summary phonemes
            ph_frames = self.vrm.lip_sync_from_text(summary.summary)
            for pf in ph_frames:
                pf.save()

            wav_file = self.synthesizer.save_synthesis(summary.summary)
            log.info("TTS WAV: %s", wav_file)
        else:
            # no speech → keep idle animation running
            self.vrm.idle_frame().save()

        # ── 5. save batch record ──────────────────
        record = {
            "segment_id": seg.segment_id,
            "summary_id": summary.batch_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "station": HEARTFM_STATION_ID,
            "rec_ogg": seg.raw_ogg_path,
            "rec_wav": seg.wav_path,
            "rec_meta": seg.meta_path,
            "trans_file": f"trans_{result.batch_id}.json",
            "summary_file": f"summ_{summary.batch_id}.json",
            "synth_wav": wav_file,
            "summary": summary.summary,
            "sentiment": summary.sentiment,
        }
        rec_path = Path(paths()["base"]) / "output" / f"batch_{summary.batch_id}.json"
        with open(rec_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        self._idle_count += 1
        log.info("✅ segment %s complete", seg.segment_id)


# ── entry point ────────────────────────────────
async def main():
    p = VOXRadioPipeline()

    log.info("=== VOX-Radio Pipeline starting ===")
    log.info("Station: %s  |  Whisper: large-v3-turbo  |  LLM: gemma4:e4b", HEARTFM_STATION_ID)
    log.info("Record: %ds / stream, Overlap: %ds, Streams: %d",
             60, 5, 2)

    await p.start()

    if RADIO_MINUTES > 0:
        log.info("Running for %d minutes", RADIO_MINUTES)
        await asyncio.sleep(RADIO_MINUTES * 60)
    else:
        log.info("Running indefinitely — Ctrl+C or send STOP to exit")
        while p._running:
            await asyncio.sleep(1)

    await p.stop()
    log.info("=== Pipeline complete! ===")


if __name__ == "__main__":
    asyncio.run(main())
