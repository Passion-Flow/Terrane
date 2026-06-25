"""Video AI parsing (in-house pipeline, pure DashScope, no public-internet upload required):

ffmpeg extracts keyframes + the audio track -> frames are base64-sent to qwen-vl-plus for visual descriptions, the audio track is base64-sent to qwen3-asr-flash for transcription
-> merged into structured Markdown (transcript + timestamped visual descriptions) -> fed into the existing chunking / embedding / RAG / graph pipeline.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import tempfile

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import model_client
from app.services.model_client import ModelError

log = structlog.get_logger("terrane.parse.video")

VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/x-matroska"}
_MAX_FRAMES = 12
_SCENE_THRESHOLD = 0.30          # Scene-change threshold (smaller = more sensitive)
_AUDIO_LIMIT_BYTES = 9_000_000   # Per-call ASR size guard (over-long audio tracks are truncated; segmenting long videos is a future enhancement)
_PTS = re.compile(rb"pts_time:([0-9.]+)")


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return proc.returncode or 0, out, err


async def _scene_keyframes(path: str, work: str, cap: int) -> list[tuple[float, str]]:
    """Use ffmpeg scene detection to extract keyframes (at visual-change points) + parse each frame's timestamp from showinfo. Returns [(seconds, file)] in time order."""
    _code, _out, err = await _run(
        "ffmpeg", "-y", "-i", path,
        "-vf", f"select='gt(scene,{_SCENE_THRESHOLD})',showinfo", "-vsync", "vfr",
        "-frames:v", str(cap), "-q:v", "3", os.path.join(work, "s%03d.jpg"))
    times = [float(m) for m in _PTS.findall(err)]
    files = sorted(f for f in os.listdir(work) if f.startswith("s") and f.endswith(".jpg"))
    return [(times[i] if i < len(times) else 0.0, os.path.join(work, f)) for i, f in enumerate(files)]


async def _duration(path: str) -> float:
    code, out, _err = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", path)
    try:
        return float(out.decode().strip()) if code == 0 else 0.0
    except ValueError:
        return 0.0


def _ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


async def parse_video(db: AsyncSession, path: str) -> str:
    """Parse a video -> Markdown (speech transcript + scene keyframe descriptions, with real timestamps). Returns an empty string if no model channel is available.

    Scene-based (comparable to SceneRAG / VideoRAG): keyframes are taken at visual-change points rather than at fixed intervals, aligning better with content sections;
    if there are no scene changes (a static video), it falls back to fixed intervals."""
    dur = await _duration(path)
    work = tempfile.mkdtemp(prefix="trn_vid_")
    audio = os.path.join(work, "a.wav")
    try:
        # Scene keyframes + audio-track extraction (in parallel)
        scene, _audio_res = await asyncio.gather(
            _scene_keyframes(path, work, _MAX_FRAMES),
            _run("ffmpeg", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", audio),
        )
        # Fallback: no scene changes -> extract frames at fixed intervals
        if not scene:
            n = min(_MAX_FRAMES, max(2, int(dur // 10) or 2))
            interval = max(1.0, dur / n) if dur else 5.0
            await _run("ffmpeg", "-y", "-i", path, "-vf", f"fps=1/{interval:.3f}", "-frames:v", str(n),
                       "-q:v", "3", os.path.join(work, "f%02d.jpg"))
            files = sorted(f for f in os.listdir(work) if f.startswith("f") and f.endswith(".jpg"))
            scene = [(i * interval, os.path.join(work, f)) for i, f in enumerate(files)]

        # Transcription
        transcript = ""
        if os.path.exists(audio) and 0 < os.path.getsize(audio) <= _AUDIO_LIMIT_BYTES:
            try:
                b = base64.b64encode(open(audio, "rb").read()).decode()
                transcript = (await model_client.asr(db, b)) or ""
            except ModelError as e:
                log.warning("video_asr_failed", error=str(e))

        # Keyframe descriptions (with real timestamps)
        captions: list[str] = []
        for ts, fp in scene:
            try:
                b = base64.b64encode(open(fp, "rb").read()).decode()
                cap = await model_client.vl_caption(db, b)
            except ModelError as e:
                log.warning("video_vl_failed", error=str(e))
                cap = None
            if cap:
                captions.append(f"- [{_ts(ts)}] {cap.strip()}")

        parts = []
        if transcript.strip():
            parts.append("## Video Speech Transcript\n" + transcript.strip())
        if captions:
            parts.append("## Scene Keyframes (by visual-change points)\n" + "\n".join(captions))
        return "\n\n".join(parts).strip()
    finally:
        for fn in os.listdir(work):
            try:
                os.unlink(os.path.join(work, fn))
            except OSError:
                pass
        try:
            os.rmdir(work)
        except OSError:
            pass
