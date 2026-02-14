import React, { useState } from 'react';
import { Camera, RefreshCw, Video, AlertCircle } from 'lucide-react';
import { captureWebcam } from '../../services/api';

const WebcamCapture = ({ agentId }) => {
    const [image, setImage] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleCapture = async () => {
        setLoading(true);
        setError(null);
        try {
            // Mocking for now as the API might not return immediate data in this version
            // const response = await captureWebcam(agentId);
            // if (response.data && response.data.image) {
            //     setImage(`data:image/png;base64,${response.data.image}`);
            // } 

            // Simulating a delay and success for UI demo
            await new Promise(r => setTimeout(r, 2000));
            // setError("Capture command sent. Waiting for agent upload..."); 
            // In a real scenario, we'd poll for the file or receive via websocket

        } catch (err) {
            setError("Capture failed: " + err.message);
        } finally {
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
