"""Precise kernel adapter — runs pdf2zh_next in an isolated subprocess/venv."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from pdf2zh.kernel.v2_bridge import request_to_cli_args, request_to_env
from pdf2zh.kernel.protocol import TranslateRequest, TranslateResult
from pdf2zh.progress import (
    ProgressInfo,
    create_renderer,
    progress_info_from_event,
)

logger = logging.getLogger(__name__)

# Resolve paths relative to the kernel package directory
_SUBMODULE_DIR = Path(__file__).resolve().parent / "PDFMathTranslate-next.git"
_VENV_DIR = _SUBMODULE_DIR / ".venv"
_WORKER_SCRIPT = Path(__file__).resolve().parent / "v2_worker.py"


def _venv_python() -> str:
    """Return the path to the venv's Python interpreter."""
    if sys.platform == "win32":
        return str(_VENV_DIR / "Scripts" / "python.exe")
    return str(_VENV_DIR / "bin" / "python")


class _WorkerProgressDispatcher:
    """Parent-side progress dispatcher for v2_worker stderr events.

    v2_worker forwards babeldoc progress events as JSON lines on stderr
    (progress_start / progress_update / progress_end).  The subprocess's own
    rich live output cannot pass through the stderr pipe safely (multi-line
    ANSI would be split per line), so the parent renders the progress bar
    here and forwards the normalized :class:`ProgressInfo` to the registered
    callback (GUI web progress / celery state).
    """

    _PROGRESS_EVENT_TYPES = ("progress_start", "progress_update", "progress_end")

    def __init__(self, callback: Any = None) -> None:
        self._callback = callback
        self._renderer = create_renderer()
        self._started = False

    def process_line(self, raw_line: str, stderr_lines: list[str]) -> None:
        """Handle one stderr line: progress event, other JSON, or plain log."""
        line = raw_line.strip()
        if not line:
            return
        stderr_lines.append(line)
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            print(line, file=sys.stderr, flush=True)
            return
        if not isinstance(event, dict) or not self._dispatch(event):
            # 非进度 JSON（如 error 事件）与普通日志行原样透传到父进程 stderr
            print(line, file=sys.stderr, flush=True)

    def _start_or_reset(self, total: Optional[float], message: str) -> None:
        if not self._started:
            self._renderer.start(total=total, message=message)
            self._started = True
        else:
            # 各阶段分行显示：前一阶段定格，新阶段另起一行
            self._renderer.reset(total=total, message=message)

    def _dispatch(self, event: dict) -> bool:
        """Route one decoded event; returns False for non-progress events."""
        event_type = event.get("type", "")
        if event_type not in self._PROGRESS_EVENT_TYPES:
            return False
        info: ProgressInfo = progress_info_from_event(event)
        total = info.total or None
        if event_type == "progress_start":
            self._start_or_reset(total, info.message)
        elif event_type == "progress_update":
            if not self._started:
                self._start_or_reset(total, info.message)
            self._renderer.update(
                current=info.current, total=info.total, message=info.message
            )
        else:  # progress_end
            self._renderer.update(
                current=max(info.current, info.total),
                total=info.total,
                message=info.message,
            )
        if self._callback:
            self._callback(info)
        return True

    def close(self) -> None:
        self._renderer.close()


class PreciseKernel:
    """Kernel adapter for pdf2zh_next, running in a subprocess with isolated deps."""

    @property
    def name(self) -> str:
        return "precise"

    @property
    def version(self) -> str:
        if not self.is_available():
            return "unknown"
        try:
            result = subprocess.run(
                [
                    _venv_python(),
                    "-c",
                    "import pdf2zh_next; print(pdf2zh_next.__version__)",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(_SUBMODULE_DIR),
            )
            return result.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    def is_available(self) -> bool:
        """Check if submodule exists and venv is initialized."""
        return (
            _SUBMODULE_DIR.is_dir()
            and (_SUBMODULE_DIR / "pyproject.toml").exists()
            and Path(_venv_python()).exists()
        )

    def ensure_venv(self) -> None:
        """Create venv and install pdf2zh_next if not already set up."""
        if (
            not _SUBMODULE_DIR.is_dir()
            or not (_SUBMODULE_DIR / "pyproject.toml").exists()
        ):
            raise RuntimeError(
                "PDFMathTranslate-next submodule not found. "
                "Run: git submodule update --init pdf2zh/kernel/PDFMathTranslate-next.git"
            )

        venv_exists = Path(_venv_python()).exists()

        if venv_exists and self._package_importable():
            return

        if not venv_exists:
            logger.info("Creating precise kernel venv...")
            subprocess.run(
                [sys.executable, "-m", "venv", str(_VENV_DIR)],
                check=True,
                timeout=60,
            )

        logger.info("Installing pdf2zh_next into venv...")
        subprocess.run(
            [_venv_python(), "-m", "pip", "install", "-e", str(_SUBMODULE_DIR)],
            check=True,
            timeout=300,
            cwd=str(_SUBMODULE_DIR),
        )

        logger.info("Precise kernel venv ready.")

    def _package_importable(self) -> bool:
        """Check if pdf2zh_next can be imported in the venv."""
        try:
            result = subprocess.run(
                [_venv_python(), "-c", "import pdf2zh_next"],
                capture_output=True,
                timeout=30,
                cwd=str(_SUBMODULE_DIR),
                env={**os.environ, "PYTHONPATH": str(_SUBMODULE_DIR)},
            )
            return result.returncode == 0
        except Exception:
            return False

    def _build_subprocess_env(self, request: TranslateRequest) -> dict[str, str]:
        """Build environment for the subprocess with PDF2ZH_ prefixed vars."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_SUBMODULE_DIR)
        env.update(request_to_env(request))
        return env

    def translate(
        self,
        request: TranslateRequest,
        callback: Any = None,
        cancellation_event: Optional[asyncio.Event] = None,
    ) -> list[TranslateResult]:
        self.ensure_venv()

        cli_args = request_to_cli_args(request)
        input_json = json.dumps(cli_args)
        env = self._build_subprocess_env(request)

        cmd = [_venv_python(), str(_WORKER_SCRIPT)]
        logger.info("Starting precise kernel subprocess: %s", " ".join(cmd))

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(_SUBMODULE_DIR),
            env=env,
        )

        stderr_lines: list[str] = []
        dispatcher = _WorkerProgressDispatcher(callback)
        try:
            assert proc.stdin is not None
            assert proc.stderr is not None
            assert proc.stdout is not None
            proc.stdin.write(input_json)
            proc.stdin.close()

            for line in proc.stderr:
                dispatcher.process_line(line, stderr_lines)

            stdout = proc.stdout.read()
            proc.wait()

        except Exception:
            proc.kill()
            raise
        finally:
            dispatcher.close()

        if proc.returncode != 0:
            detail = "\n".join(stderr_lines[-20:]) if stderr_lines else "(no stderr)"
            raise RuntimeError(
                f"Precise kernel subprocess failed (exit {proc.returncode}):\n{detail}"
            )

        try:
            result_data = json.loads(stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON from worker: {stdout[:200]}")

        results = []
        for r in result_data.get("results", []):
            results.append(
                TranslateResult(
                    mono_pdf=Path(r["mono_pdf"]) if r.get("mono_pdf") else None,
                    dual_pdf=Path(r["dual_pdf"]) if r.get("dual_pdf") else None,
                    time_cost=result_data.get("time_cost", 0.0),
                )
            )
        return results

    async def translate_async(
        self,
        request: TranslateRequest,
        callback: Any = None,
        cancellation_event: Optional[asyncio.Event] = None,
    ) -> list[TranslateResult]:
        self.ensure_venv()

        cli_args = request_to_cli_args(request)
        input_json = json.dumps(cli_args)
        env = self._build_subprocess_env(request)

        proc = await asyncio.create_subprocess_exec(
            _venv_python(),
            str(_WORKER_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_SUBMODULE_DIR),
            env=env,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        assert proc.stderr is not None

        dispatcher = _WorkerProgressDispatcher(callback)
        stderr_lines: list[str] = []
        try:
            proc.stdin.write(input_json.encode())
            await proc.stdin.drain()
            proc.stdin.close()

            # 逐行流式消费 stderr：进度事件实时渲染，非进度行原样透传
            async for line in proc.stderr:
                dispatcher.process_line(line, stderr_lines)

            stdout_bytes = await proc.stdout.read()
            await proc.wait()
        except Exception:
            proc.kill()
            raise
        finally:
            dispatcher.close()
        stdout = stdout_bytes.decode()

        if proc.returncode != 0:
            detail = "\n".join(stderr_lines[-20:]) if stderr_lines else "(no stderr)"
            raise RuntimeError(
                f"Precise kernel subprocess failed (exit {proc.returncode}):\n{detail}"
            )

        try:
            result_data = json.loads(stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON from worker: {stdout[:200]}")

        results = []
        for r in result_data.get("results", []):
            results.append(
                TranslateResult(
                    mono_pdf=Path(r["mono_pdf"]) if r.get("mono_pdf") else None,
                    dual_pdf=Path(r["dual_pdf"]) if r.get("dual_pdf") else None,
                    time_cost=result_data.get("time_cost", 0.0),
                )
            )
        return results


def setup_precise_cli() -> None:
    """CLI entry point: provision the precise kernel venv."""
    logging.basicConfig(level=logging.INFO)
    PreciseKernel().ensure_venv()
