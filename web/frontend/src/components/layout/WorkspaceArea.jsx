import React from 'react';
import { useWindowStore } from '../../store/windowStore';
import { X, Monitor, Terminal, Folder, Ghost, Settings, LayoutGrid } from 'lucide-react';
import AgentList from '../AgentList';
import AgentDetail from '../AgentDetail';
import CommandShell from '../modules/CommandShell'; // Standalone terminal
import FileManager from '../modules/FileManager';   // Standalone file manager
import { motion, AnimatePresence } from 'framer-motion';

// Mapping window types to components
const COMPONENT_MAP = {
    'dashboard': () => <AgentList />,
    'agent': (props) => <AgentDetail {...props} />,
    'terminal-global': () => <div className="p-4 text-white">Global Terminal (Coming Soon)</div>,
    'files-global': () => <div className="p-4 text-white">Global File Manager (Coming Soon)</div>,
    'settings': () => <div className="p-4 text-white">Settings Panel (Coming Soon)</div>,
};

const WorkspaceArea = () => {
    const { windows, activeWindowId, closeWindow, focusWindow } = useWindowStore();

    // Helper to get icon
    const getIcon = (type) => {
        switch (type) {
            case 'dashboard': return <LayoutGrid className="w-3 h-3" />;
            case 'agent': return <Monitor className="w-3 h-3 text-accent-primary" />;
            case 'terminal-global': return <Terminal className="w-3 h-3" />;
            case 'files-global': return <Folder className="w-3 h-3" />;
            case 'settings': return <Settings className="w-3 h-3" />;
            default: return <Ghost className="w-3 h-3" />;
        }
    };

    return (
        <div className="flex flex-col h-full bg-[#0f0f23] overflow-hidden">
            {/* Tab Bar */}
            <div className="h-10 bg-[#0f0f23] border-b border-[#2d2d44] flex items-end px-2 space-x-1 shrink-0 overflow-x-auto no-scrollbar">
                <AnimatePresence>
                    {windows.map((win) => (
                        <motion.div
                            key={win.id}
                            initial={{ opacity: 0, y: 10, scale: 0.9 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, y: 10, scale: 0.9, width: 0 }}
                            transition={{ duration: 0.15 }}
                            onClick={() => focusWindow(win.id)}
                            className={`
                                group relative flex items-center min-w-[150px] max-w-[200px] h-9 px-3 rounded-t-lg cursor-pointer transition-all border-t border-x border-transparent
                                ${activeWindowId === win.id
                                    ? 'bg-[#1a1a2e] text-white border-[#2d2d44] border-b-[#1a1a2e] z-10'
                                    : 'bg-transparent text-gray-500 hover:bg-[#1a1a2e]/50 hover:text-gray-300'
                                }
                            `}
                        >
                            {/* Active Indicator Line */}
                            {activeWindowId === win.id && (
                                <motion.div
                                    layoutId="activeTabLine"
                                    className="absolute top-0 left-0 right-0 h-[2px] bg-accent-primary"
                                />
                            )}

                            <span className="mr-2 opacity-70">{getIcon(win.type)}</span>
                            <span className="text-xs font-medium truncate flex-1">{win.title}</span>

                            {win.closable && (
                                <button
                                    onClick={(e) => { e.stopPropagation(); closeWindow(win.id); }}
                                    className="ml-2 p-0.5 rounded-full text-gray-500 hover:bg-white/10 hover:text-white opacity-0 group-hover:opacity-100 transition-all"
                                >
                                    <X className="w-3 h-3" />
                                </button>
                            )}
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-hidden relative bg-[#1a1a2e]">
                {windows.map((win) => {
                    const Component = COMPONENT_MAP[win.type] || (() => <div>Unknown Component</div>);
                    const isActive = activeWindowId === win.id;

                    return (
                        <div
                            key={win.id}
                            className={`absolute inset-0 w-full h-full overflow-auto bg-[#1a1a2e] transition-opacity duration-200 ${isActive ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}
                        >
                            <div className="p-6 h-full">
                                <Component {...(win.data || {})} />
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default WorkspaceArea;
