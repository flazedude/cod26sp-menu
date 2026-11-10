#!/usr/bin/env python3
"""Inject codgod.dll into sp26-cod.exe and talk to it over shared memory."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

k = ctypes.WinDLL("kernel32", use_last_error=True)
ps = ctypes.WinDLL("psapi", use_last_error=True)

k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k.OpenProcess.restype = wt.HANDLE
k.CloseHandle.argtypes = [wt.HANDLE]
k.VirtualAllocEx.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.DWORD, wt.DWORD]
k.VirtualAllocEx.restype = wt.LPVOID
k.VirtualFreeEx.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.DWORD]
k.VirtualFreeEx.restype = wt.BOOL
k.WriteProcessMemory.argtypes = [wt.HANDLE, wt.LPVOID, wt.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.restype = wt.BOOL
k.ReadProcessMemory.argtypes = [wt.HANDLE, wt.LPCVOID, wt.LPVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.ReadProcessMemory.restype = wt.BOOL
k.CreateRemoteThread.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.LPVOID, wt.LPVOID, wt.DWORD, ctypes.POINTER(wt.DWORD)]
k.CreateRemoteThread.restype = wt.HANDLE
k.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
k.WaitForSingleObject.restype = wt.DWORD
k.GetModuleHandleW.argtypes = [wt.LPCWSTR]
k.GetModuleHandleW.restype = wt.HMODULE
k.GetProcAddress.argtypes = [wt.HMODULE, wt.LPCSTR]
k.GetProcAddress.restype = ctypes.c_void_p
k.GetModuleHandleExW.argtypes = [wt.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
k.GetModuleHandleExW.restype = wt.BOOL
k.GetModuleFileNameW.argtypes = [wt.HMODULE, wt.LPWSTR, wt.DWORD]
k.GetModuleFileNameW.restype = wt.DWORD
k.CreateFileMappingW.argtypes = [wt.HANDLE, wt.LPVOID, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPCWSTR]
k.CreateFileMappingW.restype = wt.HANDLE
k.OpenFileMappingW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
k.OpenFileMappingW.restype = wt.HANDLE
k.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
k.MapViewOfFile.restype = ctypes.c_void_p
k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
k.UnmapViewOfFile.restype = wt.BOOL
ps.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(wt.HMODULE), wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
ps.EnumProcessModulesEx.restype = wt.BOOL
ps.GetModuleBaseNameW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]
ps.GetModuleBaseNameW.restype = wt.DWORD
ps.GetModuleFileNameExW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]
ps.GetModuleFileNameExW.restype = wt.DWORD

FILE_MAP_ALL_ACCESS = 0xF001F
PAGE_READWRITE = 0x04
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
TAG = "v17"

DATA_OFF = 64
DATA_SIZE = 16 * 1024 * 1024
SHARED_SIZE = DATA_OFF + DATA_SIZE


class Cmd(ctypes.Structure):
    _fields_ = [
        ("seq", ctypes.c_int32),
        ("done", ctypes.c_int32),
        ("op", ctypes.c_int32),
        ("status", ctypes.c_int32),
        ("addr", ctypes.c_uint64),
        ("size", ctypes.c_uint64),
        ("value", ctypes.c_double),
        ("value2", ctypes.c_double),
        ("count", ctypes.c_uint64),
        ("reserved", ctypes.c_uint64),
    ]


class Region(ctypes.Structure):
    _fields_ = [
        ("base", ctypes.c_uint64),
        ("size", ctypes.c_uint64),
        ("protect", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("state", ctypes.c_uint32),
        ("pad", ctypes.c_uint32),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("th32ModuleID", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("GlblcntUsage", wt.DWORD),
        ("ProccntUsage", wt.DWORD),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", wt.DWORD),
        ("hModule", wt.HMODULE),
        ("szModule", wt.WCHAR * 256),
        ("szExePath", wt.WCHAR * 260),
    ]


k.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k.CreateToolhelp32Snapshot.restype = wt.HANDLE
k.Module32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
k.Module32FirstW.restype = wt.BOOL
k.Module32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
k.Module32NextW.restype = wt.BOOL

k.LoadLibraryW.argtypes = [wt.LPCWSTR]
k.LoadLibraryW.restype = wt.HMODULE

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wt.HMODULE, wt.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wt.BOOL
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL


def find_pid(name: str = "sp26-cod.exe") -> int:
    out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], text=True, errors="replace")
    for line in out.splitlines():
        if name.lower() in line.lower():
            return int(line.split(",")[1].strip('"'))
    raise SystemExit(f"process not found: {name}")


def ps_modules(pid: int) -> list[tuple[int, int, str, str]]:
    script = (
        f"(Get-Process -Id {pid}).Modules | "
        "Select-Object ModuleName,ModuleMemorySize,FileName,"
        "@{Name='Base';Expression={$_.BaseAddress.ToInt64()}} | "
        "ConvertTo-Json -Compress"
    )
    try:
        import json
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command", script], text=True, errors="replace")
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return [(int(x["Base"]), int(x["ModuleMemorySize"]), x["ModuleName"], x["FileName"]) for x in data]
    except Exception as exc:
        print(f"ps_modules failed: {exc}", file=sys.stderr)
        return []


def modules(pid: int) -> list[tuple[int, int, str, str]]:
    result = ps_modules(pid)
    if result:
        return result
    TH32CS_SNAPMODULE = 0x00000008
    TH32CS_SNAPMODULE32 = 0x00000010
    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if not snap or int(snap) == 0xFFFFFFFFFFFFFFFF:
        return []
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
        if not k.Module32FirstW(snap, ctypes.byref(entry)):
            return []
        result = []
        while True:
            result.append((int(entry.modBaseAddr or 0), int(entry.modBaseSize), entry.szModule, entry.szExePath))
            if not k.Module32NextW(snap, ctypes.byref(entry)):
                break
        return result
    finally:
        k.CloseHandle(snap)


def ps_main_window(pid: int) -> int:
    script = f"(Get-Process -Id {pid}).MainWindowHandle.ToInt64()"
    try:
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command", script], text=True, errors="replace").strip()
        return int(out)
    except Exception:
        return 0


def inject(pid: int, dll: Path) -> None:
    # The DLL's worker opens this section as soon as DllMain runs.
    mapping = Agent(pid)
    have = {m[2].lower(): m for m in modules(pid)}
    if dll.name.lower() in have:
        print(f"already loaded at {have[dll.name.lower()][0]:#x}")
        mapping.close()
        return
    if not dll.exists():
        raise SystemExit(f"missing DLL: {dll}")
    h = k.OpenProcess(0x1F0FFF, False, pid)
    if not h:
        raise SystemExit(f"OpenProcess failed: {ctypes.get_last_error()}")
    remote = 0
    try:
        loader = k.GetProcAddress(k.GetModuleHandleW("kernel32.dll"), b"LoadLibraryW")
        if not loader:
            raise SystemExit("LoadLibraryW not found")
        owner = ctypes.c_void_p()
        if not k.GetModuleHandleExW(0x0004 | 0x0002, ctypes.c_void_p(loader), ctypes.byref(owner)):
            raise SystemExit(f"GetModuleHandleEx failed: {ctypes.get_last_error()}")
        owner_addr = int(owner.value or 0)
        owner_path = ctypes.create_unicode_buffer(32768)
        k.GetModuleFileNameW(wt.HMODULE(owner_addr), owner_path, 32768)
        owner_name = os.path.basename(owner_path.value).lower()
        target_owner = have.get(owner_name)
        if not target_owner:
            raise SystemExit(f"target does not have {owner_name}")
        target_base = target_owner[0]
        target_loader = target_base + (int(loader) - owner_addr)
        path_bytes = str(dll).encode("utf-16-le") + b"\0\0"
        remote = k.VirtualAllocEx(h, None, len(path_bytes), 0x3000, PAGE_READWRITE)
        if not remote:
            raise SystemExit(f"VirtualAllocEx failed: {ctypes.get_last_error()}")
        written = ctypes.c_size_t()
        if not k.WriteProcessMemory(h, remote, path_bytes, len(path_bytes), ctypes.byref(written)) or written.value != len(path_bytes):
            raise SystemExit(f"WriteProcessMemory failed: {ctypes.get_last_error()}")
        tid = wt.DWORD()
        thread = k.CreateRemoteThread(h, None, 0, ctypes.c_void_p(target_loader), remote, 0, ctypes.byref(tid))
        if not thread:
            raise SystemExit(f"CreateRemoteThread failed: {ctypes.get_last_error()}")
        try:
            waited = k.WaitForSingleObject(thread, 15000)
            print(f"thread wait={waited} tid={tid.value}")
        finally:
            k.CloseHandle(thread)
        k.VirtualFreeEx(h, remote, 0, 0x8000)
        remote = 0
        time.sleep(1)
        have = {m[2].lower(): m for m in modules(pid)}
        if dll.name.lower() not in have:
            raise SystemExit("DLL did not appear in target module list")
        print(f"loaded at {have[dll.name.lower()][0]:#x}")
        mapping.close()
    finally:
        if remote:
            k.VirtualFreeEx(h, remote, 0, 0x8000)
        k.CloseHandle(h)


class Agent:
    def __init__(self, pid: int):
        self.pid = pid
        root = Path(__file__).resolve().parents[1] / "native"
        self.cmd_path = root / f"codgod_cmd_{pid}_{TAG}.bin"
        self.resp_path = root / f"codgod_resp_{pid}_{TAG}.bin"
        self.seq = 0
        if self.cmd_path.exists():
            raw = self.cmd_path.read_bytes()
            if len(raw) >= ctypes.sizeof(Cmd):
                self.seq = Cmd.from_buffer_copy(raw[: ctypes.sizeof(Cmd)]).seq
        print(f"agent pid={pid} seq={self.seq}")

    def close(self) -> None:
        pass

    def _atomic_write(self, path: Path, payload: bytes) -> None:
        tmp = path.with_name(path.name + f".tmp{os.getpid()}_{self.seq}")
        tmp.write_bytes(payload)
        for _ in range(200):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.005)
        raise TimeoutError(f"could not replace {path}")

    def _resp_bytes(self, op: int, count: int) -> int:
        if op == 3:
            return min(count, DATA_SIZE)
        if op == 2:
            return min(count * ctypes.sizeof(Region), DATA_SIZE)
        if op in (5, 6, 9, 10):
            return min(count * 8, DATA_SIZE)
        return 0

    def call(self, op: int, addr: int = 0, size: int = 0, value: float = 0.0, value2: float = 0.0, data: bytes = b"", count: int = 0, reserved: int = 0, timeout: float = 120.0):
        self.seq += 1
        c = Cmd()
        c.seq = self.seq
        c.done = 0
        c.op = op
        c.status = 0
        c.addr = addr
        c.size = size
        c.value = value
        c.value2 = value2
        c.count = count
        c.reserved = reserved
        payload = ctypes.string_at(ctypes.byref(c), ctypes.sizeof(Cmd)) + data
        try:
            self.resp_path.unlink()
        except FileNotFoundError:
            pass
        self._atomic_write(self.cmd_path, payload)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.resp_path.exists():
                try:
                    raw = self.resp_path.read_bytes()
                except (PermissionError, FileNotFoundError):
                    time.sleep(0.005)
                    continue
                if len(raw) >= ctypes.sizeof(Cmd):
                    rc = Cmd.from_buffer_copy(raw[: ctypes.sizeof(Cmd)])
                    if rc.seq == self.seq:
                        n = self._resp_bytes(op, int(rc.count))
                        return rc.status, rc.count, raw[64 : 64 + n]
            time.sleep(0.005)
        raise TimeoutError(f"command {op} timeout")

    def ping(self) -> bool:
        status, count, _ = self.call(1, timeout=5)
        return status == 0

    def regions(self) -> list[Region]:
        status, count, data = self.call(2)
        arr = (Region * count).from_buffer_copy(data[: count * ctypes.sizeof(Region)])
        return list(arr)

    def read(self, addr: int, size: int) -> bytes:
        status, count, data = self.call(3, addr=addr, size=size)
        return data

    def write(self, addr: int, data: bytes) -> bool:
        status, count, _ = self.call(4, addr=addr, size=len(data), data=data)
        return status == 0 and count == len(data)

    def scan_float(self, value: float, tol: float = 0.001, pair: bool = False) -> np.ndarray:
        status, count, data = self.call(6 if pair else 5, value=value, value2=tol)
        if status != 0:
            raise RuntimeError(f"scan status {status}")
        return np.frombuffer(data[: count * 8], dtype=np.uint64)

    def scan_range(self, addr: int, size: int, value: float, tol: float = 0.0, pair: bool = False) -> np.ndarray:
        status, count, data = self.call(9, addr=addr, size=size, value=value, value2=tol, reserved=1 if pair else 0)
        if status != 0:
            raise RuntimeError(f"range scan status {status}")
        return np.frombuffer(data[: count * 8], dtype=np.uint64)

    def scan_range_int(self, addr: int, size: int, value: int, pair: bool = False) -> np.ndarray:
        status, count, data = self.call(10, addr=addr, size=size, value=float(value), reserved=1 if pair else 0)
        if status != 0:
            raise RuntimeError(f"int range scan status {status}")
        return np.frombuffer(data[: count * 8], dtype=np.uint64)

    def freeze_start(self, addrs, value: float = 150.0, float_mode: bool = False) -> int:
        payload = struct.pack(f"<{len(addrs)}Q", *addrs)
        status, _, _ = self.call(11, size=len(payload), data=payload, count=len(addrs), value=value, value2=1.0 if float_mode else 0.0, timeout=10)
        return status

    def freeze_stop(self) -> int:
        status, _, _ = self.call(12, timeout=5)
        return status


def inject_hook(pid: int, dll: Path) -> None:
    mapping = Agent(pid)
    have = {m[2].lower(): m for m in modules(pid)}
    if dll.name.lower() in have:
        print(f"already loaded at {have[dll.name.lower()][0]:#x}")
        mapping.close()
        return
    hmod = k.LoadLibraryW(str(dll))
    if not hmod:
        raise SystemExit(f"LoadLibraryW local failed: {ctypes.get_last_error()}")
    proc = k.GetProcAddress(hmod, b"CodgodHookProc")
    if not proc:
        raise SystemExit(f"CodgodHookProc not found: {ctypes.get_last_error()}")
    hwnd = ps_main_window(pid)
    if not hwnd:
        raise SystemExit("no main window handle for hook injection")
    tid = user32.GetWindowThreadProcessId(wt.HWND(hwnd), None)
    print(f"hwnd={hwnd:#x} tid={tid}")
    loaded = False
    for hook_type in (3, 4, 5):
        hook = user32.SetWindowsHookExW(hook_type, ctypes.c_void_p(proc), hmod, tid)
        if not hook:
            print(f"hook type {hook_type} failed: {ctypes.get_last_error()}")
            continue
        user32.PostMessageW(wt.HWND(hwnd), 0, 0, 0)
        for _ in range(30):
            time.sleep(0.1)
            if dll.name.lower() in {m[2].lower() for m in modules(pid)}:
                loaded = True
                break
        if loaded:
            print(f"hook type {hook_type} loaded DLL")
            time.sleep(2)
            user32.UnhookWindowsHookEx(hook)
            break
        user32.UnhookWindowsHookEx(hook)
    if not loaded:
        raise SystemExit("hook injection did not load DLL")
    mapping.close()


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: codgod_client.py inject|ping|regions|read|write|scan PID [args]")
        return
    command = sys.argv[1]
    pid = int(sys.argv[2]) if len(sys.argv) > 2 else find_pid()
    dll = Path(os.environ.get("COD_GOD_DLL", str(Path(__file__).resolve().parents[1] / "native" / "codgod.dll")))
    if command == "inject":
        inject(pid, dll)
        return
    if command == "hook":
        inject_hook(pid, dll)
        return
    agent = Agent(pid)
    try:
        if command == "ping":
            print("ping", agent.ping())
        elif command == "regions":
            regs = agent.regions()
            print(f"regions {len(regs)}")
            for r in sorted(regs, key=lambda x: x.size, reverse=True)[:20]:
                print(f"{r.base:#018x} {r.size/1048576:9.2f} MiB prot={r.protect:#x} type={r.type:#x}")
        elif command == "read":
            addr = int(sys.argv[3], 0)
            size = int(sys.argv[4], 0) if len(sys.argv) > 4 else 64
            print(agent.read(addr, size).hex())
        elif command == "write":
            addr = int(sys.argv[3], 0)
            data = bytes.fromhex(sys.argv[4])
            print("write", agent.write(addr, data))
        elif command == "scan":
            value = float(sys.argv[3])
            tol = float(sys.argv[4]) if len(sys.argv) > 4 else 0.001
            pair = len(sys.argv) > 5 and sys.argv[5] == "pair"
            addrs = agent.scan_float(value, tol, pair)
            print(f"count={len(addrs)}")
            for a in addrs[:20]:
                print(f"{int(a):#018x}")
            if len(sys.argv) > 6:
                np.savez_compressed(sys.argv[6], addresses=addrs)
        elif command == "rscan":
            addr = int(sys.argv[3], 0)
            size = int(sys.argv[4], 0)
            value = float(sys.argv[5])
            tol = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
            pair = len(sys.argv) > 7 and sys.argv[7] == "pair"
            addrs = agent.scan_range(addr, size, value, tol, pair)
            print(f"count={len(addrs)}")
            for a in addrs[:20]:
                print(f"{int(a):#018x}")
            if len(sys.argv) > 8:
                np.savez_compressed(sys.argv[8], addresses=addrs)
        else:
            print("unknown command")
    finally:
        agent.close()


if __name__ == "__main__":
    main()





