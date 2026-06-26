"""Video AI parsing — scene-aware, transcript-aligned, temporally-indexed pipeline (in-house, cloud VL + ASR).

Pipeline (P5 / component F5 of the all-file parsing roadmap; fixes G8 "one-shot 12-frame / 9MB-truncated"):

  1. Scene/shot detection (PySceneDetect, BSD-3, pure CPU) over the video -> shot boundaries (timecodes).
     Falls back to fixed-interval sampling when detection finds too few / too many scenes.
  2. Keyframe extraction (ffmpeg, out-of-process) — one representative frame per scene + extra frames for
     long scenes (every `_LONG_SCENE_STEP` s). Stored like figure crops (storage.video_frame_key) when a
     source id is supplied, so each frame is viewable via the same immutable-image serving route.
  3. Per-scene visual caption — the configured cloud VL channel (kind=vl) on each keyframe with a concise
     description prompt (what's visible + on-screen text/labels). Bounded by a per-video VL-call cap; beyond
     the cap captioning is skipped (frame still extracted/stored) and the skipped count is logged.
  4. ASR transcription — audio is extracted with ffmpeg and CHUNKED into fixed time windows (no 9MB
     truncation); each window is transcribed via the configured cloud ASR channel (kind=asr). The window
     offset is added back so transcript text is segment-/window-level time-aligned.
  5. Temporal alignment + index — scenes + transcript windows are merged into time-ordered SEGMENTS, each
     `[mm:ss–mm:ss]` carrying its visual caption + the transcript text falling in that interval, emitted as
     timecoded Markdown sections. Chunking then yields searchable, timecode-anchored pieces for RAG; each
     section references its stored keyframe so a hit can deep-link to `t=start`.

Public entry `parse_video(db, path, *, sid=None)` is signature-compatible with the previous one-shot version
(the extra `sid` is keyword-only and optional, so the assistant.py caller is unaffected). ffmpeg/ffprobe are
system binaries called out-of-process; if absent the pipeline degrades to an empty result rather than raising.
"""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
import tempfile
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import model_client, storage
from app.services.model_channels import get_channel
from app.services.model_client import ModelError

log = structlog.get_logger("terrane.parse.video")

VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/x-matroska"}

# --- Tunables (pure-CPU work is generous; cost is bounded only on the paid cloud VL/ASR calls) ---
_MIN_SCENES = 2              # below this PySceneDetect is treated as "found nothing" -> interval fallback
_MAX_SCENES = 400           # above this the video is over-segmented; collapse to interval sampling
_LONG_SCENE = 30.0          # a scene longer than this gets extra keyframes ...
_LONG_SCENE_STEP = 15.0     # ... one every this many seconds inside the long scene
_FALLBACK_INTERVAL = 8.0    # keyframe spacing when scene detection is unusable / there is no video stream
_AUDIO_WINDOW = 90.0        # ASR audio is chunked into windows of this many seconds (NO single-call truncation)
_VL_CONCURRENCY = 4         # parallel VL caption calls (shared ingest AsyncSession is single-threaded;
                            #   semaphore bounds in-flight HTTP, channel is resolved once and threaded in)
_ASR_CONCURRENCY = 2        # parallel ASR window calls
_VL_MAX_EDGE = 1280         # downscale the VL INPUT to <= this on the long edge (stored frame stays full-res)

# Per-video cost ceilings. A long video must not explode cost: bound the number of paid calls and log skips
# (mirrors the figures handler's per-document VL budget). Frames beyond the VL cap are still extracted/stored
# (viewable) — only the caption is skipped.
DEFAULT_MAX_VL_FRAMES = 48
DEFAULT_MAX_ASR_WINDOWS = 80   # 80 * 90s = up to 2h of audio transcribed before the window cap kicks in

_VL_CAPTION_PROMPT = (
    "这是一段视频里某一时刻的关键帧画面。请用**简洁中文**客观描述这一帧，仅用于检索：\n"
    "1) 一句话说明画面主体/场景/正在发生的动作；\n"
    "2) 逐项照抄画面中可读到的**屏幕文字/字幕/标签/标题/数字**（原样，不翻译不臆造）；\n"
    "3) 不要编造看不清的内容。只输出这段描述本身，不要标题、不要代码围栏。"
)


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    """Run an out-of-process binary (ffmpeg/ffprobe). Returns (returncode, stdout, stderr); a missing binary
    surfaces as FileNotFoundError to the caller, which degrades rather than hard-fails."""
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return proc.returncode or 0, out, err


def _ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))


def _ts(sec: float) -> str:
    m, s = divmod(int(max(0.0, sec)), 60)
    return f"{m:02d}:{s:02d}"


async def _duration(path: str) -> float:
    code, out, _err = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", path)
    try:
        return float(out.decode().strip()) if code == 0 else 0.0
    except ValueError:
        return 0.0


async def _has_audio(path: str) -> bool:
    code, out, _err = await _run("ffprobe", "-v", "error", "-select_streams", "a",
                                 "-show_entries", "stream=index", "-of", "csv=p=0", path)
    return code == 0 and bool(out.decode().strip())


def _detect_scenes(path: str) -> list[tuple[float, float]]:
    """PySceneDetect (CPU) -> [(start_sec, end_sec)] shot boundaries in time order. AdaptiveDetector is robust
    to camera motion. Returns [] on any failure (caller falls back to fixed-interval sampling)."""
    try:
        from scenedetect import AdaptiveDetector, detect
        scenes = detect(path, AdaptiveDetector())
        return [(s.get_seconds(), e.get_seconds()) for s, e in scenes if e.get_seconds() > s.get_seconds()]
    except Exception as e:  # noqa: BLE001 -- detection is best-effort; interval fallback covers all failures
        log.warning("scene_detect_failed", error=str(e))
        return []


def _interval_scenes(dur: float, interval: float = _FALLBACK_INTERVAL) -> list[tuple[float, float]]:
    """Uniform [(start,end)] windows over the duration — the fallback when scene detection is unusable."""
    if dur <= 0:
        return [(0.0, 0.0)]
    n = max(1, int(dur // interval) + (1 if dur % interval else 0))
    return [(i * interval, min((i + 1) * interval, dur)) for i in range(n)]


def _keyframe_times(scenes: list[tuple[float, float]], dur: float) -> list[tuple[int, float]]:
    """One representative timestamp per scene (its midpoint) + extra frames inside long scenes
    (every `_LONG_SCENE_STEP`). Returns [(scene_index, timestamp_sec)] in time order; the scene index lets
    several frames map back to the same scene/segment."""
    out: list[tuple[int, float]] = []
    for i, (st, en) in enumerate(scenes):
        end = en if en > st else (st + min(_FALLBACK_INTERVAL, dur or _FALLBACK_INTERVAL))
        mid = (st + end) / 2.0
        out.append((i, mid))
        span = end - st
        if span > _LONG_SCENE:
            t = st + _LONG_SCENE_STEP
            while t < end - 1.0:
                if abs(t - mid) > 2.0:      # don't duplicate the midpoint frame
                    out.append((i, t))
                t += _LONG_SCENE_STEP
    out.sort(key=lambda x: x[1])
    return out


async def _extract_frame(path: str, sec: float, dst: str) -> bool:
    """ffmpeg single-frame grab at `sec`. `-ss` before `-i` = fast input seek. Returns True if a frame landed."""
    code, _o, _e = await _run("ffmpeg", "-y", "-ss", f"{max(0.0, sec):.3f}", "-i", path,
                              "-frames:v", "1", "-q:v", "3", dst)
    return code == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0


def _vl_b64(jpg_path: str) -> str | None:
    """Base64 of a downscaled JPEG copy of the keyframe for the VL call (the stored frame stays full-res).
    Long edge <= `_VL_MAX_EDGE` so the request is small/fast/reliable. None on encode failure -> caption skip."""
    try:
        import io

        from PIL import Image
        im = Image.open(jpg_path)
        if max(im.size) > _VL_MAX_EDGE:
            im.thumbnail((_VL_MAX_EDGE, _VL_MAX_EDGE))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return None


async def _transcribe_windows(db: AsyncSession, audio: str, dur: float, work: str,
                              *, max_windows: int = DEFAULT_MAX_ASR_WINDOWS) -> list[tuple[float, float, str]]:
    """Split the extracted audio into `_AUDIO_WINDOW`-second windows, transcribe each via the cloud ASR channel,
    and return [(start_sec, end_sec, text)] time-aligned by window offset. NO 9MB single-call truncation: long
    audio is covered window by window. Bounded by `max_windows` (skips logged). Empty when no ASR channel or no
    audio. Each window is re-encoded to a fresh wav so the ASR call gets a clean, self-contained clip."""
    ch = await get_channel(db, "asr")
    if ch is None or not ch.base_url or not ch.api_key or not ch.model:
        return []
    if not os.path.exists(audio) or os.path.getsize(audio) == 0 or dur <= 0:
        return []

    starts = [i * _AUDIO_WINDOW for i in range(max(1, int(dur // _AUDIO_WINDOW) + (1 if dur % _AUDIO_WINDOW else 0)))]
    skipped = max(0, len(starts) - max_windows)
    starts = starts[:max_windows]

    sem = asyncio.Semaphore(_ASR_CONCURRENCY)
    results: dict[int, tuple[float, float, str]] = {}

    async def _one(idx: int, start: float) -> None:
        end = min(start + _AUDIO_WINDOW, dur)
        clip = os.path.join(work, f"win_{idx:03d}.wav")
        code, _o, _e = await _run("ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", audio,
                                  "-t", f"{end - start:.3f}", "-ac", "1", "-ar", "16000", clip)
        if code != 0 or not os.path.exists(clip) or os.path.getsize(clip) == 0:
            return
        try:
            b = await asyncio.to_thread(lambda: base64.b64encode(open(clip, "rb").read()).decode())
        except OSError:
            return
        async with sem:
            try:
                txt = await model_client.asr(db, b)
            except ModelError as e:
                log.warning("video_asr_window_failed", window=idx, error=str(e))
                txt = None
        if txt and txt.strip():
            results[idx] = (start, end, txt.strip())

    await asyncio.gather(*[_one(i, s) for i, s in enumerate(starts)])
    log.info("video_asr_windows", total=len(starts), transcribed=len(results), skipped=skipped,
             window_s=_AUDIO_WINDOW)
    return [results[i] for i in sorted(results)]


def _transcript_for(start: float, end: float, windows: list[tuple[float, float, str]]) -> str:
    """Concatenate transcript text from every ASR window that OVERLAPS the [start,end] segment. Window-level
    granularity (the cloud chat-completions ASR returns plain text per clip, not sub-segment word timings), so
    a window's text is attributed to any segment it overlaps — alignment is to the audio window, never lost."""
    parts = [t for (ws, we, t) in windows if we > start and ws < end and t]
    return " ".join(parts).strip()


async def parse_video(db: AsyncSession, path: str, *, sid: uuid.UUID | str | None = None,
                      max_vl: int = DEFAULT_MAX_VL_FRAMES) -> str:
    """Parse a video into timecoded Markdown segments (visual caption + aligned transcript per scene window),
    chunkable into timecode-anchored RAG pieces. Returns "" if neither VL nor ASR produced anything (e.g. no
    configured channel, or ffmpeg absent).

    `sid` (the RawSource id) makes each keyframe servable like a figure crop (storage.video_frame_key); None
    (e.g. the assistant attachment path that has no source row) -> frames are captioned but not stored, and the
    Markdown references the timecode only. `max_vl` bounds paid VL calls per video; the audio-window ASR cap is
    `DEFAULT_MAX_ASR_WINDOWS`. Both skip counts are logged."""
    if not _ffmpeg_available():
        log.warning("video_parse_no_ffmpeg")
        return ""

    dur = await _duration(path)
    has_audio = await _has_audio(path)
    work = tempfile.mkdtemp(prefix="trn_vid_")
    audio = os.path.join(work, "audio.wav")
    try:
        # --- 1. Scene detection (CPU, off-thread) + audio extraction (parallel) ---
        async def _audio_extract() -> None:
            if has_audio:
                await _run("ffmpeg", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", audio)

        scenes, _ = await asyncio.gather(asyncio.to_thread(_detect_scenes, path), _audio_extract())

        # Fall back to fixed-interval windows when detection is unusable (too few = static video / no video
        # stream; too many = over-segmented flashing content).
        used_detection = _MIN_SCENES <= len(scenes) <= _MAX_SCENES
        if not used_detection:
            scenes = _interval_scenes(dur)
        # Ensure end times are sane (last scene may report 0 end on some containers).
        scenes = [(st, en if en > st else min(st + _FALLBACK_INTERVAL, dur or (st + _FALLBACK_INTERVAL)))
                  for (st, en) in scenes]

        # --- 4. ASR (chunked windows, time-aligned) — runs concurrently with frame extraction below ---
        asr_task = asyncio.create_task(_transcribe_windows(db, audio, dur, work)) if has_audio \
            else None

        # --- 2. Keyframe extraction (one per scene + extras for long scenes) ---
        kf_times = _keyframe_times(scenes, dur)
        frames: list[tuple[int, float, str]] = []   # (scene_index, ts, file)
        for n, (scene_idx, ts) in enumerate(kf_times):
            dst = os.path.join(work, f"kf_{n:04d}.jpg")
            if await _extract_frame(path, ts, dst):
                frames.append((scene_idx, ts, dst))

        # Store frames (viewable like figure crops) when we have a source id. A failed upload never drops the
        # frame's caption/segment — only its servable ref.
        frame_ref: dict[int, str | None] = {}
        if sid is not None and frames:
            try:
                await storage.ensure_bucket()
            except Exception:  # noqa: BLE001
                pass
            for n, (_si, _ts_, fp) in enumerate(frames):
                ref = None
                try:
                    data = await asyncio.to_thread(lambda p=fp: open(p, "rb").read())
                    await storage.get_adapter().upload(storage.video_frame_key(sid, n), data,
                                                       content_type="image/jpeg")
                    ref = f"video-frame/{n}"
                except Exception as e:  # noqa: BLE001
                    log.warning("video_frame_store_failed", idx=n, error=str(e))
                frame_ref[n] = ref

        # --- 3. Per-keyframe VL captions (bounded, channel resolved ONCE, concurrent) ---
        channel = await get_channel(db, "vl")
        have_vl = channel is not None
        to_caption = list(range(len(frames)))[:max_vl] if have_vl else []
        skipped_vl = (len(frames) - len(to_caption)) if have_vl else 0
        sem = asyncio.Semaphore(_VL_CONCURRENCY)
        captions: dict[int, str] = {}

        async def _cap(n: int) -> None:
            b64 = await asyncio.to_thread(_vl_b64, frames[n][2])
            if b64 is None:
                return
            async with sem:
                try:
                    from app.services.parse import vl as parse_vl
                    txt = await model_client.vl_caption(db, b64, prompt=_VL_CAPTION_PROMPT, channel=channel)
                    if txt:
                        txt = parse_vl._strip_fence(txt)
                except Exception:  # noqa: BLE001
                    txt = None
            if txt and txt.strip():
                captions[n] = txt.strip()

        if to_caption:
            await asyncio.gather(*[_cap(n) for n in to_caption])

        windows = await asr_task if asr_task is not None else []

        # --- 5. Temporal alignment + index: one Markdown segment per scene, time-ordered ---
        # Group keyframes (with caption + stored ref) by their scene index.
        by_scene: dict[int, list[tuple[float, int]]] = {}
        for n, (scene_idx, ts, _fp) in enumerate(frames):
            by_scene.setdefault(scene_idx, []).append((ts, n))

        segments: list[str] = []
        for scene_idx, (st, en) in enumerate(scenes):
            kfs = sorted(by_scene.get(scene_idx, []))
            transcript = _transcript_for(st, en, windows)
            if not kfs and not transcript:
                continue
            header = f"### [{_ts(st)}–{_ts(en)}]"
            body: list[str] = []
            for (ts, n) in kfs:
                cap = captions.get(n)
                ref = frame_ref.get(n)
                line = f"- 关键帧 [{_ts(ts)}]"
                if ref:
                    line += f" ![帧]({ref})"
                if cap:
                    line += f"：{cap}"
                body.append(line)
            if transcript:
                body.append(f"- 语音转写：{transcript}")
            segments.append(header + "\n" + "\n".join(body))

        log.info("video_parsed", source=str(sid) if sid else None, duration_s=round(dur, 1),
                 scenes=len(scenes), scene_detection=used_detection, frames=len(frames),
                 captioned=len(captions), vl_skipped=skipped_vl, asr_windows=len(windows),
                 has_audio=has_audio)

        if not segments:
            return ""
        title = "# 视频解析（场景关键帧 + 语音转写 时序索引）\n" \
                f"> 时长 {_ts(dur)}，共 {len(scenes)} 个场景；每节标注时间码 `[起–止]`，命中可 `t=起始` 深链。\n"
        return (title + "\n" + "\n\n".join(segments)).strip()
    finally:
        shutil.rmtree(work, ignore_errors=True)
