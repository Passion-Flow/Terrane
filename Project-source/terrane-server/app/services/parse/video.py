"""视频 AI 解析（自研流水线,纯 DashScope,无需公网上传):

ffmpeg 抽关键帧 + 抽音轨 → 帧 base64 发 qwen-vl-plus 得画面描述、音轨 base64 发 qwen3-asr-flash 得转录
→ 合并成结构化 Markdown(转录 + 带时间戳的画面描述)→ 并入既有切片/嵌入/RAG/图谱。
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
_SCENE_THRESHOLD = 0.30          # 场景突变阈值(越小越敏感)
_AUDIO_LIMIT_BYTES = 9_000_000   # ASR 单次上限保护(超长音轨截断,长视频分段为后续增强)
_PTS = re.compile(rb"pts_time:([0-9.]+)")


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return proc.returncode or 0, out, err


async def _scene_keyframes(path: str, work: str, cap: int) -> list[tuple[float, str]]:
    """ffmpeg 场景切分抽关键帧(取画面突变点)+ 从 showinfo 解析每帧时间戳。返回 [(秒, 文件)] 时间序。"""
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
    """解析视频 → Markdown(语音转录 + 场景关键帧描述,带真实时间戳)。无模型渠道则返回空串。

    场景化(对标 SceneRAG/VideoRAG):按画面突变点取关键帧而非固定间隔,更贴合内容章节;
    无场景突变(静态视频)则回退固定间隔。"""
    dur = await _duration(path)
    work = tempfile.mkdtemp(prefix="trn_vid_")
    audio = os.path.join(work, "a.wav")
    try:
        # 场景关键帧 + 抽音轨(并行)
        scene, _audio_res = await asyncio.gather(
            _scene_keyframes(path, work, _MAX_FRAMES),
            _run("ffmpeg", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", audio),
        )
        # 回退:无场景突变 → 固定间隔抽帧
        if not scene:
            n = min(_MAX_FRAMES, max(2, int(dur // 10) or 2))
            interval = max(1.0, dur / n) if dur else 5.0
            await _run("ffmpeg", "-y", "-i", path, "-vf", f"fps=1/{interval:.3f}", "-frames:v", str(n),
                       "-q:v", "3", os.path.join(work, "f%02d.jpg"))
            files = sorted(f for f in os.listdir(work) if f.startswith("f") and f.endswith(".jpg"))
            scene = [(i * interval, os.path.join(work, f)) for i, f in enumerate(files)]

        # 转录
        transcript = ""
        if os.path.exists(audio) and 0 < os.path.getsize(audio) <= _AUDIO_LIMIT_BYTES:
            try:
                b = base64.b64encode(open(audio, "rb").read()).decode()
                transcript = (await model_client.asr(db, b)) or ""
            except ModelError as e:
                log.warning("video_asr_failed", error=str(e))

        # 关键帧描述(带真实时间戳)
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
            parts.append("## 视频语音转录\n" + transcript.strip())
        if captions:
            parts.append("## 场景关键帧（按画面突变点）\n" + "\n".join(captions))
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
