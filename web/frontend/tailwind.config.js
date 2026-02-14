/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                bg: {
                    primary: '#0f0f23',    // Dark Blue/Black
                    secondary: '#1a1a2e',  // Slightly Lighter
                    tertiary: '#16213e',   // Panel BG
                },
                accent: {
                    primary: '#00ff9f',    // Neon Green (Success/Active)
                    secondary: '#00d4ff',  // Cyan (Info/Links)
                },
                text: {
                    primary: '#ffffff',
                    secondary: '#b0b0b0',
                },
                border: '#2d2d44',
                error: '#ff4757',
                success: '#2ed573',
            },
            fontFamily: {
                sans: ['Segoe UI', 'Inter', 'system-ui', 'sans-serif'],
            },
        },
    },
    plugins: [],
}
