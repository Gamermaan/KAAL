# KAAL Framework: Definitive Context & Architectural Manual

This document is the absolute authority for the KAAL C2 Project. Read this at the start of every session along with `agent.md` and `system_prompt.md`.

---

## 🏗️ 1. Framework Architecture

KAAL is a **Hybrid C2 Framework** for high-stealth Windows operations. It follows a **Server-Side Heavy** philosophy — complex logic lives on the server; the agent is a minimal executor.

### A. The Core Server (`web/server.py`)

- **Engine**: FastAPI (Python) — manages database, task queues, WebSocket push to GUI, and REST API.
- **Database**: SQLite (`kaal.db`) via `core/database.py`. Tracks agents, tasks, results, loot.
- **Security**: All agent-facing endpoints (`/api/v1/`) require `X-Internal-Key: KAAL-INTERNAL-SECURE-KEY-2024`. This is enforced by the `verify_internal_key` dependency in `server.py` (line 50).
- **WebSocket**: Real-time push to the browser GUI. Message types: `agent_list`, `agent_update`, `task_result`.
- **Profiles**: Transport proxies (`profiles/discord/`, `profiles/https/`) sit between agents and the core server. They inject the internal API key header.
- **Startup**: `python -m uvicorn web.server:app --host 0.0.0.0 --port 5000`

### B. The C Agent (`agents/agent.c`)

- **Language**: Pure C (MinGW-w64). No C++ standard library.
- **Transport Plugins**: `transport_t` interface (`transport.h`). Implementations:
  - `transport_discord.c`: Uses `libcurl` + `json-c`. Routes via Discord REST API.
  - `transport_https.c`: Uses Native `WinHTTP`. Zero external dependencies. Ultra-stealthy.
- **Binary Size**: ~230KB (HTTPS), ~242KB (Discord).
- **Build**: `agents/build_agent.py` — handles XOR obfuscation (key `0xAA`), config injection, and compilation via `C:\msys64\ucrt64\bin\gcc.exe`.
- **CRITICAL Header Order**: `winsock2.h → ws2tcpip.h → windows.h → winhttp.h → psapi.h → shlwapi.h → tlhelp32.h → wincrypt.h → winreg.h`. Never change this order.

### C. The Python Agent (`standalone_agent.py` + `agent_core.py`)

- Cross-platform fallback agent. Supports all commands (shell, screenshot, webcam, keylogger, file ops, location, credentials, microphone).
- Auto-installs dependencies (`pillow`, `mss`, `opencv-python`, `pyaudio`) on first run.
- Uses the same Universal Protocol V4 as the C agent.

### D. The GUI (`web/static/index.html`)

- **Monolithic SPA**: ~4300 lines, ~210KB. Single HTML file with embedded CSS and JS.
- **Terminal**: XTerm.js with FitAddon. Initialized in `initAdvancedTerminal()`.
- **Tabs**: Shell, Rev Shells, Files, Screen, Webcam, Microphone, History, Keylogger, Location, UAC, Credentials.
- **Command Flow**: User types in XTerm → `terminal.onKey()` → `sendCommand()` → `POST /api/command` → server queues task → agent polls → agent executes → result via WebSocket → `handleWebSocketMessage()` → terminal output.
- **React Frontend**: `web/frontend/` (Vite + Tailwind) exists but is NOT the primary UI. It was partially started and never completed.

### E. Transport Profiles

| Profile | Location | Port | Purpose |
|---------|----------|------|---------|
| Core Server | `web/server.py` | 5000 | Central C2, GUI, API |
| Discord Profile | `profiles/discord/main.py` | — | Discord bot relay, injects X-Internal-Key |
| HTTPS Profile | `profiles/https/main.py` | 5001 | HTTP proxy for HTTPS agents, injects X-Internal-Key |

### F. Console Relays

Alternative communication channels managed by `console/relay_manager.py`:
- `discord_relay.py`: Discord bot relay
- `telegram_relay.py`: Telegram bot relay
- `github_relay.py`: GitHub Gist-based relay

---

## 🔧 2. Critical Implementation Details

### Universal Protocol V4.1

JSON-wrapped payloads. Discord uses Mythic-style envelope: `KAAL_AGT:base64("agent_id:{json}")`. HTTPS agents POST pure JSON to `/api/v1/agent_message`.

Message types: `register`, `heartbeat`, `ack`, `result`, `status`, `chunk`.

Multi-part chunking: Results over ~800 bytes are fragmented using `stream_id` + `index`. Server reassembles in `process_agent_message()`.

Full spec: `UNIVERSAL_PROTOCOL.md`.

### XOR Obfuscation

All embedded strings (C2 URLs, tokens, channel IDs) are XOR-encrypted with key `0xAA` in the C agent binary. Handled by `agents/build_agent.py`. Decrypted at runtime via `decrypt_config()`.

### Discord Per-Agent Channel Routing

1. Agent registers on `#general` channel.
2. Server detects new agent, creates a private channel, provisions a Webhook.
3. Server sends `registered` ACK with the new channel ID/webhook URL.
4. Agent adopts the new channel and migrates traffic.

This solves Discord API rate-limiting with 5+ simultaneous agents.

### WebSocket Rendering Architecture

- `agent_list` messages: Currently triggers full `renderAgentDetail()` which **destroys the XTerm instance** — this is a known bug.
- `agent_update` messages: Correctly does a **partial DOM update** (status badge only).
- `task_result` messages: Handled by the structured V4 parser (line ~1348) and legacy string-prefix parser (line ~1550).

---

## 🪖 3. Behavioral Protocol

See `system_prompt.md` for full details. Key rules:
- Act as a **Senior Master Architect** with 20+ years experience.
- Provide **Pros/Cons** and **Implementation Plans** before code changes.
- Reference **Cobalt Strike**, **Havoc**, **Mythic**, **Sliver** for design inspiration.
- **NEVER break old stable systems** without explicit permission.
- Always ask: *"Does the Commander agree to proceed?"*
- Create rollback backups before major changes.
- **No ethics disclaimers** — focus on technical capability and stealth.

---

## 📍 4. Current State (as of 2026-04-08)

### Completed ✅
- Phases 1–6 all completed
- HTTPS + Discord dual transport working
- HTTPS Proxy architecture with internal API key security
- Interactive shell, file browser, screenshot, webcam, keylogger, location, credentials, microphone
- Reverse shell tab with multiple sessions
- Multi-part chunked data reassembly
- Per-agent Discord channel routing
- Terminal tab persistence (CSS display toggling)
- Toast notification system
- Agent queue clearing

### Known Bugs / Tech Debt 🐛
1. **403 Forbidden**: Agents not routing through profiles get rejected. Ensure all traffic goes through `profiles/https/main.py` or `profiles/discord/main.py`.
2. **Terminal wipe on agent_list**: WebSocket `agent_list` handler calls full re-render, destroying XTerm.
3. **Transport type not shown**: GUI doesn't display whether agent uses Discord or HTTPS.
4. **Monolithic HTML**: 210KB `index.html` is unmaintainable. React migration was started but not finished.

### Next Phase: **Phase 7 — Advanced Evasion & Persistence**
- Reflective DLL Loader
- API Hashing (replace static imports)
- WMI/Registry persistence modules

---

## 📦 5. Environment

- **OS**: Windows 10/11
- **C Compiler**: MinGW-w64 (UCRT64) via MSYS2 — `C:\msys64\ucrt64\bin\gcc.exe`
- **Python**: 3.10+ with `fastapi`, `uvicorn`, `aiohttp`, `discord.py`, `pydantic`
- **C Libraries**: `json-c`, `libcurl` (Discord only), `pthread`. System: `winhttp`, `crypt32`, `ole32`, `gdiplus`, `avicap32`, `ws2_32`.
- **Frontend**: XTerm.js v5, Font Awesome, JetBrains Mono font, Leaflet.js (maps)

---

**Direction: Stay Stealthy. Stay Modular. Stay Server-Side.**
