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
# Bundled mode (portable builds): pdf2zh_next and its deps pre-installed here
# at build time (uv pip install --target). No venv/pip needed at runtime —
# the embeddable runtime ships without venv/ensurepip.
_BUNDLED_PACKAGES_DIR = Path(__file__).resolve().parent / "_precise_packages"


def _venv_python() -> str:
    """Return the path to the venv's Python interpreter."""
    if sys.platform == "win32":
        return str(_VENV_DIR / "Scripts" / "python.exe")
    return str(_VENV_DIR / "bin" / "python")


def _runtime_python() -> str:
    """Return a usable interpreter to launch the worker subprocess.

    In portable builds (PyStand) sys.executable points at pdf2zh.exe, which
    would re-run the launcher script; use the bundled runtime python instead.
    """
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.suffix.lower() == ".exe" and (
        not exe.name.lower().startswith("python")
    ):
        candidate = exe.parent / "runtime" / "python.exe"
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _worker_cwd() -> Path:
    """Working directory for the worker subprocess."""
    if _BUNDLED_PACKAGES_DIR.is_dir() and (_BUNDLED_PACKAGES_DIR / "pdf2zh_next").is_dir():
        return Path(__file__).resolve().parent
    return _SUBMODULE_DIR


_BITSTREAM_SHIM = (
    "try:\n"
    "    from bitstring import BitStream  # noqa: F401\n"
    "except ImportError:\n"
    "    from bitstring import BitArray\n"
    "    import bitstring as _bitstring\n"
    "    _bitstring.BitStream = BitArray\n"
)


def _worker_command() -> list[str]:
    """Build the command launching v2_worker.py in the isolated environment.

    - venv mode: run with the venv interpreter directly.
    - bundled mode: run with the runtime interpreter and inject the bundled
      packages dir via sys.path (a bootstrap -c script is required because
      the embeddable runtime's ._pth ignores PYTHONPATH).
    """
    if _BUNDLED_PACKAGES_DIR.is_dir() and (_BUNDLED_PACKAGES_DIR / "pdf2zh_next").is_dir():
        worker = str(_WORKER_SCRIPT)
        bootstrap = (
            "import sys\n"
            "sys.path.insert(0, r'{pkg_dir}')\n"
            # bitstring>=4 移除了 BitStream，babeldoc 需要；与构建期
            # sitecustomize.py 兼容层等价（embed 运行时无法写死该文件）
            "try:\n"
            "    from bitstring import BitStream  # noqa: F401\n"
            "except ImportError:\n"
            "    import bitstring as _bitstring\n"
            "    _bitstring.BitStream = _bitstring.BitArray\n"
            "exec(compile(open(r'{worker}', encoding='utf-8').read(), "
            "r'{worker}', 'exec'))"
        ).format(pkg_dir=_BUNDLED_PACKAGES_DIR, worker=worker)
        return [_runtime_python(), "-c", bootstrap]
    return [_venv_python(), str(_WORKER_SCRIPT)]


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
            if self._bundled_mode():
                py = _runtime_python()
                code = (
                    "import sys; sys.path.insert(0, r'{pkg}'); "
                    "import pdf2zh_next; print(pdf2zh_next.__version__)"
                ).format(pkg=_BUNDLED_PACKAGES_DIR)
            else:
                py = _venv_python()
                code = "import pdf2zh_next; print(pdf2zh_next.__version__)"
            result = subprocess.run(
                [py, "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    def is_available(self) -> bool:
        """Check if bundled packages, submodule+venv, are initialized."""
        if self._bundled_mode():
            return True
        return (
            _SUBMODULE_DIR.is_dir()
            and (_SUBMODULE_DIR / "pyproject.toml").exists()
            and Path(_venv_python()).exists()
        )

    def _bundled_mode(self) -> bool:
        """True when pdf2zh_next was pre-installed into _precise_packages."""
        return (_BUNDLED_PACKAGES_DIR / "pdf2zh_next").is_dir()

    def ensure_venv(self) -> None:
        """Create venv and install pdf2zh_next if not already set up."""
        if self._bundled_mode():
            return

        if (
            not _SUBMODULE_DIR.is_dir()
            or not (_SUBMODULE_DIR / "pyproject.toml").exists()
        ):
            raise RuntimeError(
                "Precise kernel is not available in this installation. "
                "Options: (1) switch to the 'fast' translation mode; "
                "(2) in a dev checkout run: git submodule update --init "
                "pdf2zh/kernel/PDFMathTranslate-next.git, then set up the "
                "venv. Expected path: "
                f"{_SUBMODULE_DIR}"
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
        try:
            # 依赖较重（babeldoc/onnxruntime 等），慢网络下远超 5 分钟；
            # pip 幂等可重跑，超时后给用户可操作的提示
            subprocess.run(
                [_venv_python(), "-m", "pip", "install", "-e", str(_SUBMODULE_DIR)],
                check=True,
                timeout=1800,
                cwd=str(_SUBMODULE_DIR),
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                "Precise kernel setup timed out while installing pdf2zh_next "
                "(network may be slow). Retry switching to 'precise' mode; "
                "already-downloaded packages are cached and the retry resumes."
            ) from e

        # bitstring>=4 移除了 BitStream，babeldoc 依赖它；
        # 与 build.sh 注入主 site-packages 的兼容层一致
        self._write_bitstream_shim()

        logger.info("Precise kernel venv ready.")

    def _write_bitstream_shim(self) -> None:
        """Write sitecustomize.py BitStream shim into the venv site-packages."""
        import sysconfig

        site_dir = Path(
            sysconfig.get_path("purelib", vars={"base": str(_VENV_DIR)})
        )
        try:
            site_dir.mkdir(parents=True, exist_ok=True)
            (site_dir / "sitecustomize.py").write_text(
                _BITSTREAM_SHIM, encoding="utf-8"
            )
        except OSError as e:
            logger.warning("Failed to write BitStream shim: %s", e)

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
        if self._bundled_mode():
            env["PYTHONPATH"] = str(_BUNDLED_PACKAGES_DIR)
        else:
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

        cmd = _worker_command()
        logger.info("Starting precise kernel subprocess: %s", " ".join(cmd))

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(_worker_cwd()),
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

        cmd = _worker_command()
        cmd_async = list(cmd)
        proc = await asyncio.create_subprocess_exec(
            *cmd_async,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_worker_cwd()),
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
