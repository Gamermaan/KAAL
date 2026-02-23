import React, { useState } from 'react';
import { useAgentStore } from '../../store/agentStore';
import { Clock, CheckCircle, XCircle, Loader, ArrowRight } from 'lucide-react';

const TaskHistory = ({ agentId }) => {
    const tasks = useAgentStore((state) => state.tasks[agentId] || []);
    const [expandedTask, setExpandedTask] = useState(null);

    // Sort by timestamp desc
    const sortedTasks = [...tasks].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    const toggleExpand = (taskId) => {
        setExpandedTask(expandedTask === taskId ? null : taskId);
    };

    return (
        <div className="h-full flex flex-col font-mono text-sm text-gray-300">
            {/* Header */}
            <div className="flex items-center px-4 py-2 border-b border-white/10 bg-black/40">
                <div className="w-24 text-gray-500">TIME</div>
                <div className="w-20 text-gray-500">ID</div>
                <div className="w-24 text-gray-500">STATUS</div>
                <div className="flex-1 text-gray-500">COMMAND</div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-800">
                {sortedTasks.length === 0 && (
                    <div className="p-8 text-center text-gray-600 italic">No command history found.</div>
                )}

                {sortedTasks.map((task) => (
                    <div key={task.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                        <div
                            className="flex items-center px-4 py-2 cursor-pointer"
                            onClick={() => toggleExpand(task.id)}
                        >
                            <div className="w-24 text-[10px] text-gray-500">
                                {new Date(task.timestamp).toLocaleTimeString()}
                            </div>
                            <div className="w-20 text-[10px] text-cyan-600 font-bold">
                                {task.id ? task.id.substring(0, 6) : '????'}
                            </div>
                            <div className="w-24">
                                <StatusBadge status={task.status} />
                            </div>
                            <div className="flex-1 truncate font-mono text-gray-300">
                                {task.command}
                            </div>
                            <div className="w-6 text-gray-600">
                                {expandedTask === task.id ? '▼' : '▶'}
                            </div>
                        </div>

                        {/* Expanded Details */}
                        {expandedTask === task.id && (
                            <div className="bg-black/40 p-4 border-t border-white/5 text-xs">
                                <div className="mb-2 flex gap-4 text-gray-500">
                                    <span>Full ID: {task.id}</span>
                                    <span>Date: {new Date(task.timestamp).toLocaleString()}</span>
                                </div>

                                <div className="mb-2">
                                    <div className="text-[10px] text-cyan-500 mb-1">COMMAND</div>
                                    <div className="bg-black p-2 border border-gray-800 rounded font-mono text-green-400">
                                        {task.command}
                                    </div>
                                </div>

                                <div>
                                    <div className="text-[10px] text-cyan-500 mb-1">RESULT</div>
                                    <pre className="bg-black p-2 border border-gray-800 rounded font-mono text-gray-300 overflow-x-auto whitespace-pre-wrap max-h-64 scrollbar-thin">
                                        {task.result || (task.status === 'completed' ? <span className="text-gray-600 italic">No output</span> : <span className="text-gray-600 italic animate-pulse">Waiting for result...</span>)}
                                    </pre>
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
};

const StatusBadge = ({ status }) => {
    switch (status) {
        case 'pending':
            return <span className="text-yellow-500 flex items-center gap-1"><Clock size={12} /> PEND</span>;
        case 'acknowledged':
            return <span className="text-blue-400 flex items-center gap-1"><ArrowRight size={12} /> ACK</span>;
        case 'processing':
            return <span className="text-blue-400 flex items-center gap-1 animate-pulse"><Loader size={12} /> RUN</span>;
        case 'completed':
            return <span className="text-emerald-500 flex items-center gap-1"><CheckCircle size={12} /> DONE</span>;
        case 'failed':
        case 'error':
            return <span className="text-red-500 flex items-center gap-1"><XCircle size={12} /> FAIL</span>;
        default:
            return <span className="text-gray-500">{status?.toUpperCase() || 'UNK'}</span>;
    }
};

export default TaskHistory;
