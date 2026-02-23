import os

path = r"c:\Users\Gurpartap\OneDrive\Desktop\hacking tools\malware\Kaal\standalone_agent.py"
with open(path, "r", encoding="utf-8") as f:
    code = f.read()

replacements = [
    ('print(f"[*] Loading configuration from {config_path}")', 'logger.info(f"Loading configuration from {config_path}")'),
    ('print(f"[-] Failed to load config: {e}")', 'logger.error(f"Failed to load config: {e}")'),
    ('print("[*] No config file found. Using internal defaults.")', 'logger.info("No config file found. Using internal defaults.")'),
    ('print(f"[♥] (Discord C2) {time.strftime(\'%H:%M:%S\')}")', 'logger.debug(f"[♥] (Discord C2)")'), 
    ('print(f"[*] Rate Limited (429). Sleeping {retry_after}s...")', 'logger.warning(f"Rate Limited (429). Sleeping {retry_after}s...")'),
    ('print(f"[*] Result too large ({len(result)} bytes). Splitting into {total_chunks} chunks (Stream {stream_id})...")', 'logger.info(f"Result too large ({len(result)} bytes). Splitting into {total_chunks} chunks (Stream {stream_id})...")'),
    ('print(f"[*] Stream {stream_id} complete.")', 'logger.info(f"Stream {stream_id} complete.")'),
    ('print(f"[*] Result too large ({len(encoded)} bytes). Uploading as attachment...")', 'logger.info(f"Result too large ({len(encoded)} bytes). Uploading as attachment...")'),
    ('print("[*] Interactive shell started")', 'logger.info("Interactive shell started")'),
    ('print(f"[-] Shell start failed: {e}")', 'logger.error(f"Shell start failed: {e}")'),
    ('print(f"[-] Shell write error: {e}")', 'logger.error(f"Shell write error: {e}")'),
    ('print(f"[-] Loop error: {e}")', 'logger.error(f"Loop error: {e}")')
]

for old, new in replacements:
    code = code.replace(old, new)

with open(path, "w", encoding="utf-8") as f:
    f.write(code)
print("Done")
