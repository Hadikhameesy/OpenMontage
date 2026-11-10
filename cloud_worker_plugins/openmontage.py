"""Free FFmpeg assembly adapter for uploaded OpenMontage media."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

MAX_INPUTS = 12
MAX_DURATION = 60


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise RuntimeError("ffmpeg_failed: " + (result.stderr or "unknown")[-1000:])


def _make_clip(source: Path, target: Path, kind: str, width: int, height: int, seconds: int) -> None:
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
          f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
          "setsar=1,fps=24,format=yuv420p")
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if kind == "image":
        args = common + ["-loop", "1", "-framerate", "24", "-i", str(source)]
    else:
        args = common + ["-i", str(source)]
    _run(args + ["-t", str(seconds), "-vf", vf, "-an", "-c:v", "libx264",
                 "-preset", "ultrafast", "-crf", "25", "-movflags", "+faststart", str(target)])


def execute(*, job: dict[str, Any], project: dict[str, Any], report_progress,
            stop_event, worker_client) -> dict[str, Any]:
    """Create an MP4 from user-uploaded images/videos and optional audio; no paid AI calls."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg_not_installed")
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    try:
        duration = max(5, min(MAX_DURATION, int(payload.get("duration_seconds", 30))))
    except (TypeError, ValueError):
        duration = 30
    ratio = str(project.get("aspect_ratio") or "16:9")
    sizes = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (960, 960), "4:5": (864, 1080)}
    width, height = sizes.get(ratio, sizes["16:9"])
    artifacts = worker_client.input_artifacts(job)[:MAX_INPUTS]
    if not artifacts:
        raise ValueError("upload_media_required")

    with tempfile.TemporaryDirectory(prefix="openmontage-") as tmp:
        root = Path(tmp)
        clips: list[Path] = []
        audio: Path | None = None
        for index, item in enumerate(artifacts):
            if stop_event.is_set():
                raise InterruptedError("job_cancel_requested")
            content_type = str(item.get("content_type") or "").lower()
            suffix = Path(str(item.get("object_path") or "")).suffix.lower()
            suffix = suffix if suffix.startswith(".") and len(suffix) <= 8 else ""
            source = worker_client.download_artifact(item, str(root / f"input_{index:02d}{suffix}"))
            if content_type.startswith("audio/"):
                if audio is None:
                    audio = source
                continue
            if content_type.startswith("image/") or suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                kind = "image"
            elif content_type.startswith("video/") or suffix in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}:
                kind = "video"
            else:
                continue
            target = root / f"clip_{len(clips):02d}.mp4"
            seconds = max(2, min(12, duration // max(1, min(6, len(artifacts)))))
            _make_clip(source, target, kind, width, height, seconds)
            clips.append(target)
            report_progress(min(70, 10 + int(55 * len(clips) / max(1, len(artifacts)))),
                            "assembling", f"Prepared clip {len(clips)}")

        if not clips:
            raise ValueError("no_supported_image_or_video_inputs")
        if stop_event.is_set():
            raise InterruptedError("job_cancel_requested")
        concat = root / "concat.txt"
        concat.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
        output = root / "openmontage-output.mp4"
        base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat)]
        report_progress(78, "rendering", "Composing MP4")
        if audio:
            _run(base + ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
                         "-t", str(duration), "-movflags", "+faststart", str(output)])
        else:
            _run(base + ["-map", "0:v:0", "-an", "-c:v", "copy", "-t", str(duration),
                         "-movflags", "+faststart", str(output)])
        if not output.is_file() or output.stat().st_size < 1024:
            raise RuntimeError("render_output_invalid")
        report_progress(92, "uploading", "Uploading MP4")
        artifact = worker_client.upload_artifact(job, str(output), artifact_type="output",
                                                 content_type="video/mp4")
        report_progress(99, "finalizing", "Video uploaded")
        return {"mode": "free_media_assembly",
                "message": "Rendered uploaded media with FFmpeg; no paid AI provider was called.",
                "filename": output.name, "content_type": "video/mp4",
                "size_bytes": output.stat().st_size, "aspect_ratio": ratio,
                "duration_limit_seconds": duration, "clips_used": len(clips),
                "artifact": artifact}
