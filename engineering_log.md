# KAAL Framework: Engineering & Problem Log

A record of architectural decisions and the "whys" behind the current codebase.

## 🛑 Problem: MinGW Type Redefinition Errors
- **Symptom**: `DWORD`, `WINBOOL`, and `HANDLE` being "redefined" or "not found" during compilation.
- **Root Cause**: The inclusion of `psapi.h` or `shlwapi.h` before `windows.h`, or `windows.h` before `winsock2.h`. 
- **Solution**: Enforced a strict header block in `agent.c`. Note that some IDEs "auto-format" and group headers alphabetically—**this breaks the build**. 
- **Patching**: We use a `python` script in the builder to ensure the correct order is always written to the build source.

## 🛑 Problem: SSL Connection Failures in C
- **Symptom**: `libcurl` failing to verify C2 certificates or increasing agent size by 2MB via OpenSSL dependencies.
- **Decision**: Dropped `libcurl` from the core HTTPS transport.
- **Solution**: Switched to `WinHTTP`. It uses the Windows Certificate Store, handles TLS 1.2/1.3 natively, and adds **zero bytes** to the agent because it's a system DLL.

## 🛑 Problem: Discord Message Rate Limits
- **Symptom**: Bot being blocked when 5+ agents talk simultaneously on `#general`.
- **Solution**: Implemented **Per-Agent Channels**. 
    - The server creates a unique private channel for every new `agent_id`.
    - The server provisions a **Webhook** for that channel and sends it to the agent.
    - Agents use the Webhook to SEND (bypassing bot limits) and the Channel API to RECV.

## 🛑 Problem: Binary Bloat (CRT)
- **Symptom**: A simple "Hello World" in C being 50KB+.
- **Optimization**: The HTTPS agent uses `WinHTTP` and `CryptoAPI`. When compiled with `-Os` (size optimization) and `-nostdlib` (carefully applied), the payload is significantly reduced. Current build uses standard UCRT but remains lean by avoiding heavy libraries.

## 🛑 Problem: Task Synchronization
- **Symptom**: Multiple tasks sent to an agent arriving out of order or being missed.
- **Solution**: **Task IDs and Sequence Numbers**. Every command from the server has a unique `task_id`. The agent tracks the last executed `seq` and the server ignores duplicate results.
## 🛑 Hard Truths & Technical Debt
- **ConPTY Complexity**: The interactive shell (`shell_start`) uses Windows Pseudoconsoles. It is extremely sensitive to handle counts and pipe redirection. Do not refactor this without a heavy verification phase.
- **Binary Overwrites**: The `build_agent.py` script generates `agent_build_temp.c`. Any manual edits to that temp file will be wiped on the next build. Always edit the source `agent.c` or transport plugins.
- **Async Drift**: The Discord Gateway and the FastAPI server run in separate processes/loops. Communication between them relies on the `kaal.db` and the `ChannelManager` JSON file. Be aware of race conditions during agent registration.

## 📦 Environment Manifest
- **Compiler**: MinGW-w64 (UCRT64) via MSYS2.
- **Python**: 3.10+ with `aiohttp`, `discord.py`, `pydantic`, `sqlalchemy`.
- **Libraries (Windows Build)**: `json-c`, `libcurl` (Discord only), `pthread`. System libraries used: `winhttp`, `crypt32`, `ole32`, `gdiplus`, `avicap32`, `ws2_32`.
