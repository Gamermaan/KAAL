
import sys
import os
import json
import base64

# Add parent dir to path to import standalone_agent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.getcwd())

try:
    # We must suppress print from agent import if possible, but execute_command is static
    from standalone_agent import execute_command
    print("[+] Successfully imported standalone_agent")
except ImportError as e:
    print(f"[-] Failed to import standalone_agent: {e}")
    sys.exit(1)

def test_command(cmd, expected_type):
    print(f"\n[*] Testing command: '{cmd}'...")
    try:
        result_json = execute_command(cmd)
        data = json.loads(result_json)
        
        actual_type = data.get("type", "unknown")
        if actual_type == expected_type:
            print(f"    [PASS] Type matches '{expected_type}'")
            # Print preview
            if "data" in data:
                val = str(data["data"])
                print(f"    [INFO] Data: {val[:50]}...")
            elif "files" in data:
                print(f"    [INFO] Files count: {len(data['files'])}")
            elif "processes" in data:
                print(f"    [INFO] Processes count: {len(data['processes'])}")
            elif "info" in data:
                print(f"    [INFO] System Info: {data['info']}")
            return True
        else:
            print(f"    [FAIL] Expected type '{expected_type}', got '{actual_type}'")
            print(f"    [DEBUG] Raw: {result_json[:200]}...")
            return False
            
    except json.JSONDecodeError:
        print("    [FAIL] Result is NOT valid JSON")
        print(f"    [DEBUG] Raw: {result_json[:200]}...")
        return False
    except Exception as e:
        print(f"    [FAIL] Exception: {e}")
        return False

def main():
    print("=== STARTING PHASE 1 VERIFICATION ===")
    tests = [
        ("system_info", "system_info"),
        ("process_list", "process_list"),
        ("file_list .", "file_list"),
        ("ipconfig", "text"),
        ("ping 127.0.0.1", "text"),
        ("whoami", "text"), 
        ("pwd", "text"),
    ]
    
    passed = 0
    for cmd, type_ in tests:
        if test_command(cmd, type_): passed += 1
        
    print(f"\n[=] Tests Completed: {passed}/{len(tests)} Passed")

if __name__ == "__main__":
    main()
