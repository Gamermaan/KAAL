import React, { useEffect } from 'react';
import Sidebar from './Sidebar';
import WorkspaceArea from './WorkspaceArea';
import { useWindowStore } from '../../store/windowStore';
import { useAgentStore } from '../../store/agentStore';
import { kaalEvents } from '../../services/eventBus';

const Layout = () => {
    const { windows, openWindow } = useWindowStore();
    const { addAgent, updateAgent } = useAgentStore();

    useEffect(() => {
        // Force open dashboard if empty
        if (windows.length === 0) {
            openWindow({ id: 'dashboard', title: 'COMMAND CENTER', type: 'dashboard', closable: false });
        }

        // --- GLOBAL WEBSOCKET CONNECTION ---
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("Global WebSocket Connected");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                // Dispatch to Event Bus for components (like Terminal)
                kaalEvents.emit(data.type, data);

                // Handle global store updates
                const { addTask, updateTaskStatus } = useAgentStore.getState();

                if (data.type === 'agent_registered' || data.type === 'agent_connected') {
                    addAgent(data);
                }
                else if (data.type === 'task_created') {
                    addTask(data.agent_id, {
                        id: data.task_id,
                        command: data.command,
                        status: data.status,
                        timestamp: data.timestamp
                    });
                }
                else if (data.type === 'task_status' || data.type === 'task_ack') {
                    updateTaskStatus(data.agent_id, data.task_id, data.status, { message: data.message });
                }
                else if (data.type === 'task_result') {
                    // Update agent last seen
                    updateAgent({ id: data.agent_id, last_seen: new Date().toISOString() });
                    // Mark task complete
                    updateTaskStatus(data.agent_id, data.task_id, 'completed', { result: data.result });
                }
            } catch (e) {
                console.error("WS Parse Error:", e);
            }
        };

        return () => {
            ws.close();
        };

    }, [windows, openWindow, addAgent, updateAgent]);

    return (
        <div style={{
            width: '100vw',
            height: '100vh',
            background: '#222',
            color: 'white',
            display: 'flex',
            position: 'fixed',
            top: 0,
            left: 0,
            zIndex: 99999
        }}>
            {/* DEBUG MODE - NO EFFECTS */}
            <div style={{ padding: '20px', borderRight: '5px solid red', background: '#333' }}>
                <h3 style={{ color: 'red' }}>SIDEBAR CONTAINER</h3>
                <Sidebar />
            </div>
            <div style={{ flex: 1, padding: '20px', position: 'relative', border: '5px solid blue' }}>
                <h1 style={{ color: 'cyan', fontSize: '32px', background: 'black', padding: '10px' }}>
                    VORTEX DEBUG MODE
                </h1>
                <p>If you see this, React is working.</p>
                <div style={{ border: '5px solid lime', height: '80%', padding: '10px', background: '#111' }}>
                    <h3 style={{ color: 'lime' }}>WORKSPACE CONTAINER</h3>
                    <WorkspaceArea />
                </div>
            </div>
        </div>
    );
};

export default Layout;
