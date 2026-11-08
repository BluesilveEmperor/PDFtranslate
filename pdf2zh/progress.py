"""Unified terminal progress rendering (pip-style rich bar / plain tqdm).

This module is the single place where translation progress is turned into
terminal output.  Translation pipelines report progress through the pure data
class :class:`ProgressInfo`; external consumers (web UI, celery backend)
receive the same object and never depend on how the terminal bar is drawn.

Style selection precedence:
    1. :func:`set_progress_style` — called by the CLI after parsing
       ``--progress-style {rich,plain}``.
    2. ``PDF2ZH_PROGRESS`` environment variable (``rich`` / ``plain`` / ``off``),
       read at import time — lets GUI / script launches without CLI args switch
       styles too.
    3. Default: ``rich``.

The factory :func:`create_renderer` additionally degrades ``rich`` to ``plain``
when the terminal cannot render colors safely (``NO_COLOR`` set or stdout not a
TTY), so redirected logs never contain ANSI escape sequences (FR-005).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import tqdm
from rich.console import Console
from rich.errors import LiveError
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

STYLE_RICH = "rich"
STYLE_PLAIN = "plain"
STYLE_OFF = "off"

# ``tqdm`` is accepted as an alias of ``plain`` everywhere for convenience.
_PLAIN_ALIASES = frozenset({"plain", "tqdm"})


def _normalize_style(style: str) -> str:
    style = (style or "").strip().lower()
    if style in _PLAIN_ALIASES:
        return STYLE_PLAIN
    if style == STYLE_RICH:
        return STYLE_RICH
    if style == STYLE_OFF:
        return STYLE_OFF
    raise ValueError(
        f"Unknown progress style {style!r}; expected 'rich', 'plain' or 'off'"
    )


def _style_from_env() -> str:
    raw = (os.environ.get("PDF2ZH_PROGRESS") or "").strip().lower()
    if not raw:
        return STYLE_RICH
    try:
        return _normalize_style(raw)
    except ValueError:
        return STYLE_RICH


_progress_style: str = _style_from_env()


def set_progress_style(style: str) -> None:
    """Override the global progress style (CLI ``--progress-style`` entry)."""
    global _progress_style
    _progress_style = _normalize_style(style)


def get_progress_style() -> str:
    """Return the currently active global progress style."""
    return _progress_style


@dataclass
class ProgressInfo:
    """Pure progress data passed to every callback and renderer.

    Attributes:
        stage:   Machine-readable stage id (e.g. ``page_scan``,
                 ``translate_paragraphs``, ``typeset``).
        current: Current stage progress value.
        total:   Total value of the current stage (``None`` if unknown).
        overall: Overall translation progress in ``0.0–1.0``, monotonic
                 non-decreasing across stages (consumed by the web UI and
                 celery backend).
        message: Human-readable description for the bar and web UI.
    """

    stage: str
    current: float | int = 0
    total: Optional[float | int] = None
    overall: float = 0.0
    message: str = ""


def progress_info_from_event(event: dict) -> ProgressInfo:
    """Build a :class:`ProgressInfo` from a babeldoc-style progress event dict.

    babeldoc (and the ``v2_worker`` forwarding it) reports ``overall_progress``
    on a 0–100 scale; it is normalized to the 0.0–1.0 range expected by
    :class:`ProgressInfo`.  Stage fields (``stage_current`` / ``stage_total``)
    are passed through unchanged.
    """
    overall_raw = event.get("overall_progress", 0.0)
    try:
        overall = float(overall_raw)
    except (TypeError, ValueError):
        overall = 0.0
    if overall > 1.0:
        overall = overall / 100.0
    overall = min(max(overall, 0.0), 1.0)
    stage = str(event.get("stage", ""))
    return ProgressInfo(
        stage=stage,
        current=event.get("stage_current", 0),
        total=event.get("stage_total", 0),
        overall=overall,
        message=stage,
    )


@runtime_checkable
class ProgressRenderer(Protocol):
    """What every terminal progress renderer implements.

    Renderers are context managers: ``__exit__`` always finishes and closes the
    display, so cancellation / exception paths leave the terminal clean (no
    ANSI leftovers, cursor restored).
    """

    def start(self, total: Optional[float] = None, message: str = "") -> "ProgressRenderer": ...
    def reset(self, total: Optional[float] = None, message: str = "") -> None: ...
    def update(
        self,
        current: Optional[float] = None,
        total: Optional[float] = None,
        message: Optional[str] = None,
        overall: Optional[float] = None,
    ) -> None: ...
    def advance(self, n: float = 1) -> None: ...
    def finish(self) -> None: ...
    def close(self) -> None: ...
    def __enter__(self) -> "ProgressRenderer": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...


# ``rich`` allows only one live display per console; a second concurrent
# translation (e.g. two GUI browser tabs) must not crash because of it.
_rich_live_active = False


class RichRenderer:
    """Colored multi-stage renderer backed by ``rich.progress.Progress``.

    The column layout matches babeldoc's built-in rich progress bar so all
    translation paths (fast / precise / ``--babeldoc``) look the same.
    Each :meth:`reset` starts a new task line, freezing previous stage lines
    above (pip-like multi-line stage display).
    """

    def __init__(self, console: Optional[Console] = None):
        self._progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        self._task_id = None
        self._current: float = 0
        self._total: Optional[float] = None
        self._closed = False
        self._owns_live = False
        self._degraded = False  # another live display owns the console

    @property
    def current(self) -> float:
        return self._current

    @property
    def total(self) -> Optional[float]:
        return self._total

    def start(
        self, total: Optional[float] = None, message: str = ""
    ) -> "ProgressRenderer":
        global _rich_live_active
        if self._task_id is not None:
            return self
        self._task_id = self._progress.add_task(message or "Progress", total=total)
        self._current = 0
        self._total = total
        try:
            self._progress.start()
            _rich_live_active = True
            self._owns_live = True
        except LiveError:
            # Only one live display may be active at once; degrade silently
            # instead of failing the translation itself.
            self._degraded = True
        return self

    def reset(self, total: Optional[float] = None, message: str = "") -> None:
        """Begin a new stage on its own line; previous stages stay visible."""
        if self._degraded:
            self._current = 0
            self._total = total
            return
        if self._task_id is None or self._closed:
            self.start(total=total, message=message)
            return
        self._task_id = self._progress.add_task(message or "Progress", total=total)
        self._current = 0
        self._total = total

    def update(
        self,
        current: Optional[float] = None,
        total: Optional[float] = None,
        message: Optional[str] = None,
        overall: Optional[float] = None,
    ) -> None:
        if self._degraded or self._task_id is None:
            return
        if current is not None:
            self._current = current
        if total is not None:
            self._total = total
        self._progress.update(
            self._task_id,
            completed=self._current,
            total=self._total,
            description=message or None,
        )

    def advance(self, n: float = 1) -> None:
        if self._degraded or self._task_id is None:
            return
        self._current += n
        self._progress.advance(self._task_id, n)

    def finish(self) -> None:
        # The last update already left the bar in its final state; rich keeps
        # the last frame rendered after stop(), so nothing to do here.
        pass

    def close(self) -> None:
        global _rich_live_active
        if self._closed:
            return
        self._closed = True
        self._progress.stop()
        if self._owns_live:
            _rich_live_active = False
            self._owns_live = False

    def __enter__(self) -> "ProgressRenderer":
        if self._task_id is None:
            self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.finish()
        self.close()


class TqdmRenderer:
    """Plain single-line renderer wrapping :mod:`tqdm` (fallback style)."""

    def __init__(self):
        self._bar: Optional[tqdm.tqdm] = None

    def _ensure_bar(
        self, total: Optional[float] = None, message: str = ""
    ) -> tqdm.tqdm:
        if self._bar is None:
            # Keep the exact tqdm configuration previously used inline in
            # high_level.translate_patch so the fallback looks unchanged.
            self._bar = tqdm.tqdm(
                total=total, mininterval=0, disable=False, dynamic_ncols=True
            )
            if message:
                self._bar.set_description(message)
        return self._bar

    @property
    def current(self) -> float:
        return self._bar.n if self._bar is not None else 0

    @property
    def total(self) -> Optional[float]:
        return self._bar.total if self._bar is not None else None

    def start(
        self, total: Optional[float] = None, message: str = ""
    ) -> "ProgressRenderer":
        self._ensure_bar(total, message)
        return self

    def reset(self, total: Optional[float] = None, message: str = "") -> None:
        bar = self._ensure_bar()
        if total is not None:
            bar.reset(total=total)
        if message:
            bar.set_description(message)

    def update(
        self,
        current: Optional[float] = None,
        total: Optional[float] = None,
        message: Optional[str] = None,
        overall: Optional[float] = None,
    ) -> None:
        bar = self._ensure_bar()
        if total is not None and total != bar.total:
            bar.reset(total=total)
        if current is not None:
            delta = current - bar.n
            if delta:
                bar.update(delta)
        if message:
            bar.set_description(message)

    def advance(self, n: float = 1) -> None:
        self._ensure_bar().update(n)

    def finish(self) -> None:
        pass  # tqdm closes on close(); no forced 100% jump

    def close(self) -> None:
        if self._bar is not None:
            self._bar.close()
            self._bar = None

    def __enter__(self) -> "ProgressRenderer":
        self._ensure_bar()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.finish()
        self.close()


class NullRenderer:
    """Silent renderer — tracks progress state but prints nothing."""

    def __init__(self):
        self._current: float = 0
        self._total: Optional[float] = None

    @property
    def current(self) -> float:
        return self._current

    @property
    def total(self) -> Optional[float]:
        return self._total

    def start(
        self, total: Optional[float] = None, message: str = ""
    ) -> "ProgressRenderer":
        self._current = 0
        self._total = total
        return self

    def reset(self, total: Optional[float] = None, message: str = "") -> None:
        self._current = 0
        self._total = total

    def update(
        self,
        current: Optional[float] = None,
        total: Optional[float] = None,
        message: Optional[str] = None,
        overall: Optional[float] = None,
    ) -> None:
        if current is not None:
            self._current = current
        if total is not None:
            self._total = total

    def advance(self, n: float = 1) -> None:
        self._current += n

    def finish(self) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self) -> "ProgressRenderer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.finish()
        self.close()


def _stdout_is_tty() -> bool:
    stdout = sys.stdout
    if stdout is None:
        return False
    try:
        return bool(stdout.isatty())
    except (AttributeError, ValueError):
        return False


def create_renderer() -> ProgressRenderer:
    """Create a renderer according to the global style + terminal capabilities.

    Degradation rules (FR-005):
      - ``plain`` / ``off`` styles are returned as-is;
      - ``rich`` degrades to ``TqdmRenderer`` when ``NO_COLOR`` is set, when
        stdout is not a TTY (redirected / dumb terminal) or when another rich
        live display already owns the console (concurrent translation).
    """
    style = get_progress_style()
    if style == STYLE_PLAIN:
        return TqdmRenderer()
    if style == STYLE_OFF:
        return NullRenderer()
    if (
        _rich_live_active
        or "NO_COLOR" in os.environ
        or not _stdout_is_tty()
    ):
        return TqdmRenderer()
    return RichRenderer()
