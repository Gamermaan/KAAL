import random
import re
import string

class RuleGenerator:
    """Rule‑based source code transformation to enhance compatibility and evade static signatures."""
    def __init__(self):
        self.winapi_names = [
            'dwResult', 'hProcess', 'lpBuffer', 'cbData', 'hKey', 'dwThreadId',
            'lpParameter', 'hModule', 'hFile', 'dwBytesRead', 'lpOverlapped',
            'phResult', 'lpData', 'dwFlags', 'lpFileName'
        ]

    def rename_vars(self, code: str) -> str:
        """Rename variables to realistic Windows API style."""
        lines = code.split('\n')
        var_map = {}
        for line in lines:
            m = re.search(r'\b(DWORD|HANDLE|LPVOID|BOOL|int|char\*?|void\*)\s+([a-zA-Z_][a-zA-Z0-9_]+)', line)
            if m:
                old_name = m.group(2)
                if old_name not in var_map and len(old_name) > 2:
                    new_name = random.choice(self.winapi_names) + str(random.randint(10,99))
                    var_map[old_name] = new_name
        for old, new in var_map.items():
            code = re.sub(r'\b' + old + r'\b', new, code)
        return code

    def reorder_funcs(self, code: str) -> str:
        """Shuffle function order (except main/WinMain/DllMain)."""
        lines = code.split('\n')
        funcs = []
        current = []
        in_func = False
        for line in lines:
            if re.match(r'^(BOOL|DWORD|VOID|int|void|HANDLE|LPVOID)\s+\w+\s*\(', line.strip()):
                if in_func and current:
                    funcs.append('\n'.join(current))
                current = [line]
                in_func = True
            elif in_func:
                current.append(line)
                if line.strip() == '}':
                    funcs.append('\n'.join(current))
                    current = []
                    in_func = False
        if current:
            funcs.append('\n'.join(current))

        main_func = None
        others = []
        for f in funcs:
            if 'main(' in f or 'WinMain' in f or 'DllMain' in f:
                main_func = f
            else:
                others.append(f)
        random.shuffle(others)
        ordered = others + ([main_func] if main_func else [])
        return '\n\n'.join(ordered)

    def insert_deadcode(self, code: str) -> str:
        """Insert harmless opaque predicates and dummy operations."""
        dead_templates = [
            '\n    if (1) {{ int x = 0x{0:04x}; x ^= x; }}\n',
            '\n    {{ volatile DWORD dw = GetTickCount(); dw = dw ^ dw; }}\n',
            '\n    {{ MEMORYSTATUSEX ms; ms.dwLength = sizeof(ms); GlobalMemoryStatusEx(&ms); }}\n',
            '\n    {{ SYSTEM_INFO si; GetSystemInfo(&si); }}\n',
            '\n    for (int i = 0; i < 10; i++) {{ int j = i * i; }}\n'
        ]
        lines = code.split('\n')
        pos = random.randint(0, len(lines)-1)
        dead = random.choice(dead_templates).format(random.randint(1000,9999))
        lines.insert(pos, dead)
        return '\n'.join(lines)

    def encrypt_strings(self, code: str) -> str:
        """Replace string literals with XOR‑encrypted versions and a decryption stub."""
        pattern = r'"((?:\\.|[^"\\])*)"'
        def replacer(match):
            s = match.group(1)
            if len(s) < 4 or s.startswith('\\x'):
                return match.group(0)
            key = random.randint(1, 255)
            enc = ''.join(chr(ord(c) ^ key) for c in s)
            stub = f'_decrypt_xor("{enc}", {len(s)}, {key})'
            return stub
        if '_decrypt_xor' not in code:
            decryptor = '''
void _decrypt_xor(char* s, int len, char key) {
    for(int i=0; i<len; i++) s[i] ^= key;
}
'''
            code = decryptor + '\n' + code
        return re.sub(pattern, replacer, code)
