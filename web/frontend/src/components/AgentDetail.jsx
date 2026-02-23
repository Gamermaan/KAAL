import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Terminal, Folder, Camera, Smartphone, Cpu, Activity, ShieldCheck, Zap, Keyboard, Clock } from 'lucide-react';
import { getAgent } from '../services/api';
import CommandShell from './modules/CommandShell';
import AndroidFrame from './modules/AndroidFrame';
import FileManager from './modules/FileManager';
import WebcamCapture from './modules/WebcamCapture';
import Keylogger from './modules/Keylogger';
import ProcessManager from './modules/ProcessManager';
import TaskHistory from './modules/TaskHistory';
import AgentLogs from './modules/AgentLogs';
import FuiFrame from './ui/FuiFrame';
import { useAgentStore } from '../store/agentStore';

const AgentDetail = ({ agentId: propAgentId }) => {
    const { agentId: paramAgentId } = useParams();
    const [agent, setAgent] = useState(null);
    const [activeTool, setActiveTool] = useState('files');
    const agentId = propAgentId || paramAgentId;

    // Get tasks from store
    const tasks = useAgentStore((state) => state.tasks[agentId] || []);

    // ... (useEffect and loadAgent remain same)

    if (!agent) return <div className="p-10 text-cyan-500 font-mono animate-pulse">ACQUIRING TARGET LOCK...</div>;

    return (
        <div className="h-full flex flex-col gap-4 font-tech p-2">
            {/* TOP ROW: TOOLS + INFO (Flex) */}
            <div className="flex-1 flex gap-4 min-h-0">
                {/* ... (Tool Selector Rail) ... */}
                <div className="w-16 flex flex-col gap-2">
                    <ToolButton icon={Folder} active={activeTool === 'files'} onClick={() => setActiveTool('files')} label="FILES" />
                    <ToolButton icon={Cpu} active={activeTool === 'proc'} onClick={() => setActiveTool('proc')} label="PROC" />
                    <ToolButton icon={Camera} active={activeTool === 'cam'} onClick={() => setActiveTool('cam')} label="CAM" />
                    <ToolButton icon={Terminal} active={activeTool === 'shell'} onClick={() => setActiveTool('shell')} label="SHELL" />
                    <ToolButton icon={Keyboard} active={activeTool === 'keys'} onClick={() => setActiveTool('keys')} label="KEYS" />
                    <ToolButton icon={Clock} active={activeTool === 'history'} onClick={() => setActiveTool('history')} label="HIST" />
                    <ToolButton icon={Activity} active={activeTool === 'logs'} onClick={() => setActiveTool('logs')} label="LOGS" />
                    {agent.platform === 'android' && (
                        <ToolButton icon={Smartphone} active={activeTool === 'android'} onClick={() => setActiveTool('android')} label="MOB" />
                    )}
                </div>

                {/* ... (Main Viewport) ... */}
                <FuiFrame title={`MODULE :: ${activeTool.toUpperCase()}`} className="flex-1" glow={false}>
                    <div className="h-full bg-black/50 p-1">
                        {activeTool === 'files' && <FileManager agentId={agentId} />}
                        {activeTool === 'proc' && <ProcessManager agentId={agentId} />}
                        {activeTool === 'cam' && <WebcamCapture agentId={agentId} />}
                        {activeTool === 'keys' && <Keylogger agentId={agentId} />}
                        {activeTool === 'android' && <AndroidFrame agentId={agentId} />}
                        {activeTool === 'shell' && <CommandShell agentId={agentId} />}
                        {activeTool === 'history' && <TaskHistory agentId={agentId} />}
                        {activeTool === 'logs' && <AgentLogs agentId={agentId} />}
                    </div>
                </FuiFrame>

                {/* 3. Target Intel Panel (Right) - UPDATED */}
                <FuiFrame title="TARGET_INTEL" className="w-64 flex flex-col" variant="alert">
                    <div className="p-4 space-y-6 border-b border-white/10">
                        {/* ID Plate */}
                        <div className="border-b border-red-500/30 pb-4">
                            <h2 className="text-xl font-bold text-white tracking-widest">{agent.hostname.toUpperCase()}</h2>
                            <p className="text-xs text-red-400 font-mono">ID: {agent.id.substring(0, 8)}</p>
                        </div>

                        {/* Specs */}
                        <div className="space-y-3 font-mono text-sm">
                            <InfoRow label="IP_ADDR" value={agent.internal_ip} />
                            <InfoRow label="OS_PLAT" value={agent.platform} />
                            <InfoRow label="PRIVILEGE" value="ADMIN/ROOT" color="text-yellow-400" />
                            <InfoRow label="STATUS" value="ONLINE" color="text-emerald-400" />
                        </div>
                    </div>

                    {/* TASK HISTORY (Replaces Hex Graph) */}
                    <div className="flex-1 flex flex-col min-h-0 bg-black/20">
                        <div className="bg-red-900/20 px-2 py-1 text-[10px] text-red-400 border-b border-red-500/20 font-bold tracking-wider">
                            ACTIVE_TASKS :: {tasks.length}
                        </div>
                        <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-red-900/50">
                            {tasks.length === 0 && (
                                <div className="text-center py-4 text-xs text-gray-600 italic">No task history</div>
                            )}
                            {tasks.map((task) => (
                                <div key={task.id} className="group border-b border-white/5 pb-1 flex justify-between items-start text-xs font-mono">
                                    <div className="flex flex-col overflow-hidden mr-2">
                                        <span className="text-gray-300 truncate w-full group-hover:text-cyan-400 transition-colors" title={task.command}>
                                            {task.command}
                                        </span>
                                        <span className="text-[9px] text-gray-600">{new Date(task.timestamp).toLocaleTimeString()}</span>
                                    </div>
                                    <StatusIcon status={task.status} />
                                </div>
                            ))}
                        </div>
                    </div>
                </FuiFrame>
            </div>

            {/* BOTTOM ROW: QUICK TERMINAL (If tool is NOT shell, show mini shell) */}
            {activeTool !== 'shell' && (
                <FuiFrame title="SECURE_SHELL_LINK" className="h-48" variant="default">
                    <CommandShell agentId={agentId} minimal={true} />
                </FuiFrame>
            )}
        </div>
    );
};

const StatusIcon = ({ status }) => {
    switch (status) {
        case 'pending': return <span className="text-yellow-500 animate-pulse" title="Sent">⌛</span>;
        case 'acknowledged': return <span className="text-cyan-400" title="Acknowledged">⬇️</span>;
        case 'processing': return <span className="text-blue-400 animate-spin" title="Running">⚙️</span>;
        case 'completed': return <span className="text-emerald-400" title="Done">✅</span>;
        default: return <span className="text-red-500" title="Error">❌</span>;
    }
};

const ToolButton = ({ icon: Icon, active, onClick, label }) => (
    <button
        onClick={onClick}
        className={`
            aspect-square flex flex-col items-center justify-center border transition-all duration-300
            ${active
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-400 shadow-[0_0_15px_rgba(0,243,255,0.3)]'
                : 'bg-black/40 border-gray-800 text-gray-500 hover:border-cyan-500/50 hover:text-cyan-200'
            }
        `}
    >
        <Icon className="w-6 h-6 mb-1" strokeWidth={1.5} />
        <span className="text-[8px] font-bold">{label}</span>
    </button>
);

const InfoRow = ({ label, value, color = 'text-gray-300' }) => (
    <div className="flex justify-between items-center border-b border-white/5 pb-1">
        <span className="text-xs text-gray-500">{label}</span>
        <span className={`${color}`}>{value}</span>
    </div>
);

export default AgentDetail;
