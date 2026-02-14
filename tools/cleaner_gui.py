import tkinter as tk
from tkinter import messagebox, scrolledtext
import os
import sys
import subprocess
import winreg
import shutil
import psutil
from pathlib import Path

class KaalCleaner:
    def __init__(self, root):
        self.root = root
        self.root.title("Kaal Agent Cleaner (Test Environment)")
        self.root.geometry("500x400")
        
        # UI Elements
        tk.Label(root, text="Kaal Agent Cleaner", font=("Arial", 16, "bold")).pack(pady=10)
        
        self.log_area = scrolledtext.ScrolledText(root, height=15)
        self.log_area.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="Scan System", command=self.scan, width=15, bg="#dddddd").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Clean All", command=self.clean_all, width=15, bg="#ffcccc", fg="red").pack(side=tk.LEFT, padx=5)
        
        self.log("Ready to scan.")

    def log(self, msg):
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)

    def scan(self):
        self.log("[*] Scanning for artifacts...")
        found = False
        
        # Safety Check: Am I on the Host?
        if os.path.exists("config.yaml") and os.path.exists("core"):
            self.log("[!] WARNING: HOST ENVIRONMENT DETECTED!")
            self.log("[!] This tool is meant for VICTIM machines.")
            self.log("[!] creation/deletion of framework files is disabled.")
            self.is_host = True
        else:
            self.is_host = False
        
        # Check Process
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Target specifically the compiled agent name or the test script
                name = proc.info['name'].lower()
                if name in ["kaal_agent.exe", "test_agent.exe", "test_agent_direct.exe"]:
                    self.log(f"[!] Found Agent Process: {name} (PID: {proc.info['pid']})")
                    found = True
                elif "python" in name:
                    # Check cmdline for script name
                    cmdline = " ".join(proc.info['cmdline'] or []).lower()
                    if "test_agent_direct.py" in cmdline:
                         self.log(f"[!] Found Test Agent Script: {proc.info['pid']}")
                         found = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        # Check Files (Specific locations)
        # Real Agent usually installs to AppData or Temp
        temp_dir = Path(os.getenv('TEMP')) / "KaalAgent"
        if temp_dir.exists():
             self.log(f"[!] Found Agent Data: {temp_dir}")
             found = True

        appdata_dir = Path(os.getenv('APPDATA')) / "Kaal"
        if appdata_dir.exists():
             self.log(f"[!] Found Persistence Dir: {appdata_dir}")
             found = True
            
        if not found:
            self.log("[+] System appears clean.")

    def clean_all(self):
        if self.is_host:
            if not messagebox.askyesno("Safety Warning", "You appear to be on the HOST machine. This attempts to kill agent processes but will SKIP file deletion to protect your framework. Continue?"):
                return
        else:
            if not messagebox.askyesno("Confirm", "Wipe all Kaal Agent artifacts from this machine?"):
                return
            
        self.log("[*] Starting cleanup...")
        
        # 1. Kill Processes
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info['name'].lower()
                cmdline = " ".join(proc.info['cmdline'] or []).lower()
                
                target = False
                if name in ["kaal_agent.exe", "test_agent.exe"]: target = True
                if "python" in name and "test_agent_direct.py" in cmdline: target = True
                
                if target:
                    self.log(f"[-] Killing {name} (PID: {proc.info['pid']})")
                    proc.kill()
            except:
                pass
                
        # 2. Remove Files (Only if not host, or strictly specific paths)
        if not self.is_host:
            paths_to_remove = [
                Path(os.getenv('TEMP')) / "KaalAgent",
                Path(os.getenv('APPDATA')) / "Kaal",
                Path.home() / ".kaal" # Be careful with this one
            ]
            
            for p in paths_to_remove:
                if p.exists():
                    try:
                        shutil.rmtree(p)
                        self.log(f"[-] Removed: {p}")
                    except Exception as e:
                        self.log(f"[!] Error removing {p}: {e}")
        else:
            self.log("[*] Skipped file deletion (Host Safety Mode)")

        # 3. Remove Persistence
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
            try:
                winreg.DeleteValue(key, "KaalAgent")
                self.log("[-] Removed Registry Key: KaalAgent")
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception as e:
            self.log(f"[!] Registry: {e}")

        self.log("[+] Cleanup complete.")
        messagebox.showinfo("Done", "Cleanup finished.")

if __name__ == "__main__":
    # Check Admin - simplified, cleaner usually needs rights if agent installed as admin
    # if not ctypes.windll.shell32.IsUserAnAdmin(): ...
    
    root = tk.Tk()
    app = KaalCleaner(root)
    root.mainloop()
