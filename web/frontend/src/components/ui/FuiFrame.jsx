import React from 'react';
import { motion } from 'framer-motion';

/**
 * FuiFrame (Futuristic User Interface Frame)
 * Wraps content in a high-tech, angled border container with holographic effects.
 * 
 * @param {string} title - Optional title displayed on the frame edge
 * @param {string} className - Additional Tailwind classes
 * @param {boolean} glow - Whether to animate a pulse glow
 * @param {string} variant - 'default' | 'alert' | 'success'
 */
const FuiFrame = ({ children, title, className = '', glow = false, variant = 'default' }) => {

    // Color mappings
    const colors = {
        default: { border: 'border-cyan-500/30', text: 'text-cyan-400', bg: 'bg-cyan-500' },
        alert: { border: 'border-red-500/40', text: 'text-red-500', bg: 'bg-red-500' },
        success: { border: 'border-emerald-500/40', text: 'text-emerald-400', bg: 'bg-emerald-500' },
    };
    const c = colors[variant];

    return (
        <div className={`relative ${className} group`}>
            {/* Main Container with Angled Corners */}
            <div className={`
                relative w-full h-full 
                bg-[#0a0f14]/80 backdrop-blur-md 
                border-l border-r ${c.border}
                fui-clip-corners
            `}>
                {/* Top Border Segment */}
                <div className={`absolute top-0 left-[20px] right-[20px] h-[1px] ${c.bg} opacity-50`}></div>

                {/* Bottom Border Segment */}
                <div className={`absolute bottom-0 left-[20px] right-[20px] h-[1px] ${c.bg} opacity-50`}></div>

                {/* Corner Decorations (SVG Vectors for perfect crispness) */}
                <svg className="absolute top-0 left-0 w-6 h-6" style={{ fill: 'none', stroke: 'currentColor' }}>
                    <path d="M0 20 L0 6 L6 0 L20 0" className={`${c.text} opacity-80`} strokeWidth="1.5" />
                </svg>
                <svg className="absolute top-0 right-0 w-6 h-6 rotate-90" style={{ fill: 'none', stroke: 'currentColor' }}>
                    <path d="M0 20 L0 6 L6 0 L20 0" className={`${c.text} opacity-80`} strokeWidth="1.5" />
                </svg>
                <svg className="absolute bottom-0 right-0 w-6 h-6 rotate-180" style={{ fill: 'none', stroke: 'currentColor' }}>
                    <path d="M0 20 L0 6 L6 0 L20 0" className={`${c.text} opacity-80`} strokeWidth="1.5" />
                </svg>
                <svg className="absolute bottom-0 left-0 w-6 h-6 -rotate-90" style={{ fill: 'none', stroke: 'currentColor' }}>
                    <path d="M0 20 L0 6 L6 0 L20 0" className={`${c.text} opacity-80`} strokeWidth="1.5" />
                </svg>

                {/* Optional Title Label */}
                {title && (
                    <div className="absolute -top-3 left-8 px-2 bg-[#020205] border border-cyan-500/30 text-[10px] tracking-[0.2em] font-bold text-cyan-400 uppercase select-none z-10">
                        {title}
                    </div>
                )}

                {/* Content Area */}
                <div className="relative z-0 h-full overflow-hidden">
                    {children}
                </div>
            </div>

            {/* Glow Effect (Optional) */}
            {glow && (
                <div className={`absolute inset-0 z-[-1] blur-md opacity-20 ${c.bg} animate-pulse`}></div>
            )}
        </div>
    );
};

export default FuiFrame;
