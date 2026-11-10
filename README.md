# COD: Modern Warfare 4 — Campaign God Mode (WIP)

Single-player campaign trainer for **Call of Duty: Modern Warfare 4** (COD HQ,
`Call of Duty HQ\sp26\sp26-cod.exe`). It works **in-process**: a small helper DLL is
injected into the campaign process and rewrites candidate health integers.

> **Status: work in progress / unconfirmed.** The UI runs, the DLL freeze runs, and
> zeroing frozen candidates is repaired live. But two live-fire tests — freezing *every*
> int-100 pair, then *every* int-150 pair, each rewritten every 2 ms — were both
> followed by a player death. So the real health field is probably **not** an adjacent
> equal-value integer pair. Do not treat this as a finished God Mode yet.

## Layout

```
trainer.py             Tkinter UI: Enable / Disable / Rescan
start_trainer.bat      launcher
health_exact.json      two known 150/150 player-state slots (addresses go stale)
native/codgod.c        helper DLL source (file-based IPC + freeze worker)
native/codgod17.dll    current build (value/type-aware freeze)
native/codgod15.dll    earlier build (150-only freeze)
native/codgod16.dll    2 ms freeze build
tools/codgod_client.py Python IPC client, TAG v17
tools/find_health*.py  candidate scanners
tools/watch_pairs.py   value watcher used for damage tests
docs/shots/            evidence screenshots
```

## How it works

1. The DLL is injected with `SetWindowsHookExW(WH_GETMESSAGE)` + `PostMessageW`.
2. A worker thread in the DLL polls command files (`codgod_cmd_<pid>_v17.bin`) and
   writes responses atomically (`codgod_resp_<pid>_v17.bin`).
3. `Enable` loads the known 150/150 slots from `health_exact.json` if they still read
   `(150, 150)`; otherwise it scans private committed memory for adjacent integer pairs
   equal to 100/150.
4. `freeze_start(addrs, value)` tells the DLL to rewrite those addresses to `value`
   every 2 ms. `freeze_stop` halts it.

## Verified in this session

- v15 lifecycle on live campaign PID 24928: `freeze_start` → 0, `ping` → True,
  `freeze_stop` → 0, `ping` → True.
- With a freeze active, writing `0` into the frozen candidates reads back `150` within
  0.3 s and the player stays alive (pause state and live gameplay).
- Without a freeze, zeroing the candidate set produced a black screen followed by
  **CHECKPOINT REACHED**.
- **Not verified:** surviving real enemy fire. Two attempts failed (player died).

## Usage

```
start_trainer.bat          # or: python trainer.py
```

1. `sc query atvi-randgrid_sr` must show `STATE : 4 RUNNING`.
2. Launch via Steam AppID **1938090**, then start the campaign.
3. Be in **live gameplay** (not a menu or cutscene).
4. Click **Enable God Mode**; click **Rescan** after any checkpoint/mission load.
5. Click **Disable** before closing the trainer or returning to HQ/multiplayer.

## Anti-ban notes (practical, not a guarantee)

- Campaign/offline only. Never enable in multiplayer or while matchmaking.
- Data-only changes; no code patching, no engine detours.
- Close the trainer and restart the game before any multiplayer session.
- The DLL is unsigned and visible to a module scan; prefer a separate account.
- No absolute no-ban guarantee is possible.

## Next step to finish it

Health is very likely a **float**, or an int that is not stored as an equal adjacent
pair (e.g. health 100 next to max 150, or inside a struct with padding). The next
attempt should:

1. Scan for `(100,150)` / `(150,100)` integer neighbours.
2. Scan float variants of the same.
3. Confirm by watching the exact candidate during a real damage event, then lock that
   single address.
