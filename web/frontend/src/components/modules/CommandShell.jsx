import React, { useEffect, useRef } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import { sendCommand } from '../../services/api';
import { Terminal as TerminalIcon, Maximize2, Trash2 } from 'lucide-react';

const CommandShell = ({ agentId }) => {
    const terminalRef = useRef(null);
    const term = useRef(null);
    const fitAddon = useRef(null);
    const commandBuffer = useRef('');

    useEffect(() => {
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
                    } else {
                        await executeCommand(cmdToSend);
                    }
                }

                commandBuffer.current = '';
                term.current.write('\x1b[1;32mroot@kaal\x1b[0m:\x1b[1;34m~\x1b[0m$ ');
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

        const handleResize = () => fitAddon.current.fit();
        window.addEventListener('resize', handleResize);

        return () => {
            term.current.dispose();
            window.removeEventListener('resize', handleResize);
        };
    }, []);

    const executeCommand = async (cmd) => {
        try {
            // Echo execution
            // term.current.writeln(`\x1b[33m[EXEC] ${cmd}\x1b[0m`);

            const result = await sendCommand(agentId, `exec ${cmd}`);
            if (result.data && result.data.task) {
                term.current.writeln(`\x1b[90m[Task Queued: ${result.data.task}]\x1b[0m`);
                term.current.writeln(`\x1b[32mOK\x1b[0m`);
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
