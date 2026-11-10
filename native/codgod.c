// codgod.dll - in-process memory helper for the COD26 campaign.
// Injected with CreateRemoteThread(LoadLibraryW); talks to the trainer over
// a small named shared-memory command block.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

#define IPC_TAG "v17"

#pragma pack(push, 1)
typedef struct {
    volatile LONG seq;
    volatile LONG done;
    volatile LONG op;
    volatile LONG status;
    uint64_t addr;
    uint64_t size;
    double value;
    double value2;
    uint64_t count;
    uint64_t reserved;
} Cmd;

typedef struct {
    uint64_t base;
    uint64_t size;
    uint32_t protect;
    uint32_t type;
    uint32_t state;
    uint32_t pad;
} RegionInfo;

typedef struct {
    Cmd cmd;
    unsigned char data[16 * 1024 * 1024];
} Shared;
#pragma pack(pop)

enum {
    OP_PING = 1,
    OP_REGIONS = 2,
    OP_READ = 3,
    OP_WRITE = 4,
    OP_SCAN_FLOAT = 5,
    OP_SCAN_PAIR = 6,
    OP_STOP = 7,
    OP_UNLOAD = 8,
    OP_SCAN_RANGE = 9,
    OP_SCAN_RANGE_INT = 10,
    OP_FREEZE = 11,
    OP_STOP_FREEZE = 12,
};

static HMODULE g_module;
static HANDLE g_thread;
static Shared* g_sh;
static Shared g_buf;
static volatile LONG g_stop;
static volatile LONG g_freeze_active;
static uint64_t g_freeze_addrs[4096];
static int g_freeze_count;
static int g_freeze_value = 150;
static int g_freeze_float = 0;
static LONG g_last_seq;

static void logmsg(const char* msg) {
    HANDLE f = CreateFileA("C:\\Users\\flaze\\Desktop\\Coding\\cod-sp-trainer\\native\\codgod.log",
                           FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                           NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        DWORD wrote = 0;
        WriteFile(f, msg, (DWORD)strlen(msg), &wrote, NULL);
        WriteFile(f, "\r\n", 2, &wrote, NULL);
        CloseHandle(f);
    }
}

static int writable_protect(DWORD p) {
    return (p & (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)) != 0;
}

static void do_regions(Shared* sh) {
    RegionInfo* out = (RegionInfo*)sh->data;
    uint64_t count = 0;
    uintptr_t addr = 0;
    MEMORY_BASIC_INFORMATION mbi;
    while (VirtualQuery((void*)addr, &mbi, sizeof(mbi)) == sizeof(mbi)) {
        uintptr_t base = (uintptr_t)mbi.BaseAddress;
        uint64_t size = (uint64_t)mbi.RegionSize;
        if (size == 0) break;
        if (mbi.State == MEM_COMMIT && (mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)) == 0) {
            if (count < (sizeof(sh->data) / sizeof(RegionInfo))) {
                out[count].base = base;
                out[count].size = size;
                out[count].protect = mbi.Protect;
                out[count].type = mbi.Type;
                out[count].state = mbi.State;
                out[count].pad = 0;
                count++;
            }
        }
        uintptr_t next = base + size;
        if (next <= addr) break;
        addr = next;
    }
    sh->cmd.count = count;
}

static void do_read(Shared* sh) {
    uint64_t size = sh->cmd.size;
    if (size > sizeof(sh->data)) size = sizeof(sh->data);
    SIZE_T got = 0;
    if (!ReadProcessMemory(GetCurrentProcess(), (void*)(uintptr_t)sh->cmd.addr,
                           sh->data, (SIZE_T)size, &got)) {
        sh->cmd.status = 1;
        sh->cmd.count = got;
        return;
    }
    sh->cmd.count = got;
}

static void do_write(Shared* sh) {
    uint64_t size = sh->cmd.size;
    if (size > sizeof(sh->data)) size = sizeof(sh->data);
    SIZE_T wrote = 0;
    if (!WriteProcessMemory(GetCurrentProcess(), (void*)(uintptr_t)sh->cmd.addr,
                            sh->data, (SIZE_T)size, &wrote)) {
        sh->cmd.status = 2;
        sh->cmd.count = wrote;
        return;
    }
    sh->cmd.count = wrote;
}

static void do_scan_float(Shared* sh, int pair) {
    const float target = (float)sh->cmd.value;
    const int exact = sh->cmd.value2 == 0.0;
    const float tol = (float)(sh->cmd.value2 > 0 ? sh->cmd.value2 : 0.0001);
    uint32_t target_bits = 0;
    memcpy(&target_bits, &target, sizeof(target_bits));
    const size_t chunk = 8 * 1024 * 1024;
    unsigned char* buf = (unsigned char*)malloc(chunk);
    uint64_t* out = (uint64_t*)sh->data;
    const uint64_t capacity = sizeof(sh->data) / sizeof(uint64_t);
    uint64_t count = 0;
    if (!buf) { sh->cmd.status = 3; return; }

    uintptr_t addr = 0;
    MEMORY_BASIC_INFORMATION mbi;
    while (VirtualQuery((void*)addr, &mbi, sizeof(mbi)) == sizeof(mbi)) {
        uintptr_t base = (uintptr_t)mbi.BaseAddress;
        uint64_t size = (uint64_t)mbi.RegionSize;
        if (size == 0) break;
        uintptr_t next = base + size;
        if (next <= addr) break;
        if (mbi.State == MEM_COMMIT && mbi.Type == MEM_PRIVATE &&
            writable_protect(mbi.Protect) && (mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)) == 0) {
            uintptr_t pos = base;
            while (pos < next) {
                uint64_t want = next - pos;
                if (want > chunk) want = chunk;
                memcpy(buf, (void*)pos, (size_t)want);
                {
                    size_t n = (size_t)want / 4;
                    if (exact) {
                        const uint32_t* u = (const uint32_t*)buf;
                        for (size_t i = 0; i < n; i++) {
                            if (u[i] == target_bits) {
                                if (pair) {
                                    if (i + 1 < n && u[i + 1] == target_bits) {
                                        if (count < capacity) out[count++] = pos + (uint64_t)i * 4;
                                    }
                                } else if (count < capacity) {
                                    out[count++] = pos + (uint64_t)i * 4;
                                }
                            }
                        }
                    } else {
                        const float* f = (const float*)buf;
                        for (size_t i = 0; i < n; i++) {
                            if (fabsf(f[i] - target) <= tol) {
                                if (pair) {
                                    if (i + 1 < n && fabsf(f[i + 1] - target) <= tol) {
                                        if (count < capacity) out[count++] = pos + (uint64_t)i * 4;
                                    }
                                } else if (count < capacity) {
                                    out[count++] = pos + (uint64_t)i * 4;
                                }
                            }
                        }
                    }
                }
                pos += want;
                if (count >= capacity) break;
            }
        }
        if (count >= capacity) break;
        addr = next;
    }
    free(buf);
    sh->cmd.count = count;
}

static void do_scan_range(Shared* sh) {
    const float target = (float)sh->cmd.value;
    const int int_mode = sh->cmd.op == OP_SCAN_RANGE_INT;
    const int exact = int_mode || sh->cmd.value2 == 0.0;
    const float tol = (float)(sh->cmd.value2 > 0 ? sh->cmd.value2 : 0.0001);
    const int pair = sh->cmd.reserved != 0;
    uint32_t target_bits = 0;
    if (int_mode) target_bits = (uint32_t)sh->cmd.value;
    else memcpy(&target_bits, &target, sizeof(target_bits));
    const size_t chunk = 8 * 1024 * 1024;
    unsigned char* buf = (unsigned char*)malloc(chunk);
    uint64_t* out = (uint64_t*)sh->data;
    const uint64_t capacity = sizeof(sh->data) / sizeof(uint64_t);
    uint64_t count = 0;
    if (!buf) { sh->cmd.status = 3; return; }

    uintptr_t pos = (uintptr_t)sh->cmd.addr;
    uintptr_t end = pos + (uintptr_t)sh->cmd.size;
    logmsg("range enter");
    while (pos < end && count < capacity) {
        uint64_t want = end - pos;
        if (want > chunk) want = chunk;
        SIZE_T got = 0;
        if (!ReadProcessMemory(GetCurrentProcess(), (void*)pos, buf, (SIZE_T)want, &got) || got < 4) {
            pos += want;
            continue;
        }
        size_t n = (size_t)got / 4;
        if (exact) {
            const uint32_t* u = (const uint32_t*)buf;
            for (size_t i = 0; i < n && count < capacity; i++) {
                if (u[i] == target_bits && (!pair || (i + 1 < n && u[i + 1] == target_bits))) {
                    out[count++] = pos + (uint64_t)i * 4;
                }
            }
        } else {
            const float* f = (const float*)buf;
            for (size_t i = 0; i < n && count < capacity; i++) {
                if (fabsf(f[i] - target) <= tol && (!pair || (i + 1 < n && fabsf(f[i + 1] - target) <= tol))) {
                    out[count++] = pos + (uint64_t)i * 4;
                }
            }
        }
        pos += want;
    }
    free(buf);
    sh->cmd.count = count;
    logmsg("range exit");
}

static DWORD response_bytes(void) {
    switch (g_buf.cmd.op) {
        case OP_READ: return (DWORD)g_buf.cmd.count;
        case OP_REGIONS: return (DWORD)(g_buf.cmd.count * sizeof(RegionInfo));
        case OP_SCAN_FLOAT:
        case OP_SCAN_PAIR:
        case OP_SCAN_RANGE:
        case OP_SCAN_RANGE_INT: return (DWORD)(g_buf.cmd.count * sizeof(uint64_t));
        default: return 0;
    }
}

static int read_command(const char* path) {
    HANDLE f = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                           NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) return 0;
    DWORD got = 0;
    if (!ReadFile(f, &g_buf.cmd, sizeof(Cmd), &got, NULL) || got != sizeof(Cmd)) {
        CloseHandle(f);
        return 0;
    }
    LONG seq = g_buf.cmd.seq;
    if (seq == g_last_seq) {
        CloseHandle(f);
        return 0;
    }
    if (g_buf.cmd.op == OP_WRITE || g_buf.cmd.op == OP_FREEZE) {
        DWORD want = (DWORD)g_buf.cmd.size;
        if (want > sizeof(g_buf.data)) want = sizeof(g_buf.data);
        SetFilePointer(f, sizeof(Cmd), NULL, FILE_BEGIN);
        if (!ReadFile(f, g_buf.data, want, &got, NULL) || got != want) {
            CloseHandle(f);
            return 0;
        }
    }
    CloseHandle(f);
    g_last_seq = seq;
    return 1;
}

static void write_response(const char* path) {
    char temp[512];
    snprintf(temp, sizeof(temp), "%s.tmp", path);
    HANDLE f = CreateFileA(temp, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                           NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) return;
    DWORD wrote = 0;
    DWORD bytes = response_bytes();
    WriteFile(f, &g_buf.cmd, sizeof(Cmd), &wrote, NULL);
    if (bytes) WriteFile(f, g_buf.data, bytes, &wrote, NULL);
    CloseHandle(f);
    for (int i = 0; i < 100; i++) {
        if (MoveFileExA(temp, path, MOVEFILE_REPLACE_EXISTING)) break;
        Sleep(2);
    }
}

static DWORD WINAPI freeze_thread(LPVOID param) {
    (void)param;
    while (g_freeze_active) {
        for (int i = 0; i < g_freeze_count; i++) {
            int* p = (int*)(uintptr_t)g_freeze_addrs[i];
            if (g_freeze_float) {
                ((float*)p)[0] = (float)g_freeze_value;
                ((float*)p)[1] = (float)g_freeze_value;
            } else {
                p[0] = g_freeze_value;
                p[1] = g_freeze_value;
            }
        }
        Sleep(2);
    }
    return 0;
}

static DWORD WINAPI server_thread(LPVOID param) {
    (void)param;
    logmsg("server_thread enter");
    g_sh = &g_buf;
    char cmd_path[512];
    char resp_path[512];
    snprintf(cmd_path, sizeof(cmd_path),
             "C:\\Users\\flaze\\Desktop\\Coding\\cod-sp-trainer\\native\\codgod_cmd_%lu_%s.bin",
             (unsigned long)GetCurrentProcessId(), IPC_TAG);
    snprintf(resp_path, sizeof(resp_path),
             "C:\\Users\\flaze\\Desktop\\Coding\\cod-sp-trainer\\native\\codgod_resp_%lu_%s.bin",
             (unsigned long)GetCurrentProcessId(), IPC_TAG);
    logmsg("file ipc start");

    while (!g_stop) {
        if (read_command(cmd_path)) {
            LONG op = g_buf.cmd.op;
            LONG in_count = g_buf.cmd.count;
            g_buf.cmd.status = 0;
            g_buf.cmd.count = 0;
            switch (op) {
                case OP_PING: break;
                case OP_REGIONS: do_regions(g_sh); break;
                case OP_READ: do_read(g_sh); break;
                case OP_WRITE: do_write(g_sh); break;
                case OP_SCAN_FLOAT: do_scan_float(g_sh, 0); break;
                case OP_SCAN_PAIR: do_scan_float(g_sh, 1); break;
                case OP_SCAN_RANGE: do_scan_range(g_sh); break;
                case OP_SCAN_RANGE_INT: do_scan_range(g_sh); break;
                case OP_FREEZE:
                    g_freeze_value = (int)g_buf.cmd.value;
                    g_freeze_float = g_buf.cmd.value2 != 0.0;
                    g_freeze_count = (int)(in_count > 4096 ? 4096 : in_count);
                    memcpy(g_freeze_addrs, g_buf.data, (size_t)g_freeze_count * 8);
                    g_freeze_active = 1;
                    CreateThread(NULL, 0, freeze_thread, NULL, 0, NULL);
                    break;
                case OP_STOP_FREEZE: g_freeze_active = 0; break;
                case OP_STOP: g_stop = 1; break;
                case OP_UNLOAD:
                    write_response(resp_path);
                    Sleep(20);
                    FreeLibraryAndExitThread(g_module, 0);
                    break;
                default: g_buf.cmd.status = 4; break;
            }
            write_response(resp_path);
        }
        Sleep(2);
    }
    return 0;
}

BOOL WINAPI DllMain(HMODULE module, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        logmsg("DllMain attach");
        g_module = module;
        DisableThreadLibraryCalls(module);
        HMODULE pinned = NULL;
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN | GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                           (LPCWSTR)module, &pinned);
        logmsg("pinned");
        g_thread = CreateThread(NULL, 0, server_thread, NULL, 0, NULL);
        logmsg(g_thread ? "thread created" : "thread create failed");
        if (g_thread) CloseHandle(g_thread);
    }
    return TRUE;
}

// Export used only by the SetWindowsHookEx fallback injector.
__declspec(dllexport) LRESULT CALLBACK CodgodHookProc(int code, WPARAM wParam, LPARAM lParam) {
    return CallNextHookEx(NULL, code, wParam, lParam);
}



