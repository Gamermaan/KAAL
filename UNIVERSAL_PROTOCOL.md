# KAAL Universal Agent Protocol (v4.1)

This document dictates the strict communication schema that **all** KAAL agents (Windows, Linux, macOS, Android, iOS) MUST adhere to when communicating with the Central C2 Server, regardless of the transport relay (Discord, Telegram, direct HTTP).

Failure to adhere to these schemas will result in the Python C2 Router dropping the telemetry.

---

## 1. Transport Layer (Profile Dependent)

Depending on the C2 profile chosen, the raw transmission format differs, but the inner JSON remains identical.

**Discord Profile Example:**
Messages sent to Discord must be prefixed with `KAAL_AGT:` followed by a Base64 encoded string containing the Agent ID and the core JSON payload separated by a colon.
`KAAL_AGT:base64("agent_id:{\"type\": \"...\"}")`

**Direct HTTP Example:**
Agents interacting with the server directly send pure JSON POST requests to `/api/v1/agent_message`.

---

## 2. Core JSON Top-Level Schema

*Every* JSON payload emitted by any agent must contain at minimum:
```json
{
  "agent_id": "unique-agent-identifier",
  "type": "MESSAGE_TYPE"
}
```

### Supported Message Types (`type`)
1. `register`: First communication upon execution.
2. `heartbeat`: Periodic check-in to confirm the agent is alive.
3. `ack`: Acknowledgment that a command was received.
4. `result`: Final output of an executed command.
5. `status`: Intermediate status updates during long-running tasks.
6. `chunk`: Data blocks for large file exfiltration.

---

## 3. Detailed Message Schemas

### 3.1 Registration (`type: "register"`)
Sent once when the agent boots up. If the server receives a message from an unknown agent *without* seeing a register first, the server will "Auto-Register" it robustly, but explicit registration provides rich OS details.

**Payload:**
```json
{
  "agent_id": "win-agent-1234",
  "type": "register",
  "platform": "windows",    // "windows", "linux", "macos", "android", "ios"
  "hostname": "DESKTOP-XYZ" // System hostname or device name
}
```

### 3.2 Heartbeat (`type: "heartbeat"`)
Sent periodically based on the sleep interval. Used by the server to update the `last_seen` timestamp. No extra data is required.

**Payload:**
```json
{
  "agent_id": "win-agent-1234",
  "type": "heartbeat",
  "data": {} // Optional padding
}
```

### 3.3 Acknowledgment (`type: "ack"`)
Sent immediately after parsing an incoming task, BEFORE execution begins. This updates the task status in the GUI from "pending" to "acknowledged".

**Payload:**
```json
{
  "agent_id": "win-agent-1234",
  "type": "ack",
  "task_id": "abcd1234_uuid_here" // Must match the received command's task_id
}
```

### 3.4 Command Result (`type: "result"`)
Sent when a command finishes execution. The output is placed in the `result` field. The output can be either a string (terminal output) or a structured JSON object (e.g., file arrays).

**Payload:**
```json
{
  "agent_id": "win-agent-1234",
  "type": "result",
  "task_id": "abcd1234_uuid_here",
  "result": {
    "type": "text", // e.g., "text", "file_list", "process_list", "screenshot"
    "data": {
       "text": "Volume in drive C has no label..."
    }
  }
}
```
*CRITICAL:* The C2 server looks explicitly for the `"result"` key at the top level to broadcast the output to the frontend.

### 3.5 Intermediate Status (`type: "status"`)
Sent to update the human operator on the progress of long-running operations.

**Payload:**
```json
{
  "agent_id": "win-agent-1234",
  "type": "status",
  "task_id": "abcd1234_uuid_here",
  "status": "processing",   // e.g., "processing", "downloading", "error"
  "message": "Downloaded 50/100 MB..."
}
```

### 3.6 Chunked Exfiltration (`type: "chunk"`)
Used to upload files larger than Discord/Telegram API limits. The server reassembles these dynamically based on the `stream_id`.

**Payload:**
```json
{
  "agent_id": "win-agent-1234",
  "type": "chunk",
  "task_id": "abcd1234_uuid_here",
  "stream_id": "stream_uuid", // Unique ID for this specific file transfer session
  "index": 0,                 // 0-based index of this chunk
  "total": 5,                 // Total number of chunks expected
  "data": "base64_encoded_binary_chunk_here"
}
```

---

## 4. Server-Side Robustness

To ensure massive stability across heterogeneous agent deployments, the KAAL server implements the following fail-safes:

- **Missing Registration:** If an agent skips `$register` and fires a `$result` directly, the server will **Auto-Register** the UUID as "Unknown OS" but still process the telemetry to prevent data loss.
- **Malformed Serialization:** If an agent forgets to wrap its output in a proper JSON object and just sends a raw string for `$result`, the Python parser will gracefully intercept the JSONDecodeError, wrap the string internally as a `text` type, and broadcast it to the GUI safely.
- **Dropped Task IDs:** If an agent's parser crashes and it strips the `task_id` from the return payload, the server falls back to `'unknown'` and drops the response in a global agent log channel preventing a backend database crash.
