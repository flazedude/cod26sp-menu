#!/usr/bin/env python3
"""COD MW4 campaign trainer: in-process freeze of the player health/max integers.

Campaign / offline only. This is a data-only change (no code patching), but the
helper is still an unsigned DLL inside the process; no anti-ban guarantee is possible.

Status: the exact player slot was NOT confirmed. The UI can load known 150/150
player-state slots from health_exact.json when they are still valid, otherwise it
freezes the integer candidate families it can find. Two independent live-fire
tests (freezing every int-150 pair, then every int-100 pair, each rewritten every
2 ms) were still followed by a player death, so the real health field is probably
not an adjacent equal-value int pair. Treat this as a work in progress.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
NATIVE = ROOT / "native"
sys.path.insert(0, str(TOOLS))

from codgod_client import Agent, find_pid, inject_hook  # noqa: E402

DLL = NATIVE / "codgod17.dll"
HEALTH_VALUES = (100, 150)
EXACT_PATH = ROOT / "health_exact.json"
MAX_CANDIDATES = 4000
SCAN_CHUNK = 16 * 1024 * 1024
SCAN_LIMIT = 24 * 1024 * 1024 * 1024


def game_pid() -> int:
    return find_pid("sp26-cod.exe")


def ensure_agent(pid: int) -> Agent:
    agent = Agent(pid)
    try:
        if agent.ping():
            return agent
    except Exception:
        pass
    os.environ["COD_GOD_DLL"] = str(DLL)
    inject_hook(pid, DLL)
    time.sleep(1.5)
    agent = Agent(pid)
    if not agent.ping():
        raise RuntimeError("agent did not respond after injection")
    return agent


def load_exact() -> list[int]:
    try:
        data = json.loads(EXACT_PATH.read_text())
        return [int(x) for x in data.get("hits", [])]
    except Exception:
        return []


def exact_still_valid(agent: Agent, addrs: list[int]) -> bool:
    if not addrs:
        return False
    for addr in addrs:
        data = agent.read(addr, 8)
        if len(data) != 8 or struct.unpack("<ii", data) != (150, 150):
            return False
    return True


def scan_health_candidates(agent: Agent, value: int) -> list[int]:
    """Scan private committed regions for adjacent int pairs equal to value."""
    hits: list[int] = []
    scanned = 0
    stop = False
    for r in agent.regions():
        if stop:
            break
        if r.type != 0x20000 or r.state != 0x1000:
            continue
        if r.protect & 0x100:  # PAGE_GUARD
            continue
        base, size = int(r.base), int(r.size)
        off = 0
        while off < size and len(hits) < MAX_CANDIDATES:
            n = min(SCAN_CHUNK, size - off)
            try:
                found = agent.scan_range_int(base + off, n, value, pair=True)
                hits.extend(int(x) for x in found)
            except Exception:
                pass
            off += n
            scanned += n
            if scanned >= SCAN_LIMIT:
                stop = True
                break
    seen = set()
    out = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:MAX_CANDIDATES]


class Trainer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("COD MW4 Campaign God Mode")
        self.geometry("500x330")
        self.resizable(False, False)
        self.agent: Agent | None = None
        self.pid = 0
        self.frozen = False
        self.candidates: list[int] = []
        self.freeze_value = 150
        self.busy = False
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(300, self.connect)

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Call of Duty: Modern Warfare 4 - Campaign",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frm, text="In-process health freeze - campaign/offline only",
                  foreground="#555").pack(anchor="w", pady=(2, 10))

        self.status = tk.StringVar(value="Looking for sp26-cod.exe...")
        ttk.Label(frm, textvariable=self.status, wraplength=460,
                  justify="left").pack(anchor="w", pady=(0, 10))

        row = ttk.Frame(frm)
        row.pack(fill="x", pady=4)
        self.btn_on = ttk.Button(row, text="Enable God Mode", command=self.enable)
        self.btn_on.pack(side="left", padx=(0, 6))
        self.btn_off = ttk.Button(row, text="Disable", command=self.disable, state="disabled")
        self.btn_off.pack(side="left", padx=(0, 6))
        self.btn_scan = ttk.Button(row, text="Rescan", command=self.rescan)
        self.btn_scan.pack(side="left")

        self.detail = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.detail, wraplength=460,
                  justify="left", foreground="#333").pack(anchor="w", pady=(10, 0))

        warn = (
            "UNCONFIRMED: two live-fire tests with every int-100 and int-150 pair frozen "
            "still ended in death. Use as a test build, not a finished God Mode. "
            "Campaign only; restart the game before multiplayer. No anti-ban guarantee."
        )
        ttk.Label(frm, text=warn, wraplength=470, justify="left",
                  foreground="#8a3b00").pack(anchor="w", side="bottom", pady=(12, 0))

    def log(self, text: str) -> None:
        self.status.set(text)

    def connect(self) -> None:
        if self.busy:
            self.after(300, self.connect)
            return
        try:
            pid = game_pid()
            self.pid = pid
            self.agent = ensure_agent(pid)
            self.log(f"Connected to sp26-cod.exe (PID {pid}). Ready.")
            self.detail.set("Enable tries the known player slots first, then scans.")
        except Exception as exc:
            self.log(f"Waiting for campaign: {exc}")
            self.after(2000, self.connect)

    def _run(self, fn) -> None:
        if self.busy:
            return
        self.busy = True
        self.btn_on.configure(state="disabled")
        self.btn_off.configure(state="disabled")
        self.btn_scan.configure(state="disabled")

        def work() -> None:
            try:
                fn()
            except Exception as exc:
                self.after(0, lambda: self.log(f"Error: {exc}"))
            finally:
                self.after(0, self._done)

        threading.Thread(target=work, daemon=True).start()

    def _done(self) -> None:
        self.busy = False
        self.btn_on.configure(state="normal" if not self.frozen else "disabled")
        self.btn_off.configure(state="normal" if self.frozen else "disabled")
        self.btn_scan.configure(state="normal")

    def _start_freeze(self, hits: list[int], value: int) -> None:
        status = self.agent.freeze_start(hits, value=float(value))
        if status != 0:
            raise RuntimeError(f"freeze failed (status {status})")
        self.candidates = hits
        self.freeze_value = value
        self.frozen = True

    def enable(self) -> None:
        self._run(self._enable_worker)

    def _enable_worker(self) -> None:
        pid = game_pid()
        self.pid = pid
        self.agent = ensure_agent(pid)

        exact = load_exact()
        if exact_still_valid(self.agent, exact):
            self.after(0, lambda: self.log(f"Using {len(exact)} known 150/150 slots..."))
            self._start_freeze(exact, 150)
            self.after(0, lambda: self.detail.set(
                f"God Mode ON - {len(exact)} known 150/150 slots held. UNCONFIRMED."))
            self.after(0, lambda: self.log("God Mode enabled (known slots)."))
            return

        self.after(0, lambda: self.log("No valid known slots; scanning candidate pairs..."))
        hits: list[int] = []
        value = HEALTH_VALUES[0]
        for candidate_value in HEALTH_VALUES:
            found = scan_health_candidates(self.agent, candidate_value)
            if found:
                hits = found
                value = candidate_value
                break
        if not hits:
            self.after(0, lambda: self.log("No candidates. Be in live gameplay, not a menu."))
            return
        self.after(0, lambda: self.log(f"Freezing {len(hits)} int-{value} pairs..."))
        self._start_freeze(hits, value)
        self.after(0, lambda: self.detail.set(
            f"God Mode ON - {len(hits)} int-{value} pairs held. UNCONFIRMED; press Rescan."))
        self.after(0, lambda: self.log("God Mode enabled (scanned set)."))

    def disable(self) -> None:
        self._run(self._disable_worker)

    def _disable_worker(self) -> None:
        if self.agent:
            self.agent.freeze_stop()
        self.frozen = False
        self.candidates = []
        self.after(0, lambda: self.log("God Mode disabled; values are no longer held."))
        self.after(0, lambda: self.detail.set(""))

    def rescan(self) -> None:
        self._run(self._rescan_worker)

    def _rescan_worker(self) -> None:
        if not self.agent:
            self.agent = ensure_agent(game_pid())
        self.agent.freeze_stop()
        time.sleep(0.15)
        hits: list[int] = []
        value = HEALTH_VALUES[1]
        for candidate_value in HEALTH_VALUES:
            found = scan_health_candidates(self.agent, candidate_value)
            if found:
                hits = found
                value = candidate_value
                break
        if not hits:
            self.frozen = False
            self.after(0, lambda: self.log("No candidates after rescan."))
            return
        self._start_freeze(hits, value)
        self.after(0, lambda: self.log(f"Rescanned: {len(self.candidates)} int-{value} pairs frozen."))

    def on_close(self) -> None:
        try:
            if self.agent and self.frozen:
                self.agent.freeze_stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    Trainer().mainloop()
