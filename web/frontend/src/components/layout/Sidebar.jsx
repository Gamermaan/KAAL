import React from 'react';
import { useWindowStore } from '../../store/windowStore';
import {
    Activity, Cpu, Terminal, Database, Zap, Hexagon, Settings, Monitor
} from 'lucide-react';

const Sidebar = () => {
    const { activeWindowId, openWindow } = useWindowStore();

    const navItems = [
        { id: 'dashboard', icon: Activity, label: 'CMD' },
        { id: 'agents', icon: Cpu, label: 'NODES' },
        { id: 'terminal', icon: Terminal, label: 'SHELL' },
        { id: 'files', icon: Database, label: 'DATA' },
        { id: 'payloads', icon: Zap, label: 'WPN' },
    ];

    const handleOpen = (id, type, title) => {
        openWindow({ id, type, title, closable: id !== 'dashboard' });
    };

    return (
        <nav className="h-full w-20 flex flex-col items-center py-6 bg-[#0a0f14]/90 border-r border-cyan-500/20 backdrop-blur-xl z-50">
            {/* Animated Logo */}
            <div className="mb-10 relative group cursor-pointer">
                <div className="absolute inset-0 bg-cyan-500 blur-[20px] opacity-20 group-hover:opacity-60 transition-opacity animate-pulse"></div>
                <Hexagon className="w-10 h-10 text-cyan-400 group-hover:rotate-180 transition-transform duration-1000" strokeWidth={1} />
                <div className="absolute top-[50%] left-[50%] -translate-x-[50%] -translate-y-[50%] w-2 h-2 bg-cyan-500 rounded-full"></div>
            </div>

            {/* Nav Rail */}
            <div className="flex-1 flex flex-col space-y-6 w-full items-center">
                {navItems.map((item) => {
                    // Check active state
                    const isActive = activeWindowId === item.id || (item.id === 'agents' && activeWindowId.startsWith('agent-'));

                    return (
                        <button
                            key={item.id}
                            onClick={() => handleOpen(
                                item.id === 'agents' ? 'agents-list' : item.id === 'terminal' ? 'terminal-global' : item.id === 'files' ? 'files-global' : item.id,
                                item.id === 'agents' ? 'agents-list' : item.id === 'terminal' ? 'terminal-global' : item.id === 'files' ? 'files-global' : item.id,
                                item.label === 'CMD' ? 'COMMAND CENTER' : item.label
                            )}
                            className="group relative flex flex-col items-center justify-center w-12 h-12"
                        >
                            {/* Active Indicator (Left Bar) */}
                            <div className={`
                                absolute left-0 w-1 h-8 bg-cyan-400 rounded-r shadow-[0_0_10px_cyan] transition-all duration-300
                                ${isActive ? 'opacity-100' : 'opacity-0 h-0 group-hover:opacity-50 group-hover:h-4'}
                            `}></div>

                            {/* Icon */}
                            <item.icon
                                className={`w-6 h-6 transition-all duration-300 ${isActive ? 'text-cyan-400 scale-110 drop-shadow-[0_0_5px_rgba(0,243,255,0.8)]' : 'text-gray-500 group-hover:text-cyan-200'}`}
                                strokeWidth={1.5}
                            />

                            {/* Tooltip Label */}
                            <span className="absolute left-14 bg-black/90 border border-cyan-500/30 text-cyan-400 text-[10px] font-bold px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity translate-x-2 group-hover:translate-x-0 pointer-events-none tracking-widest uppercase rounded-sm whitespace-nowrap z-50">
                                {item.label}
                            </span>
                        </button>
                    );
                })}
            </div>

            {/* Bottom Actions */}
            <button className="mb-4 text-gray-600 hover:text-cyan-400 hover:rotate-90 transition-all duration-500">
                <Settings className="w-6 h-6" strokeWidth={1.5} />
            </button>
        </nav>
    );
};

export default Sidebar;
