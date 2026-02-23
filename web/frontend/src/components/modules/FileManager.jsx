import React, { useState, useEffect } from 'react';
import { Folder, File, ArrowUp, Download, Upload, Trash2, ChevronRight, RefreshCw } from 'lucide-react';
import { listFiles, downloadFile, uploadFile } from '../../services/api';
import { kaalEvents } from '../../services/eventBus';

const FileManager = ({ agentId }) => {
    const [currentPath, setCurrentPath] = useState('.');
    const [files, setFiles] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Listen for file results
        const unsubscribe = kaalEvents.on('task_result', (data) => {
            if (data.agent_id !== agentId) return;

            let parsed = null;
            try {
                // Try parse JSON first (Phase 1 Agent)
                if (typeof data.result === 'string' && (data.result.startsWith('{') || data.result.startsWith('['))) {
                    parsed = JSON.parse(data.result);
                } else if (typeof data.result === 'object') {
                    parsed = data.result;
                }
            } catch (e) { /* Not JSON */ }

            // Handle Structured Output (Phase 1+)
            if (parsed && parsed.type === 'file_list') {
                if (parsed.files) {
                    setFiles(parsed.files);
                    if (parsed.path) setCurrentPath(parsed.path);
                } else if (parsed.items) {
                    setFiles(parsed.items); // Backward compat if needed
                }
                setLoading(false);
            }
            else if (parsed && parsed.type === 'error') {
                setError(parsed.data || "Unknown Error");
                setLoading(false);
            }
            // Handle Legacy Output (Phase 0)
            else if (data.result && typeof data.result === 'string' && data.result.startsWith("[FILES]")) {
                try {
                    const legacyParsed = JSON.parse(data.result.substring(8));
                    if (legacyParsed.items) {
                        setFiles(legacyParsed.items);
                        if (legacyParsed.path) setCurrentPath(legacyParsed.path);
                    }
                    setLoading(false);
                } catch (e) {
                    setError("Failed to parse file list");
                    setLoading(false);
                }
            } else if (data.result && typeof data.result === 'string' && data.result.startsWith("Error")) {
                setError(data.result);
                setLoading(false);
            }
        });

        loadFiles('.');
        return () => unsubscribe();
    }, [agentId]);

    const loadFiles = async (path) => {
        setLoading(true);
        setError(null);
        try {
            await listFiles(agentId, path);
            // Don't setFiles here, wait for WebSocket result
            setCurrentPath(path);
        } catch (err) {
            setError("Failed to request file list: " + err.message);
            setLoading(false);
        }
    };

    const handleNavigate = (dir) => {
        const newPath = currentPath === '.' ? dir : `${currentPath}/${dir}`;
        loadFiles(newPath);
    };

    const handleUp = () => {
        if (currentPath === '.') return;
        const parts = currentPath.split('/');
        parts.pop();
        const newPath = parts.length === 0 ? '.' : parts.join('/');
        loadFiles(newPath);
    };

    const handleDownload = async (filename) => {
        try {
            const filepath = currentPath === '.' ? filename : `${currentPath}/${filename}`;
            const response = await downloadFile(agentId, filepath);
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', filename);
            document.body.appendChild(link);
            link.click();
            link.remove();
        } catch (err) {
            setError("Download failed: " + err.message);
        }
    };

    const handleUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        try {
            setLoading(true);
            await uploadFile(agentId, file, currentPath);
            loadFiles(currentPath);
        } catch (err) {
            setError("Upload failed: " + err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="bg-bg-secondary border border-border rounded-lg p-5 shadow-lg h-full flex flex-col">
            {/* Toolbar */}
            <div className="flex items-center justify-between mb-4 bg-bg-tertiary p-3 rounded-lg border border-border">
                <div className="flex items-center space-x-2 w-full mr-4">
                    <button onClick={handleUp} className="p-2 hover:bg-bg-secondary rounded-md text-text-secondary hover:text-accent-primary transition-colors disabled:opacity-50" disabled={currentPath === '.'}>
                        <ArrowUp className="w-5 h-5" />
                    </button>
                    <div className="flex-1 bg-bg-secondary border border-border rounded px-3 py-2 text-sm font-mono text-accent-secondary flex items-center">
                        <span className="opacity-50 mr-2">path:</span>
                        {currentPath}
                    </div>
                </div>
                <div className="flex space-x-3">
                    <label className="cursor-pointer bg-bg-secondary hover:bg-bg-primary border border-border hover:border-accent-primary text-text-secondary hover:text-accent-primary px-4 py-2 rounded-md flex items-center space-x-2 text-sm transition-all shadow-sm">
                        <Upload className="w-4 h-4" />
                        <span>Upload</span>
                        <input type="file" className="hidden" onChange={handleUpload} />
                    </label>
                    <button onClick={() => loadFiles(currentPath)} className="bg-accent-primary hover:bg-green-400 text-bg-primary px-4 py-2 rounded-md text-sm font-semibold flex items-center shadow-[0_0_10px_rgba(0,255,159,0.2)] transition-all">
                        <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            {/* File List */}
            <div className="flex-1 border border-border rounded-lg bg-bg-primary overflow-hidden relative">
                {loading && (
                    <div className="absolute inset-0 bg-bg-primary/80 flex items-center justify-center z-10">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary"></div>
                    </div>
                )}

                {error ? (
                    <div className="p-6 text-error flex flex-col items-center justify-center h-full">
                        <div className="bg-error/10 p-3 rounded-full mb-2"><Trash2 className="w-6 h-6" /></div>
                        {error}
                    </div>
                ) : (
                    <div className="overflow-auto h-full">
                        <table className="w-full text-sm">
                            <thead className="bg-bg-tertiary text-left sticky top-0 z-10 shadow-sm">
                                <tr>
                                    <th className="p-3 w-10 border-b border-border"></th>
                                    <th className="p-3 border-b border-border text-text-secondary font-medium">Name</th>
                                    <th className="p-3 w-32 border-b border-border text-text-secondary font-medium">Size</th>
                                    <th className="p-3 w-32 border-b border-border text-text-secondary font-medium text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                                {files.map((file, idx) => (
                                    <tr key={idx} className="hover:bg-bg-tertiary/50 transition-colors group">
                                        <td className="p-3 text-center">
                                            {file.is_dir ? <Folder className="w-5 h-5 text-yellow-500 fill-current opacity-80" /> : <File className="w-5 h-5 text-accent-secondary opacity-70" />}
                                        </td>
                                        <td className="p-3">
                                            {file.is_dir ? (
                                                <button onClick={() => handleNavigate(file.name)} className="hover:text-accent-primary hover:underline text-left w-full text-text-primary font-medium">
                                                    {file.name}
                                                </button>
                                            ) : (
                                                <span className="text-text-secondary group-hover:text-text-primary">{file.name}</span>
                                            )}
                                        </td>
                                        <td className="p-3 font-mono text-xs text-text-secondary">
                                            {file.is_dir ? '-' : (file.size / 1024).toFixed(1) + ' KB'}
                                        </td>
                                        <td className="p-3 text-right">
                                            {!file.is_dir && (
                                                <button onClick={() => handleDownload(file.name)} className="p-1.5 hover:bg-bg-tertiary rounded text-text-secondary hover:text-accent-secondary transition-colors" title="Download">
                                                    <Download className="w-4 h-4" />
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                                {files.length === 0 && !loading && (
                                    <tr><td colSpan="4" className="p-10 text-center text-text-secondary italic">Empty directory</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
};

export default FileManager;
