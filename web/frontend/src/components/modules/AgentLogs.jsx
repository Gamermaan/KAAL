import React, { useEffect, useState, useRef } from 'react';
import { kaalEvents } from '../../services/eventBus';

const AgentLogs = ({ agentId }) => {
    const [logs, setLogs] = useState([]);
    const logsEndRef = useRef(null);

    useEffect(() => {
        // Initial Fetch (If backend supported it, for now we just rely on real-time)
        // In a real app, you'd fetch the last 100 logs here.

        const unsubscribe = kaalEvents.on('agent_log', (data) => {
            if (data.agent_id !== agentId) return;
            setLogs(prev => {
                const newLogs = [...prev, data.log];
                if (newLogs.length > 200) newLogs.shift();
                return newLogs;
            });
        });

        return () => unsubscribe();
    }, [agentId]);

    useEffect(() => {
        logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [logs]);

    const getLevelColor = (level) => {
        switch (level.toUpperCase()) {
            case 'ERROR': return 'text-red-500';
            case 'WARNING': return 'text-yellow-500';
            case 'INFO': return 'text-blue-400';
            case 'DEBUG': return 'text-gray-500';
            default: return 'text-white';
        }
    };

    return (
        <div className="h-full flex flex-col bg-[#0f0f23] text-gray-300 font-mono text-xs">
            <div className="flex-none p-2 border-b border-white/10 flex justify-between items-center bg-[#1a1a2e]">
                <span className="font-bold text-cyan-500">SYSTEM_LOGS</span>
                <button onClick={() => setLogs([])} className="text-gray-500 hover:text-white transition-colors">CLEAR</button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-1">
                {logs.length === 0 ? (
                    <div className="text-gray-600 italic">Waiting for incoming logs...</div>
                ) : (
                    logs.map((log, idx) => (
                        <div key={idx} className="flex gap-2">
                            <span className="text-gray-500 shrink-0">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                            <span className={`shrink-0 font-bold ${getLevelColor(log.level)}`}>[{log.level}]</span>
                            <span className="break-all">{log.message}</span>
                        </div>
                    ))
                )}
                <div ref={logsEndRef} />
            </div>
        </div>
    );
};

export default AgentLogs;
