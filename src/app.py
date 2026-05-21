"""Main orchestrator — radio → transcription → summarization → VOICEVOX → VRM pipeline.

Continuously:
1. Receives HeartFM Ogg/Opus via JCBA API
2. Transcribes with faster-whisper large-v3-turbo
3. Summarizes with Ollama (Gemma4 e4b) + sentiment analysis
4. Synthesizes with VOICEVOX
5. Generates VRM blend shape frames
6. Saves all intermediate artifacts to output/
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from src.radio.receiver import Receiver
from src.transcription.transcriber import Transcriber
from src.summarization.summarizer import Summarizer
from src.tts.vox_player import VoxSynthesizer
from src.vr_renderer.vrm_generator import VRMVisualizer
from src.config import (
    HEARTFM_STATION_ID,
    PIPELINE_LOOP,
    RADIO_BATCH_SECONDS,
    RADIO_MINUTES,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("output/pipeline.log"),
    ],
)
log = logging.getLogger("vox-radio.pipeline")


async def run_batch():
    """Run one pipeline cycle."""
    log.info("=== Pipeline batch start ===")

    # 1. Receive audio
    receiver = Receiver(HEARTFM_STATION_ID)
    await receiver.open()
    log.info("Receiving for %ds...", RADIO_BATCH_SECONDS)
    frames = await receiver.receive_frames(RADIO_BATCH_SECONDS)
    log.info("Received %d frames", len(frames))

    # Save raw audio
    wav_path = receiver.save_raw_to_wav(
        f"output/raw/batch_{int(time.time())}.wav"
    )
    log.info("Raw audio: %s", wav_path)

    # 2. Transcribe
    log.info("Transcribing...")
    transcriber = Transcriber()
    result = transcriber.transcribe_file(wav_path)
    log.info("Transcribed (%d segments): %s", len(result.segments), result.raw_transcript[:100])

    # Save raw data artifact
    with open(f"output/transcripts/batch_{result.batch_id}_raw.json", "w") as f:
        json.dump({
            "frame_count": len(frames),
            "total_bytes": sum(len(f.raw_data) for f in frames) if frames else 0,
        }, f, indent=2)

    # 3. Summarize
    log.info("Summarizing...")
    summarizer = Summarizer()
    summary = summarizer.summarize(result.raw_transcript)
    log.info("Summary: %s", summary.summary[:80])
    log.info("Sentiment: %s (score=%.2f)", summary.sentiment.get("label"), summary.sentiment.get("score", 0))
    if summary.emotions:
        log.info("Dominant emotion: %s", summary.emotions.dominant())

    # 4. VOICEVOX synthesis
    if summary.summary and len(summary.summary) > 0:
        log.info("Synthesizing voice...")
        synth = VoxSynthesizer()
        wav_file = synth.save_synthesis(summary.summary)
        log.info("Synthesized: %s", wav_file)
    else:
        wav_file = ""
        log.warning("No summary text — skipping synthesis")

    # 5. VRM blend shapes
    vrm = VRMVisualizer()
    frame = vrm.set_expression(
        "happy" if summary.sentiment.get("score", 0.5) > 0.6 else "neutral",
        weight=min(1.0, summary.sentiment.get("score", 0.5)),
    )
    frame_body = vrm.set_body_motion(breath_scale=0.02)
    frame_body.save_frame()
    log.info("VRM frames saved")

    # Save batch summary record
    record = {
        "batch_id": result.batch_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "station": HEARTFM_STATION_ID,
        "transcript_file": f"trans_{result.batch_id}.json",
        "summary_file": f"summ_{summary.batch_id}.json",
        "synth_file": wav_file,
    }
    with open(f"output/batch_record_{result.batch_id}.json", "w") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    await receiver.close()
    log.info("=== Pipeline batch end ===\n")


async def main():
    """Main loop — continuous pipeline."""
    log.info("=== VOX-Radio Pipeline starting ===")
    log.info("Station: %s", HEARTFM_STATION_ID)
    log.info("Whisper: large-v3-turbo")
    log.info("LLM: Ollama (Gemma4 e4b)")

    if PIPELINE_LOOP:
        total_secs = RADIO_MINUTES * 60
        batch_secs = RADIO_BATCH_SECONDS
        cycles = total_secs // batch_secs
        log.info("Will run %d batches (%d min)", cycles, RADIO_MINUTES)

        for i in range(cycles):
            try:
                await run_batch()
            except Exception as e:
                log.error("Batch %d failed: %s", i, e, exc_info=True)
            time.sleep(1)
    else:
        await run_batch()

    log.info("=== Pipeline complete! ===")


if __name__ == "__main__":
    asyncio.run(main())
