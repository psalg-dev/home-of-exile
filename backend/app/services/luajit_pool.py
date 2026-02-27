"""LuaJIT pool manager for PathOfBuilding calculation engine.

Manages a pool of persistent LuaJIT subprocess workers that communicate
via stdin/stdout JSON-RPC protocol (POB_API_STDIO mode).

Protocol:
    1. Start: ``luajit HeadlessWrapper.lua --stdio`` with env POB_API_STDIO=1
    2. Ready banner: ``{"ok": true, "ready": true, "version": {...}}``
    3. Commands:  ``{"action": "...", "params": {...}}``
    4. Responses: ``{"ok": true/false, ...}``
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

# Timeout for a single RPC round-trip (seconds)
_RPC_TIMEOUT: float = 15.0

# Max calculations before recycling a worker to avoid memory leaks
_MAX_CALCS_PER_WORKER: int = 500

# Max time to wait for the LuaJIT ready banner on startup (seconds)
_STARTUP_TIMEOUT: float = 60.0

# Stat fields to request from PoB for every calculation
_DEFAULT_STAT_FIELDS: list[str] = [
    "Life",
    "EnergyShield",
    "Armour",
    "Evasion",
    "FireResist",
    "ColdResist",
    "LightningResist",
    "ChaosResist",
    "BlockChance",
    "SpellBlockChance",
    "TotalDPS",
    "FullDPS",
    "CombinedDPS",
    "AverageDamage",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LuaJITWorkerError(Exception):
    """Raised when a LuaJIT worker encounters an error."""


# ---------------------------------------------------------------------------
# Individual worker
# ---------------------------------------------------------------------------


class LuaJITWorker:
    """Manages a single LuaJIT subprocess running HeadlessWrapper.lua.

    Each worker holds state for one loaded build at a time; all operations
    on a worker are serialised with an asyncio.Lock so the caller simply
    acquires-use-releases.

    Args:
        worker_id: Human-readable index for log messages.
        pob_src_dir: Absolute path to the PoB ``src/`` directory.
        luajit_cmd: Executable name or absolute path of the LuaJIT binary.
        max_calcs: Recycle the worker after this many calculations.
    """

    def __init__(
        self,
        worker_id: int,
        pob_src_dir: str,
        luajit_cmd: str,
        max_calcs: int = _MAX_CALCS_PER_WORKER,
    ) -> None:
        """Initialise the worker (does NOT start the subprocess)."""
        self.worker_id = worker_id
        self.pob_src_dir = pob_src_dir
        self.luajit_cmd = luajit_cmd
        self.max_calcs = max_calcs

        self._process: asyncio.subprocess.Process | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._ready: bool = False
        self._num_calcs: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """True when the worker process is running and has announced ready."""
        return (
            self._ready
            and self._process is not None
            and self._process.returncode is None
        )

    @property
    def needs_recycle(self) -> bool:
        """True when the worker should be replaced to prevent memory leaks."""
        return self._num_calcs >= self.max_calcs

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the subprocess and wait for the ready banner.

        Raises:
            LuaJITWorkerError: If HeadlessWrapper.lua is missing, the
                process fails to start, or the ready banner is invalid.
        """
        wrapper = Path(self.pob_src_dir) / "HeadlessWrapper.lua"
        if not wrapper.exists():
            raise LuaJITWorkerError(
                f"Worker {self.worker_id}: HeadlessWrapper.lua not found at "
                f"{wrapper}"
            )

        env = os.environ.copy()
        env["POB_API_STDIO"] = "1"

        logger.info(
            "Worker %d: starting LuaJIT (cmd=%s, cwd=%s)",
            self.worker_id,
            self.luajit_cmd,
            self.pob_src_dir,
        )

        self._process = await asyncio.create_subprocess_exec(
            self.luajit_cmd,
            "HeadlessWrapper.lua",
            "--stdio",
            cwd=self.pob_src_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Read until we get valid JSON (skip any non-JSON stderr noise the
        # PoB engine might have emitted to stdout during initialisation).
        deadline = asyncio.get_event_loop().time() + _STARTUP_TIMEOUT
        banner: dict[str, Any] | None = None

        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            try:
                raw = await asyncio.wait_for(
                    self._process.stdout.readline(),  # type: ignore[union-attr]
                    timeout=remaining,
                )
            except TimeoutError:
                break

            if not raw:
                break

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # Skip non-JSON output (e.g., Lua print statements)
                logger.debug(
                    "Worker %d: skipping non-JSON stdout line: %r",
                    self.worker_id,
                    line,
                )
                continue

            if obj.get("ok") and obj.get("ready"):
                banner = obj
                break
            # Unexpected JSON before ready — keep waiting

        if banner is None:
            await self.stop()
            raise LuaJITWorkerError(
                f"Worker {self.worker_id}: did not receive ready banner "
                f"within {_STARTUP_TIMEOUT}s"
            )

        self._ready = True
        version = banner.get("version") or {}
        logger.info(
            "Worker %d: ready (pob=%s api=%s)",
            self.worker_id,
            version.get("number", "?"),
            version.get("apiVersion", "?"),
        )

    async def stop(self) -> None:
        """Terminate the subprocess gracefully, then kill if necessary."""
        self._ready = False
        if self._process is None:
            return

        proc = self._process
        self._process = None

        if proc.returncode is not None:
            return

        # Ask nicely first
        if proc.stdin and not proc.stdin.is_closing():
            try:
                proc.stdin.write(b'{"action":"quit"}\n')
                await proc.stdin.drain()
            except Exception:
                pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except TimeoutError:
            proc.kill()
        except Exception:
            pass

        logger.info("Worker %d: stopped", self.worker_id)

    # ------------------------------------------------------------------
    # Internal RPC
    # ------------------------------------------------------------------

    async def _call(
        self,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one JSON-RPC command and return the parsed response.

        Args:
            action: Action name understood by API/Server.lua.
            params: Optional parameters dict.

        Returns:
            Parsed JSON response.

        Raises:
            LuaJITWorkerError: On I/O error, broken pipe, or timeout.
        """
        if (
            self._process is None
            or self._process.stdin is None
            or self._process.stdout is None
        ):
            raise LuaJITWorkerError(
                f"Worker {self.worker_id}: process is not running"
            )

        msg: dict[str, Any] = {"action": action}
        if params:
            msg["params"] = params

        line_bytes = (json.dumps(msg, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )

        try:
            self._process.stdin.write(line_bytes)
            await self._process.stdin.drain()

            raw = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=_RPC_TIMEOUT,
            )
        except TimeoutError as exc:
            self._ready = False
            raise LuaJITWorkerError(
                f"Worker {self.worker_id}: RPC timeout on '{action}'"
            ) from exc
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            self._ready = False
            raise LuaJITWorkerError(
                f"Worker {self.worker_id}: I/O error on '{action}': {exc}"
            ) from exc

        if not raw:
            self._ready = False
            raise LuaJITWorkerError(
                f"Worker {self.worker_id}: process closed stdout on '{action}'"
            )

        try:
            response: dict[str, Any] = json.loads(
                raw.decode("utf-8", errors="replace").strip()
            )
        except json.JSONDecodeError as exc:
            raise LuaJITWorkerError(
                f"Worker {self.worker_id}: invalid JSON response for "
                f"'{action}': {raw!r}"
            ) from exc

        return response

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Send a ping and return True if the worker responds correctly.

        Returns:
            True if healthy; False on error.
        """
        try:
            resp = await self._call("ping")
            return bool(resp.get("pong"))
        except LuaJITWorkerError:
            self._ready = False
            return False

    async def calculate(self, build_xml: str) -> dict[str, Any]:
        """Load a build and retrieve calculated stats.

        Args:
            build_xml: Raw PoB XML string.

        Returns:
            Dict with ``stats`` key mapping stat names to numeric values.

        Raises:
            LuaJITWorkerError: On load or stats failure.
        """
        async with self._lock:
            # Load
            load_resp = await self._call(
                "load_build_xml", {"xml": build_xml}
            )
            if not load_resp.get("ok"):
                raise LuaJITWorkerError(
                    f"Worker {self.worker_id}: load_build_xml failed: "
                    f"{load_resp.get('error', 'unknown')}"
                )

            # Stats
            stats_resp = await self._call(
                "get_stats", {"fields": _DEFAULT_STAT_FIELDS}
            )
            if not stats_resp.get("ok"):
                raise LuaJITWorkerError(
                    f"Worker {self.worker_id}: get_stats failed: "
                    f"{stats_resp.get('error', 'unknown')}"
                )

            self._num_calcs += 1
            return {"stats": stats_resp.get("stats", {})}

    async def calculate_with_swap(
        self,
        build_xml: str,
        item_text: str,
        slot_name: str,
    ) -> dict[str, Any]:
        """Load a build, record baseline, swap an item, record modified stats.

        Args:
            build_xml: Original PoB XML string.
            item_text: PoE item text format for the new item.
            slot_name: Equipment slot to swap (e.g. ``'Helmet'``,
                ``'Weapon 1'``).

        Returns:
            Dict with ``baseline``, ``modified`` stats and ``item`` info.

        Raises:
            LuaJITWorkerError: On any operation failure.
        """
        async with self._lock:
            # Load original
            load_resp = await self._call(
                "load_build_xml", {"xml": build_xml}
            )
            if not load_resp.get("ok"):
                raise LuaJITWorkerError(
                    f"load_build_xml failed: "
                    f"{load_resp.get('error', 'unknown')}"
                )

            # Baseline
            base_resp = await self._call(
                "get_stats", {"fields": _DEFAULT_STAT_FIELDS}
            )
            if not base_resp.get("ok"):
                raise LuaJITWorkerError(
                    f"get_stats (baseline) failed: "
                    f"{base_resp.get('error', 'unknown')}"
                )
            baseline = base_resp.get("stats", {})

            # Swap item
            swap_resp = await self._call(
                "add_item_text",
                {"text": item_text, "slotName": slot_name},
            )
            if not swap_resp.get("ok"):
                raise LuaJITWorkerError(
                    f"add_item_text failed: "
                    f"{swap_resp.get('error', 'unknown')}"
                )

            # Modified
            mod_resp = await self._call(
                "get_stats", {"fields": _DEFAULT_STAT_FIELDS}
            )
            if not mod_resp.get("ok"):
                raise LuaJITWorkerError(
                    f"get_stats (modified) failed: "
                    f"{mod_resp.get('error', 'unknown')}"
                )
            modified = mod_resp.get("stats", {})

            self._num_calcs += 1
            return {
                "baseline": baseline,
                "modified": modified,
                "item": swap_resp.get("item", {}),
            }


# ---------------------------------------------------------------------------
# Pool manager
# ---------------------------------------------------------------------------


class LuaJITPoolManager:
    """Manages a pool of persistent LuaJIT workers.

    Workers are pre-started on ``startup()`` and kept alive across requests.
    Idle workers are tracked in an asyncio.Queue; each request acquires one,
    uses it, and releases it back.  Crashed workers are restarted
    automatically behind the scenes.

    If LuaJIT or HeadlessWrapper.lua are missing the pool starts in a
    degraded "unavailable" mode rather than crashing the server.

    Args:
        pool_size: Number of parallel workers to maintain.
        pob_src_dir: Path to the PoB ``src/`` directory.
        luajit_cmd: LuaJIT executable name or full path.
        max_calcs_per_worker: Recycle workers after this many calculations.
    """

    def __init__(
        self,
        pool_size: int,
        pob_src_dir: str,
        luajit_cmd: str = "luajit",
        max_calcs_per_worker: int = _MAX_CALCS_PER_WORKER,
    ) -> None:
        """Initialise the pool (does NOT start workers)."""
        self.pool_size = pool_size
        self.pob_src_dir = pob_src_dir
        self.luajit_cmd = luajit_cmd
        self.max_calcs_per_worker = max_calcs_per_worker

        self._workers: list[LuaJITWorker] = []
        # Queue holds indices into self._workers for idle workers
        self._idle: asyncio.Queue[int] = asyncio.Queue()
        self._available: bool = False
        # Keep strong references to fire-and-forget restart tasks
        self._background_tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """True if at least one worker is running."""
        return self._available

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Start all workers.

        Logs errors and marks pool unavailable on failure rather than raising,
        to allow the API server to start even without LuaJIT.
        """
        if not shutil.which(self.luajit_cmd):
            logger.error(
                "LuaJIT binary '%s' not found on PATH. "
                "Calculation endpoints will return 503.",
                self.luajit_cmd,
            )
            return

        wrapper = Path(self.pob_src_dir) / "HeadlessWrapper.lua"
        if not wrapper.exists():
            logger.error(
                "HeadlessWrapper.lua not found at '%s'. "
                "Calculation endpoints will return 503.",
                wrapper,
            )
            return

        logger.info(
            "LuaJIT pool: starting %d worker(s) (cmd=%s, src=%s)",
            self.pool_size,
            self.luajit_cmd,
            self.pob_src_dir,
        )

        started = 0
        for i in range(self.pool_size):
            worker = LuaJITWorker(
                worker_id=i,
                pob_src_dir=self.pob_src_dir,
                luajit_cmd=self.luajit_cmd,
                max_calcs=self.max_calcs_per_worker,
            )
            try:
                await worker.start()
                self._workers.append(worker)
                self._idle.put_nowait(i)
                started += 1
            except LuaJITWorkerError as exc:
                logger.error("Worker %d failed to start: %s", i, exc)

        if started > 0:
            self._available = True
            logger.info(
                "LuaJIT pool ready: %d/%d workers started.",
                started,
                self.pool_size,
            )
        else:
            logger.error(
                "LuaJIT pool: 0 workers started. "
                "Calculation endpoints will return 503."
            )

    async def shutdown(self) -> None:
        """Stop all workers gracefully."""
        self._available = False
        for worker in self._workers:
            await worker.stop()
        self._workers.clear()
        logger.info("LuaJIT pool shut down.")

    # ------------------------------------------------------------------
    # Worker management helpers
    # ------------------------------------------------------------------

    async def _acquire(self) -> tuple[int, LuaJITWorker]:
        """Acquire an idle worker, blocking until one is free.

        Returns:
            ``(worker_idx, worker)`` tuple.

        Raises:
            LuaJITWorkerError: If no worker becomes available before timeout.
        """
        try:
            idx = await asyncio.wait_for(
                self._idle.get(),
                timeout=_RPC_TIMEOUT,
            )
        except TimeoutError as exc:
            raise LuaJITWorkerError(
                "No idle LuaJIT worker available within "
                f"{_RPC_TIMEOUT:.0f}s timeout"
            ) from exc
        return idx, self._workers[idx]

    def _release(self, idx: int) -> None:
        """Return a worker to the idle queue."""
        self._idle.put_nowait(idx)

    async def _restart_worker(self, idx: int) -> None:
        """Restart a specific worker in-place.

        Args:
            idx: Index of the worker to restart.
        """
        logger.warning("LuaJIT pool: restarting worker %d", idx)
        old = self._workers[idx]
        await old.stop()

        new_worker = LuaJITWorker(
            worker_id=idx,
            pob_src_dir=self.pob_src_dir,
            luajit_cmd=self.luajit_cmd,
            max_calcs=self.max_calcs_per_worker,
        )
        try:
            await new_worker.start()
            logger.info("Worker %d restarted successfully.", idx)
        except LuaJITWorkerError as exc:
            logger.error("Worker %d restart failed: %s", idx, exc)
        self._workers[idx] = new_worker

    # ------------------------------------------------------------------
    # Public calculation API
    # ------------------------------------------------------------------

    async def calculate(self, build_xml: str) -> dict[str, Any]:
        """Calculate stats for a build XML using an available worker.

        Args:
            build_xml: PoB XML string.

        Returns:
            Dict containing ``stats`` key with numeric stat values.

        Raises:
            LuaJITWorkerError: On calculation failure or timeout.
        """
        idx, worker = await self._acquire()

        try:
            # Proactively recycle if needed
            if worker.needs_recycle or not worker.is_ready:
                await self._restart_worker(idx)
                worker = self._workers[idx]

            result = await worker.calculate(build_xml)
            return result
        except LuaJITWorkerError:
            # Fire-and-forget restart so the worker index stays valid
            task = asyncio.create_task(self._restart_worker(idx))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            raise
        finally:
            self._release(idx)

    async def calculate_swap(
        self,
        build_xml: str,
        item_text: str,
        slot_name: str,
    ) -> dict[str, Any]:
        """Calculate stats with one item swapped in a specific slot.

        Args:
            build_xml: Original PoB XML.
            item_text: New item in PoE item-text format.
            slot_name: Equipment slot (e.g. ``'Helmet'``, ``'Body Armour'``).

        Returns:
            Dict with ``baseline``, ``modified``, and ``item`` keys.

        Raises:
            LuaJITWorkerError: On failure.
        """
        idx, worker = await self._acquire()

        try:
            if worker.needs_recycle or not worker.is_ready:
                await self._restart_worker(idx)
                worker = self._workers[idx]

            result = await worker.calculate_with_swap(
                build_xml, item_text, slot_name
            )
            return result
        except LuaJITWorkerError:
            task = asyncio.create_task(self._restart_worker(idx))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            raise
        finally:
            self._release(idx)

    async def calculate_swap_batch(
        self,
        build_xml: str,
        swaps: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Calculate multiple item swaps in parallel across the pool.

        Each swap is dispatched to any available worker concurrently.

        Args:
            build_xml: Original PoB XML (shared across all swaps).
            swaps: List of ``{item_text, slot_name}`` dicts.

        Returns:
            List of results in the same order as ``swaps``.  Failed swaps
            include an ``error`` key instead of stats.
        """
        tasks = [
            self.calculate_swap(build_xml, s["item_text"], s["slot_name"])
            for s in swaps
        ]
        results: list[Any] = await asyncio.gather(
            *tasks, return_exceptions=True
        )
        return [
            r if not isinstance(r, Exception) else {"error": str(r)}
            for r in results
        ]

    async def health_check(self) -> dict[str, Any]:
        """Ping all workers and return pool health information.

        Returns:
            Dict with ``available``, ``total_workers``, ``healthy_workers``,
            and ``pool_size`` keys.
        """
        healthy = 0
        for worker in self._workers:
            try:
                if await worker.ping():
                    healthy += 1
            except Exception:
                pass
        return {
            "available": self._available,
            "pool_size": self.pool_size,
            "total_workers": len(self._workers),
            "healthy_workers": healthy,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_pool: LuaJITPoolManager | None = None


def get_pool() -> LuaJITPoolManager:
    """Return the global pool singleton.

    Raises:
        RuntimeError: If the pool has not been initialised yet.
    """
    if _pool is None:
        raise RuntimeError(
            "LuaJIT pool not initialised. "
            "Call init_pool() during application startup."
        )
    return _pool


def init_pool(
    pool_size: int,
    pob_src_dir: str,
    luajit_cmd: str = "luajit",
) -> LuaJITPoolManager:
    """Create and register the global pool singleton.

    Should be called exactly once during application startup.

    Args:
        pool_size: Number of workers.
        pob_src_dir: PoB ``src/`` directory path.
        luajit_cmd: LuaJIT binary command.

    Returns:
        The newly created :class:`LuaJITPoolManager`.
    """
    global _pool
    _pool = LuaJITPoolManager(
        pool_size=pool_size,
        pob_src_dir=pob_src_dir,
        luajit_cmd=luajit_cmd,
    )
    return _pool
