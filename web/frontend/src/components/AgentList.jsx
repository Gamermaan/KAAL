import React, { useEffect, useState } from 'react';
import { useAgentStore } from '../store/agentStore';
import { useWindowStore } from '../store/windowStore';
import { getAgents } from '../services/api';
import { motion } from 'framer-motion';
import FuiFrame from './ui/FuiFrame';
import { Monitor, Wifi, Shield, Activity, HardDrive, Globe, Terminal, Cpu } from 'lucide-react';

const AgentList = () => {
    const { openWindow } = useWindowStore();
    const { agents, setAgents } = useAgentStore();
    const [scanRot, setScanRot] = useState(0);

    // Scan Animation Loop
    useEffect(() => {
        const interval = setInterval(() => {
            setScanRot(r => (r + 2) % 360);
        }, 50);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        const fetchAgents = async () => {
            try {
                const response = await getAgents();
                setAgents(response.data);
            } catch (error) {
                console.error('Failed to fetch agents:', error);
            }
        };
        fetchAgents();
        const interval = setInterval(fetchAgents, 5000);
        return () => clearInterval(interval);
    }, [setAgents]);

    const activeAgents = agents.filter(a => a.status === 'active').length;

    return (
        <div className="h-full grid grid-cols-12 gap-6 p-2 overflow-hidden">

            {/* LEFT: STATUS & GLOBAL MAP (3 Cols) */}
            <div className="col-span-3 flex flex-col space-y-6">

                {/* 1. Global Threat Map (Abstract) */}
                <FuiFrame title="GLOBAL_THREAT_MAP" className="h-64" glow={true}>
                    <div className="relative w-full h-full bg-[#050510] flex items-center justify-center overflow-hidden">
                        {/* Grid Background */}
                        <div className="absolute inset-0 opacity-20" style={{ backgroundImage: 'radial-gradient(circle, #00f3ff 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>

                        {/* Radar Sweep */}
                        <div
                            className="absolute w-[150%] h-[2px] bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-50"
                            style={{ transform: `rotate(${scanRot}deg)` }}
                        ></div>

                        {/* Central Point */}
                        <div className="w-4 h-4 bg-cyan-500 rounded-full shadow-[0_0_20px_cyan]"></div>

                        {/* Orbiting Nodes */}
                        <motion.div
                            animate={{ rotate: 360 }}
                            transition={{ duration: 10, repeat: Infinity, ease: 'linear' }}
                            className="absolute w-40 h-40 border border-cyan-500/20 rounded-full"
                        >
                            <div className="absolute top-0 left-1/2 w-2 h-2 bg-emerald-400 rounded-full shadow-[0_0_10px_lime]"></div>
                        </motion.div>
                    </div>
                    {/* Map Overlay Stats */}
                    <div className="absolute bottom-2 left-4 text-[10px] text-cyan-400 font-mono">
                        LAT: 34.0522 N <br /> LON: 118.2437 W
                    </div>
                </FuiFrame>

                {/* 2. System Vitals */}
                <FuiFrame title="SYSTEM_VITALS" className="flex-1">
                    <div className="p-4 space-y-4">
                        <ResourceBar label="CPU_CORE" percent={18} color="bg-emerald-500" />
                        <ResourceBar label="MEM_ALLOC" percent={42} color="bg-yellow-500" />
                        <ResourceBar label="NET_IO" percent={67} color="bg-cyan-500" />
                        <ResourceBar label="STORAGE" percent={89} color="bg-red-500" />
                    </div>
                </FuiFrame>
            </div>

            {/* CENTER: AGENT FLEET (6 Cols) */}
            <div className="col-span-6 flex flex-col">
                <FuiFrame title="DETECTED_NODES" className="h-full" variant="default">
                    <div className="h-full flex flex-col">
                        <div className="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
                            {agents.map((agent) => (
                                <motion.div
                                    key={agent.id}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    whileHover={{ scale: 1.02, backgroundColor: 'rgba(0, 243, 255, 0.05)' }}
                                    onClick={() => openWindow({
                                        id: `agent-${agent.id}`,
                                        title: agent.hostname || agent.id.substring(0, 8),
                                        type: 'agent',
                                        data: { agentId: agent.id },
                                        closable: true
                                    })}
                                    className="cursor-pointer border-b border-cyan-900/40 p-3 flex items-center justify-between group"
                                >
                                    <div className="flex items-center space-x-4">
                                        <div className={`
                                            w-2 h-2 rounded-full shadow-[0_0_10px_currentColor] 
                                            ${agent.status === 'active' ? 'text-emerald-400 bg-emerald-400' : 'text-red-500 bg-red-500'}
                                        `}></div>
                                        <div>
                                            <div className="text-sm font-bold text-white group-hover:text-cyan-400 tracking-wider">
                                                {agent.hostname.toUpperCase()}
                                            </div>
                                            <div className="text-[10px] text-gray-500 font-mono">ID: {agent.id.substring(0, 8)}</div>
                                        </div>
                                    </div>

                                    <div className="text-right">
                                        <div className="text-[10px] font-mono text-cyan-700 group-hover:text-cyan-400">{agent.internal_ip}</div>
                                        <div className="text-[10px] font-bold text-gray-600 uppercase">{agent.platform}</div>
                                    </div>
                                </motion.div>
                            ))}
                            {agents.length === 0 && (
                                <div className="text-center text-gray-600 mt-20 font-mono animate-pulse">Scanning for signals...</div>
                            )}
                        </div>
                    </div>
                </FuiFrame>
            </div>

            {/* RIGHT: OPERATIONS LOG (3 Cols) */}
            <div className="col-span-3">
                <FuiFrame title="OPS_LOG" className="h-full">
                    <div className="p-4 font-mono text-[10px] space-y-2 text-gray-500 h-full overflow-hidden">
                        <div className="text-cyan-500 border-l-2 border-cyan-500 pl-2">INIT_SEQUENCE_STARTED</div>
                        <div className="pl-2">Loading core modules... [OK]</div>
                        <div className="pl-2">Connecting to C2 Relay... [OK]</div>
                        {agents.map(a => (
                            <div key={a.id + 'log'} className="pl-2 border-l-2 border-transparent hover:border-emerald-500 hover:text-emerald-400 transition-colors">
                                Host <span className="text-white">{a.hostname}</span> detected.
                            </div>
                        ))}
                    </div>
                </FuiFrame>
            </div>
        </div>
    );
};

const ResourceBar = ({ label, percent, color }) => (
    <div className="space-y-1">
        <div className="flex justify-between text-[10px] text-gray-400">
            <span>{label}</span>
            <span>{percent}%</span>
        </div>
        <div className="h-1 w-full bg-gray-800 relative overflow-hidden">
            <motion.div
                className={`h-full ${color} shadow-[0_0_5px_currentColor]`}
                initial={{ width: 0 }}
                animate={{ width: `${percent}%` }}
                transition={{ duration: 1.5 }}
            />
        </div>
    </div>
);

export default AgentList;
