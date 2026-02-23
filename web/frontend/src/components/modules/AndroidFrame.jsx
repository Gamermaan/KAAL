import React, { useState } from 'react';
import { Smartphone, Camera, Mic, MessageSquare, Users, MapPin, Eye, Wifi, Battery } from 'lucide-react';

const AndroidFrame = ({ agentId }) => {
    const [activeTab, setActiveTab] = useState('screen');

    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">
            {/* Mobile Frame */}
            <div className="lg:col-span-1 flex justify-center">
                <div className="mobile-frame bg-black border-[6px] border-bg-tertiary rounded-[3rem] p-2 shadow-2xl relative w-[320px] h-[640px]">
                    {/* Camera Notch/Punch hole substitute */}
                    <div className="absolute top-0 left-1/2 transform -translate-x-1/2 h-6 w-32 bg-black rounded-b-xl z-20"></div>

                    <div className="mobile-screen bg-bg-primary rounded-[2.5rem] overflow-hidden h-full relative border border-gray-800">
                        <div className="flex flex-col h-full">
                            {/* Status Bar */}
                            <div className="flex justify-between items-center text-[10px] px-6 pt-3 text-text-secondary z-10">
                                <span>{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                <div className="flex space-x-1 items-center">
                                    <Wifi className="w-3 h-3" />
                                    <Battery className="w-3 h-3" />
                                </div>
                            </div>

                            {/* Content */}
                            <div className="flex-1 p-2 overflow-y-auto mt-2">
                                {activeTab === 'screen' && (
                                    <div className="bg-bg-secondary rounded-xl flex items-center justify-center h-full border border-border">
                                        <div className="text-center p-4">
                                            <div className="w-16 h-16 bg-bg-tertiary rounded-full flex items-center justify-center mx-auto mb-4 border border-border">
                                                <Eye className="h-8 w-8 text-accent-secondary" />
                                            </div>
                                            <p className="mt-2 text-sm text-text-secondary">Live screen stream</p>
                                            <p className="text-xs text-text-secondary opacity-50 mb-6">Connect to agent to view</p>
                                            <button className="px-5 py-2.5 bg-accent-primary text-bg-primary font-bold rounded-lg text-sm hover:shadow-[0_0_15px_rgba(0,255,159,0.4)] transition-all">
                                                START STREAM
                                            </button>
                                        </div>
                                    </div>
                                )}

                                {activeTab === 'camera' && (
                                    <div className="bg-bg-secondary rounded-xl flex items-center justify-center h-full border border-border">
                                        <div className="text-center p-4">
                                            <div className="w-16 h-16 bg-bg-tertiary rounded-full flex items-center justify-center mx-auto mb-4 border border-border">
                                                <Camera className="h-8 w-8 text-accent-primary" />
                                            </div>
                                            <p className="mt-2 text-sm text-text-secondary">Camera preview</p>
                                            <div className="flex space-x-2 mt-6 justify-center">
                                                <button className="px-3 py-1.5 bg-bg-tertiary border border-border text-text-primary rounded text-xs hover:border-accent-primary transition-colors">Front</button>
                                                <button className="px-3 py-1.5 bg-bg-tertiary border border-border text-text-primary rounded text-xs hover:border-accent-primary transition-colors">Back</button>
                                            </div>
                                            <button className="mt-4 px-5 py-2.5 bg-accent-primary text-bg-primary font-bold rounded-lg text-sm hover:shadow-[0_0_15px_rgba(0,255,159,0.4)] transition-all">
                                                CAPTURE
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Home Indicator */}
                            <div className="flex justify-center pb-2 pt-1">
                                <div className="w-24 h-1 bg-gray-600 rounded-full"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Control Panel */}
            <div className="lg:col-span-2 space-y-4">
                <div className="bg-bg-secondary rounded-xl p-6 border border-border shadow-lg">
                    <h3 className="text-sm font-semibold uppercase text-text-secondary tracking-wider mb-4 flex items-center">
                        <Smartphone className="w-4 h-4 mr-2 text-accent-secondary" />
                        Device Controls
                    </h3>

                    {/* Quick Actions */}
                    <div className="grid grid-cols-4 gap-3">
                        <ControlBtn icon={Eye} label="Screen" active={activeTab === 'screen'} onClick={() => setActiveTab('screen')} />
                        <ControlBtn icon={Camera} label="Camera" active={activeTab === 'camera'} onClick={() => setActiveTab('camera')} />
                        <ControlBtn icon={Mic} label="Mic" active={activeTab === 'mic'} onClick={() => setActiveTab('mic')} />
                        <ControlBtn icon={MessageSquare} label="SMS" active={activeTab === 'sms'} onClick={() => setActiveTab('sms')} />
                        <ControlBtn icon={Users} label="Contacts" active={activeTab === 'contacts'} onClick={() => setActiveTab('contacts')} />
                        <ControlBtn icon={MapPin} label="Location" active={activeTab === 'location'} onClick={() => setActiveTab('location')} />
                    </div>
                </div>

                {/* Info Panel based on selection */}
                <div className="bg-bg-secondary rounded-xl p-6 border border-border min-h-[200px]">
                    <h4 className="text-sm font-medium mb-3 text-accent-secondary">
                        {activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} Data
                    </h4>
                    <div className="text-center text-text-secondary py-10 opacity-50 bg-bg-primary/50 rounded-lg border border-dashed border-border">
                        Select a module or wait for data...
                    </div>
                </div>
            </div>
        </div>
    );
};

const ControlBtn = ({ icon: Icon, label, active, onClick }) => (
    <button
        onClick={onClick}
        className={`p-3 rounded-lg flex flex-col items-center space-y-2 transition-all duration-200 border ${active
                ? 'bg-[rgba(0,212,255,0.1)] text-accent-secondary border-accent-secondary shadow-[0_0_10px_rgba(0,212,255,0.2)]'
                : 'bg-bg-tertiary border-border text-text-secondary hover:text-text-primary hover:border-text-secondary hover:bg-bg-primary'
            }`}
    >
        <Icon className="h-5 w-5" />
        <span className="text-xs font-medium">{label}</span>
    </button>
);

export default AndroidFrame;
