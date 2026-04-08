# KAAL Framework: Development Roadmap

This roadmap outlines the path from the current state (Hybrid Transport PoC with stable GUI) to a production-grade Red Team framework.

---

## ✅ Completed Phases

### Phase 1–3: Foundation & HTTPS Transport
- Initial HTTPS agent tasking
- Protocol V4 implementation
- Agent ↔ Server communication pipeline

### Phase 4: HTTPS Proxy & Core Security
- Standalone HTTPS Proxy (`profiles/https/main.py`) on port 5001
- `X-Internal-Key` header enforcement on all `/api/v1/` endpoints
- Discord Profile updated to inject internal key

### Phase 5: Agent Reconfiguration & Performance
- Agent reconfiguration commands (`config_relay`)
- Performance tuning for chunked data transfer
- Proxy chunk size optimization

### Phase 6: Bug Fixes & GUI Stability
- Screenshot command hang fix
- Terminal tab persistence (CSS display toggling)
- "Clear Queue" functionality
- Reverse shell crash fix (asyncio.gather → asyncio.wait)
- Webcam capture fix
- HTTPS RevShell connection address prompt

---

## 🔲 Phase 7: Advanced Evasion & Persistence (NEXT)
- [ ] **Reflective Loader**: Custom Reflective DLL Loader to run the agent entirely in memory.
- [ ] **API Hashing**: Replace static imports with `GetProcAddress` + `GetModuleHandle` to avoid IAT signatures.
- [ ] **Persistence Modules**: WMI event subscription and Registry run-key persistence.
- [ ] **Sleep Obfuscation**: Encrypt agent memory during sleep intervals to evade memory scanners.

## 🔲 Phase 8: Data Exfiltration & Pivoting
- [ ] **SOCKS5 Proxy**: Implement a SOCKS5 pivot inside the agent to tunnel traffic through the infected host.
- [ ] **Staged Payloads**: Create a 5KB "Dropper" that fetches the main ~230KB HTTPS agent from C2.
- [ ] **Screenshot Interval**: "Spectator Mode" — capture and exfiltrate screens every X seconds.
- [ ] **Process Injection**: Migrate the agent into another process (e.g., explorer.exe).

## 🔲 Phase 9: C2 Intelligence
- [ ] **Automated Deconfliction**: Prevent duplicate agents on the same host (HWID-based UUID).
- [ ] **Transport Library Expansion**: Add Telegram and Slack as first-class transport plugins for the C agent.
- [ ] **Agent Network Visualization**: Show pivot paths and agent topology in the GUI.
- [ ] **React GUI Migration**: Complete the `web/frontend/` React app to replace the monolithic `index.html`.

## 🔲 Phase 10: Operational Security (OPSEC)
- [ ] **Malleable C2 Profiles**: Define traffic patterns to mimic Google Analytics, Windows Update, etc.
- [ ] **Self-Destruct**: "Burn" command that wipes all traces and deletes the agent binary from disk.
- [ ] **Domain Fronting**: Support CDN-based domain fronting for HTTPS transport.
- [ ] **Certificate Pinning**: Pin the C2 server's TLS certificate in the agent to prevent MITM.

---

## 🐛 Bug Backlog (Fix Alongside Any Phase)

| Bug | Location | Severity |
|-----|----------|----------|
| WebSocket `agent_list` re-renders destroy XTerm terminal | `index.html` line ~1324 | High |
| Transport type not shown in agent detail header | `index.html` `renderAgentDetail()` | Low |
| 403 on direct agent → server (bypassing profile proxy) | `server.py` `verify_internal_key` | Medium |
| Monolithic `index.html` (210KB) is unmaintainable | `web/static/index.html` | Medium — long-term |

---

## 🏆 End Vision

A **Plugin-Friendly, Modular C2** that competes with Cobalt Strike, Havoc, and Mythic:
- Dynamic plugin loading (DLLs downloaded and executed in memory)
- BOF (Beacon Object File) support for community extensibility
- Multi-platform agents (Windows, Linux, macOS, Android)
- Beautiful React-based operator GUI with real-time dashboards
