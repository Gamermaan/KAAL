import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Terminal, Folder, Camera, Smartphone, Cpu, Activity, ShieldCheck, Zap } from 'lucide-react';
import { getAgent } from '../services/api';
import CommandShell from './modules/CommandShell';
import AndroidFrame from './modules/AndroidFrame';
import FileManager from './modules/FileManager';
import WebcamCapture from './modules/WebcamCapture';
import FuiFrame from './ui/FuiFrame';

const AgentDetail = ({ agentId: propAgentId }) => {
    const { agentId: paramAgentId } = useParams();
    const [agent, setAgent] = useState(null);
    const [activeTool, setActiveTool] = useState('files');
    const agentId = propAgentId || paramAgentId;

    useEffect(() => {
        if (!agentId) return;
        const loadAgent = async () => {
            try {
                const response = await getAgent(agentId);
                setAgent(response.data);
            } catch (error) {
                setAgent({ id: agentId, platform: 'unknown', hostname: 'TARGET_OFFLINE', status: 'offline', internal_ip: '0.0.0.0' });
            }
        };
        loadAgent();
    }, [agentId]);

    if (!agent) return <div className="p-10 text-cyan-500 font-mono animate-pulse">ACQUIRING TARGET LOCK...</div>;

    return (
        <div className="h-full flex flex-col gap-4 font-tech p-2">

            {/* TOP ROW: TOOLS + INFO (Flex) */}
            <div className="flex-1 flex gap-4 min-h-0">

                {/* 1. Tool Selector Rail */}
                <div className="w-16 flex flex-col gap-2">
                    <ToolButton icon={Folder} active={activeTool === 'files'} onClick={() => setActiveTool('files')} label="FILES" />
                    <ToolButton icon={Camera} active={activeTool === 'cam'} onClick={() => setActiveTool('cam')} label="CAM" />
                    <ToolButton icon={Terminal} active={activeTool === 'shell'} onClick={() => setActiveTool('shell')} label="SHELL" />
                    {agent.platform === 'android' && (
                        <ToolButton icon={Smartphone} active={activeTool === 'android'} onClick={() => setActiveTool('android')} label="MOB" />
                    )}
                </div>

                {/* 2. Main Viewport (Files, Cam, etc.) */}
                <FuiFrame title={`MODULE :: ${activeTool.toUpperCase()}`} className="flex-1" glow={false}>
                    <div className="h-full bg-black/50 p-1">
                        {activeTool === 'files' && <FileManager agentId={agentId} />}
                        {activeTool === 'cam' && <WebcamCapture agentId={agentId} />}
                        {activeTool === 'android' && <AndroidFrame agentId={agentId} />}
                        {activeTool === 'shell' && <CommandShell agentId={agentId} />}
                    </div>
                </FuiFrame>

                {/* 3. Target Intel Panel (Right) */}
                <FuiFrame title="TARGET_INTEL" className="w-64" variant="alert">
                    <div className="p-4 space-y-6">
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

                        {/* Visual Hex Graph (Decor) */}
                        <div className="mt-8 flex justify-center opacity-60">
                            <ShieldCheck className="w-16 h-16 text-red-500 animate-pulse" strokeWidth={1} />
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
