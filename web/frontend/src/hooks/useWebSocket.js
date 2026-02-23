import { useState, useEffect, useRef } from 'react';

export const useWebSocket = (url) => {
    const [isConnected, setIsConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState(null);
    const ws = useRef(null);

    useEffect(() => {
        ws.current = new WebSocket(url);

        ws.current.onopen = () => {
            setIsConnected(true);
        };

        ws.current.onclose = () => {
            setIsConnected(false);
            // Attempt reconnect after 3 seconds
            setTimeout(() => {
                ws.current = new WebSocket(url);
            }, 3000);
        };

        ws.current.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        ws.current.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                setLastMessage(data);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
            }
        };

        return () => {
            ws.current.close();
        };
    }, [url]);

    const sendMessage = (message) => {
        if (ws.current && isConnected) {
            ws.current.send(JSON.stringify(message));
        }
    };

    return { isConnected, lastMessage, sendMessage };
};
