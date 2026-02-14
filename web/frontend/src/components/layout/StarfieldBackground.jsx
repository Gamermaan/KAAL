import React, { useEffect, useRef } from 'react';

const StarfieldBackground = () => {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        let width = canvas.width = window.innerWidth;
        let height = canvas.height = window.innerHeight;

        let stars = [];
        const numStars = 150;
        const speed = 0.5;

        // Initialize stars
        for (let i = 0; i < numStars; i++) {
            stars.push({
                x: Math.random() * width,
                y: Math.random() * height,
                z: Math.random() * width
            });
        }

        const resize = () => {
            if (canvas) {
                width = canvas.width = window.innerWidth;
                height = canvas.height = window.innerHeight;
            }
        };
        window.addEventListener('resize', resize);

        const animate = () => {
            if (!ctx) return;
            ctx.fillStyle = "#020205"; // Deep background
            ctx.fillRect(0, 0, width, height);

            stars.forEach(star => {
                // Move star
                star.z -= speed;
                if (star.z <= 0) {
                    star.z = width;
                    star.x = Math.random() * width;
                    star.y = Math.random() * height;
                }

                // Project star
                const k = 128.0 / star.z;
                const px = (star.x - width / 2) * k + width / 2;
                const py = (star.y - height / 2) * k + height / 2;

                if (px >= 0 && px <= width && py >= 0 && py <= height) {
                    const size = (1 - star.z / width) * 2.5;
                    const shade = parseInt((1 - star.z / width) * 255);

                    // Draw Star
                    ctx.fillStyle = `rgb(${shade},${shade},${shade})`;
                    ctx.beginPath();
                    ctx.arc(px, py, size, 0, Math.PI * 2);
                    ctx.fill();
                }
            });

            requestAnimationFrame(animate);
        };

        const animId = requestAnimationFrame(animate);

        return () => {
            window.removeEventListener('resize', resize);
            cancelAnimationFrame(animId);
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            className="absolute inset-0 w-full h-full z-0 pointer-events-none"
        />
    );
};

export default StarfieldBackground;
