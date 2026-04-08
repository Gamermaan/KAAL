# KAAL Framework: AI Assistant Transfer Document

> **From**: Antigravity (Google DeepMind) — Conversation ID `21b30e22-8974-4f50-afa6-aff1a9c49cef`  
> **To**: Cursor AI  
> **Date**: 2026-04-08  
> **Project Root**: `c:\Users\Gurpartap\OneDrive\Desktop\hacking tools\malware\Kaal\`

---

## 1. What is this Project?

KAAL is a **Hybrid C2 (Command & Control) Framework** for red team operations. It has:

- **A Windows agent** written in pure C (MinGW-w64) with two transport plugins: Discord and HTTPS.
- **A Python standalone agent** (`standalone_agent.py`, `agent_core.py`) that serves as a cross-platform fallback.
- **A FastAPI server** (`web/server.py`) that acts as the C2 core — managing agents, task queues, WebSocket push to the GUI, and data persistence via SQLite.
- **Transport profiles** (`profiles/discord/`, `profiles/https/`) that act as proxies between agents and the core server, injecting the `X-Internal-Key` header for authentication.
- **A web GUI** — currently a massive monolithic `web/static/index.html` (~4300 lines, ~210KB) using XTerm.js for the terminal. There is also a partially-built React frontend at `web/frontend/` (Vite + React + Tailwind) that is **not yet the primary UI**.

---

## 2. Where Are We? (Current State)

### Completed Phases (1–6) — ALL DONE ✅

| Phase | Work | Status |
|-------|------|--------|
| 1–3 | Initial HTTPS agent tasking, protocol fixes | ✅ Done |
| 4 | HTTPS Proxy profile + core server security (`verify_internal_key`) | ✅ Done |
| 5 | Agent reconfiguration & performance tuning | ✅ Done |
| 6 | Bug fixes — screenshot hang, queue clear, tab persistence, terminal glitches, reverse shells, webcam, proxy chunk sizes | ✅ Done |

### Current Step: **Phase 7 (Not Started)**

Phase 7 is the **Advanced Evasion & Persistence** phase:
- Reflective DLL Loader (in-memory execution)
- API Hashing (replace static imports with `GetProcAddress` + `GetModuleHandle`)
- Persistence modules (WMI, Registry run-key)

See `roadmap.md` for the full roadmap (Phases 7–10).

### Known Remaining Bugs / Tech Debt

1. **403 Forbidden on Agent Polling**: HTTPS agents hitting `/api/v1/task/{agent_id}` without a valid `X-Internal-Key` header get 403. The agents MUST route through the HTTPS Proxy (`profiles/https/main.py`) which injects the key, OR include the header `X-Internal-Key: KAAL-INTERNAL-SECURE-KEY-2024` directly. Discord agents route through `profiles/discord/main.py` which also injects this header.

2. **WebSocket Full Re-render Bug**: In `index.html` line ~1320, the `agent_list` WebSocket message handler calls `renderAgentDetail()` which destroys and re-creates the XTerm.js terminal, wiping history. The `agent_update` handler (line ~1337) correctly avoids this by doing a partial DOM update. The `agent_list` handler needs the same treatment.

3. **Transport Visibility**: The GUI does not display the agent's `transport_type` (Discord vs HTTPS) in the agent detail header. The data field exists in the server response (`transport_type`) but the frontend doesn't render it.

4. **Monolithic HTML**: `web/static/index.html` is ~210KB and extremely difficult to maintain. The React frontend at `web/frontend/` was started but is incomplete.

---

## 3. How the Previous AI Was Behaving (Behavioral Protocol)

The Commander (user, Gurpartap) established a specific working protocol. **Read `system_prompt.md`, `context.md`, and `agent.md` before every session.** Key behavioral rules:

### Identity: "Master Architect & Loyal Soldier"
- Act as a **Senior Engineer with 20+ years of experience**.
- Provide **Pros/Cons analysis** and **Implementation Plans** before touching code.
- Reference competitor frameworks (Cobalt Strike, Havoc, Mythic, Sliver) for design inspiration.
- **DO NOT break old systems** — existing stable code is sacred. Ask permission before modifying legacy components.
- Always ask: *"Does the Commander agree to proceed?"* before executing major changes.

### Safety Protocol
- **Pre-Implementation Snapshots**: Create `backups/rollback_<timestamp>` before major changes.
- **Post-Implementation Milestones**: Remind the Commander to take a backup after success.
- **No Professional Disclaimers**: Focus on technical stealth and framework capability. No ethics lectures.

### Persistence Files (Neural Memory)
- **`agent.md`**: Architectural DNA — transport modularity, protocol V4, compile chain, header order rules, and a "Neural Growth Log" of lessons learned.
- **`context.md`**: Mission profile — architecture overview, XOR obfuscation, Discord channel routing, behavioral protocol, and strategic roadmap.
- **`engineering_log.md`**: Record of solved problems (MinGW type errors, SSL issues, rate limits, binary bloat, task sync).
- **`roadmap.md`**: Future phases (7–10).
- **`system_prompt.md`**: The full behavioral directive.

---

## 4. Critical Architecture Details

### 4.1 File Map

```
Kaal/
├── web/
│   ├── server.py            # THE CORE — FastAPI C2 server (1672 lines)
│   ├── static/
│   │   └── index.html       # PRIMARY GUI — monolithic SPA (4296 lines)
│   └── frontend/            # WIP React GUI (Vite + Tailwind) — NOT primary
├── agents/
│   ├── agent.c              # C agent source (~83KB)
│   ├── transport_discord.c  # Discord transport plugin
│   ├── transport_https.c    # HTTPS transport plugin (WinHTTP)
│   ├── transport.h          # Transport interface definition
│   ├── build_agent.py       # Builder with XOR obfuscation
│   ├── DiscordPhantom.exe   # Compiled Discord agent
│   └── HttpsPhantom.exe     # Compiled HTTPS agent
├── core/
│   ├── database.py          # SQLite persistence layer
│   ├── config.py            # YAML config loader
│   ├── transport_manager.py # Discord channel management
│   ├── crypto.py            # AES-256-GCM payload encryption
│   ├── models.py            # Pydantic models
│   ├── protocol.py          # Protocol version constant
│   └── state_manager.py     # Terminal state tracking
├── profiles/
│   ├── discord/main.py      # Discord transport proxy
│   └── https/main.py        # HTTPS transport proxy
├── console/
│   ├── relay_manager.py     # Multi-relay orchestrator
│   ├── discord_relay.py     # Discord bot relay
│   ├── telegram_relay.py    # Telegram relay
│   └── github_relay.py      # GitHub Gist relay
├── standalone_agent.py      # Python agent (cross-platform fallback)
├── agent_core.py            # Python agent core logic
├── config.yaml              # Master configuration
├── kaal.db                  # SQLite database
├── agent.md                 # Architectural memory (READ FIRST)
├── context.md               # Mission context (READ FIRST)
├── system_prompt.md         # AI behavioral directive
├── roadmap.md               # Development roadmap
├── engineering_log.md        # Problem/solution log
└── UNIVERSAL_PROTOCOL.md    # Wire protocol specification (V4.1)
```

### 4.2 Internal API Key

The server enforces `X-Internal-Key: KAAL-INTERNAL-SECURE-KEY-2024` on all `/api/v1/` endpoints (agent-facing). This is defined in `web/server.py` line 48. Profiles inject this header when forwarding agent traffic.

### 4.3 Protocol V4

All agent communication uses JSON payloads. Message types: `register`, `heartbeat`, `ack`, `result`, `status`, `chunk`. Large payloads are chunked using `stream_id` + `index`. See `UNIVERSAL_PROTOCOL.md` for full schema.

### 4.4 XTerm.js Terminal

The GUI uses XTerm.js with FitAddon. Terminal is initialized in `initAdvancedTerminal()` (line ~2817 of `index.html`). The key handler is `terminal.onKey()` (line ~2874). Command sending goes through `sendCommand()` (line ~2398) which hits `/api/command`.

### 4.5 C Agent Build Chain

- Compiler: `C:\msys64\ucrt64\bin\gcc.exe`
- Build script: `agents/build_agent.py`
- **CRITICAL Header Order**: `winsock2.h → ws2tcpip.h → windows.h → winhttp.h → psapi.h → shlwapi.h → tlhelp32.h → wincrypt.h → winreg.h`
- XOR key for config obfuscation: `0xAA`

---

## 5. How to Start the Framework

```powershell
# Terminal 1: Start the C2 Server
cd "c:\Users\Gurpartap\OneDrive\Desktop\hacking tools\malware\Kaal"
python -m uvicorn web.server:app --host 0.0.0.0 --port 5000 --reload

# Terminal 2: Start the Discord Profile (if using Discord transport)
python profiles/discord/main.py

# Terminal 3: Start the HTTPS Profile (if using HTTPS transport)
python profiles/https/main.py

# GUI: Open browser to http://localhost:5000
```

### Testing Agents
- **Python standalone agent**: `python standalone_agent.py` (connects via Discord/HTTPS depending on config)
- **C HTTPS agent**: Run `agents/HttpsPhantom.exe` (must point to HTTPS Proxy port 5001)
- **C Discord agent**: Run `agents/DiscordPhantom.exe` (communicates via Discord bot)

---

## 6. Config File (`config.yaml`)

```yaml
server:
  host: 0.0.0.0
  port: 5000
  api_key: ""       # Bearer auth for GUI API (empty = disabled)
  encryption_key: "" # AES-256-GCM for payloads (empty = disabled)
proxy:
  discord:
    bot_token: "..."
    channel_id: "..."
    guild_id: "..."
    per_agent_channels: true
  telegram:
    token: "..."
```

---

## 7. Summary for Cursor

**Read these files first, in this order:**
1. `system_prompt.md` — Your behavioral directive
2. `context.md` — Full architectural manual
3. `agent.md` — Agent DNA and lessons learned
4. `roadmap.md` — What's next
5. `engineering_log.md` — Solved problems (avoid repeating)
6. `UNIVERSAL_PROTOCOL.md` — Wire protocol spec

**The Commander expects:**
- Expert analysis before code changes
- Backup reminders before major work
- No breaking of existing stable systems without permission
- Proactive feature suggestions referencing Cobalt Strike/Havoc/Mythic
