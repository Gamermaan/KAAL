
import asyncio
import json
import websockets
import aiohttp
import sys

# Mock Agent ID
AGENT_ID = "test-agent-phase2"
API_URL = "http://localhost:5000/api"
WS_URL = "ws://localhost:5000/ws"

async def mock_frontend():
    async with websockets.connect(WS_URL) as ws:
        print("[Frontend] Connected to WS")
        
        # Authenticate/Init
        await ws.send(json.dumps({"type": "init"}))
        
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                
                if data.get("type") == "task_created":
                    print(f"[Frontend] EVENT: Task Created -> ID: {data.get('task_id')}")
                elif data.get("type") == "task_status":
                    print(f"[Frontend] EVENT: Task Status -> {data.get('status')} ({data.get('message')})")
                    if data.get("status") == "acknowledged":
                        print("[PASS] Received ACK event")
                    elif data.get("status") == "processing":
                        print("[PASS] Received STATUS event")
                elif data.get("type") == "task_result":
                    print(f"[Frontend] EVENT: Task Result -> {str(data.get('result'))[:20]}...")
                    print("[PASS] Received RESULT event")
                    return # Test Complete
            except websockets.exceptions.ConnectionClosed:
                break

async def mock_agent_flow():
    await asyncio.sleep(2) # Wait for WS
    
    async with aiohttp.ClientSession() as session:
        # Register
        print("[Agent] Registering...")
        await session.post(f"{API_URL}/v1/register", json={"agent_id": AGENT_ID, "hostname": "TEST_HOST"})
        
        # Send Command (as Operator)
        print("[Operator] Sending Command...")
        async with session.post(f"{API_URL}/command", json={"agent_id": AGENT_ID, "command": "whoami"}) as resp:
            data = await resp.json()
            task_id = data.get("task_id")
            print(f"[Operator] Command Sent. Task ID: {task_id}")
            
        await asyncio.sleep(1)
        
        # Agent: Poll (Task Fetch)
        # Note: Server now pushes via C2 response or standalone get_task. Let's use get_task.
        # But wait, send_command queues it. 
        # Server.py line 201 pops task. 
        # And endpoint handle_agent_message handles popping too.
        
        # Agent: Fetch Task via C2 Message (Simulate Poll)
        print("[Agent] Polling for tasks (via C2 message)...")
        async with session.post(f"{API_URL}/v1/agent_message", json={"type": "heartbeat", "agent_id": AGENT_ID}) as resp:
            data = await resp.json()
            tasks = data.get("tasks", [])
            if tasks:
                tid = tasks[0]["task_id"]
                print(f"[Agent] Got Task: {tid}")
                
                # Agent: Send ACK
                print("[Agent] Sending ACK...")
                await session.post(f"{API_URL}/v1/agent_message", json={"type": "ack", "agent_id": AGENT_ID, "task_id": tid})
                await asyncio.sleep(0.5)

                # Agent: Send Status
                print("[Agent] Sending Status...")
                await session.post(f"{API_URL}/v1/agent_message", json={"type": "status", "agent_id": AGENT_ID, "task_id": tid, "status": "processing", "message": "Working..."})
                await asyncio.sleep(0.5)

                # Agent: Send Result
                print("[Agent] Sending Result...")
                await session.post(f"{API_URL}/v1/agent_message", json={"type": "result", "agent_id": AGENT_ID, "task_id": tid, "result": "root"})
                
            else:
                print("[Agent] No tasks found!")

async def main():
    # Start both
    await asyncio.gather(
        mock_frontend(),
        mock_agent_flow()
    )

if __name__ == "__main__":
    # Check dependencies
    try:
        import websockets
        import aiohttp
        asyncio.run(main())
    except ImportError:
        print("Please install websockets and aiohttp: pip install websockets aiohttp")
