import React, { useState, useEffect } from 'react';
import { Cpu, RefreshCw, Trash2, ShieldAlert } from 'lucide-react';
import { sendCommand } from '../../services/api';
import { kaalEvents } from '../../services/eventBus';

const ProcessManager = ({ agentId }) => {
    const [processes, setProcesses] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        const unsubscribe = kaalEvents.on('task_result', (data) => {
            if (data.agent_id !== agentId) return;

            let parsed = null;
            try {
                if (typeof data.result === 'string' && (data.result.startsWith('{') || data.result.startsWith('['))) {
                    parsed = JSON.parse(data.result);
                } else if (typeof data.result === 'object') {
                    parsed = data.result;
                }
            } catch (e) { /* Not JSON */ }

            if (parsed && parsed.type === 'process_list') {
                if (parsed.processes) {
                    setProcesses(parsed.processes);
                }
                setLoading(false);
            } else if (parsed && parsed.type === 'error') {
                setError(parsed.data || "Unknown Error");
                setLoading(false);
            }
        });

        loadProcesses();
        return () => unsubscribe();
    }, [agentId]);

    const loadProcesses = async () => {
        setLoading(true);
        setError(null);
        try {
            await sendCommand(agentId, "ps");
        } catch (err) {
            setError("Failed to request process list: " + err.message);
            setLoading(false);
        }
    };

    const killProcess = async (pid) => {
        if (!window.confirm(`Are you sure you want to KILL process ${pid}?`)) return;
        try {
            setLoading(true);
            await sendCommand(agentId, `kill ${pid}`);
            // Optimistic update or wait for refresh? kill command doesn't return process list.
            // But we should refresh after a delay.
            setTimeout(() => loadProcesses(), 2000);
        } catch (err) {
            setError("Failed to kill process: " + err.message);
            setLoading(false);
        }
    };

    return (
        <div className="bg-bg-secondary border border-border rounded-lg p-5 shadow-lg h-full flex flex-col">
            {/* Toolbar */}
            <div className="flex items-center justify-between mb-4 bg-bg-tertiary p-3 rounded-lg border border-border">
                <div className="flex items-center space-x-2">
                    <Cpu className="w-5 h-5 text-accent-primary" />
                    <span className="font-bold text-text-primary tracking-wider">ACTIVE PROCESSES</span>
                    <span className="bg-bg-secondary text-text-secondary text-xs px-2 py-1 rounded-full border border-border">
                        {processes.length} items
                    </span>
                </div>
                <button onClick={loadProcesses} className="bg-accent-primary hover:bg-green-400 text-bg-primary px-4 py-2 rounded-md text-sm font-semibold flex items-center shadow-[0_0_10px_rgba(0,255,159,0.2)] transition-all">
                    <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </button>
            </div>

            {/* Process List */}
            <div className="flex-1 border border-border rounded-lg bg-bg-primary overflow-hidden relative">
                {loading && processes.length === 0 && (
                    <div className="absolute inset-0 bg-bg-primary/80 flex items-center justify-center z-10">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary"></div>
                    </div>
                )}

                {error ? (
                    <div className="p-6 text-error flex flex-col items-center justify-center h-full">
                        <div className="bg-error/10 p-3 rounded-full mb-2"><ShieldAlert className="w-6 h-6" /></div>
                        {error}
                    </div>
                ) : (
                    <div className="overflow-auto h-full">
                        <table className="w-full text-sm">
                            <thead className="bg-bg-tertiary text-left sticky top-0 z-10 shadow-sm">
                                <tr>
                                    <th className="p-3 w-20 border-b border-border text-text-secondary font-medium font-mono">PID</th>
                                    <th className="p-3 border-b border-border text-text-secondary font-medium">Name</th>
                                    <th className="p-3 w-32 border-b border-border text-text-secondary font-medium text-right">Memory</th>
                                    <th className="p-3 w-20 border-b border-border text-text-secondary font-medium text-right">Action</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border font-mono">
                                {processes.map((proc, idx) => (
                                    <tr key={idx} className="hover:bg-bg-tertiary/50 transition-colors group">
                                        <td className="p-3 text-cyan-500">{proc.pid}</td>
                                        <td className="p-3 text-text-primary text-xs">{proc.name}</td>
                                        <td className="p-3 text-right text-text-secondary text-xs">{proc.memory}</td>
                                        <td className="p-3 text-right">
                                            <button
                                                onClick={() => killProcess(proc.pid)}
                                                className="p-1.5 hover:bg-red-500/20 rounded text-text-secondary hover:text-red-400 transition-colors"
                                                title="Kill Process"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                                {processes.length === 0 && !loading && (
                                    <tr><td colSpan="4" className="p-10 text-center text-text-secondary italic">No process data available</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
};

export default ProcessManager;
