import React, { useState, useRef, useEffect } from 'react';
import { Bot, Send, X } from 'lucide-react';

const AIChat = () => {
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState([
        { role: 'assistant', content: 'Hello! I am KAAL Copilot. Ask me anything about the framework, command syntax, or post‑deployment assessment techniques.' }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const sendMessage = async () => {
        if (!input.trim()) return;

        const userMessage = { role: 'user', content: input };
        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);

        try {
            const response = await fetch('/api/copilot', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: input })
            });
            const data = await response.json();
            setMessages(prev => [...prev, { role: 'assistant', content: data.answer }]);
        } catch (error) {
            setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error. Please make sure Ollama is running.' }]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    return (
        <>
            {/* Chat Toggle Button */}
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`fixed bottom-6 right-6 p-4 rounded-full shadow-lg transition-all z-50 ${isOpen ? 'bg-kaal-error' : 'bg-kaal-accent'
                    }`}
            >
                {isOpen ? <X className="h-6 w-6 text-white" /> : <Bot className="h-6 w-6 text-white" />}
            </button>

            {/* Chat Window */}
            {isOpen && (
                <div className="fixed bottom-24 right-6 w-96 h-[600px] bg-kaal-surface/95 backdrop-blur-md rounded-lg shadow-2xl border border-kaal-surface2 flex flex-col z-50">
                    {/* Header */}
                    <div className="p-4 border-b border-kaal-surface2 flex items-center space-x-3">
                        <Bot className="h-6 w-6 text-kaal-accent" />
                        <div>
                            <h3 className="font-semibold text-white">KAAL Copilot</h3>
                            <p className="text-xs text-kaal-textMuted">Offline • Unrestricted</p>
                        </div>
                    </div>

                    {/* Messages */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-4">
                        {messages.map((msg, idx) => (
                            <div
                                key={idx}
                                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                <div
                                    className={`max-w-[80%] rounded-lg p-3 ${msg.role === 'user'
                                            ? 'bg-kaal-accent text-white'
                                            : 'bg-kaal-surface2 text-kaal-text'
                                        }`}
                                >
                                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                                </div>
                            </div>
                        ))}
                        {isLoading && (
                            <div className="flex justify-start">
                                <div className="bg-kaal-surface2 rounded-lg p-3">
                                    <div className="flex space-x-1">
                                        <div className="w-2 h-2 bg-kaal-textMuted rounded-full animate-bounce"></div>
                                        <div className="w-2 h-2 bg-kaal-textMuted rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                                        <div className="w-2 h-2 bg-kaal-textMuted rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                                    </div>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Input */}
                    <div className="p-4 border-t border-kaal-surface2">
                        <div className="flex items-center space-x-2">
                            <textarea
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyPress={handleKeyPress}
                                placeholder="Ask a question..."
                                className="flex-1 bg-kaal-surface2 border border-kaal-surface2 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-kaal-accent resize-none text-white placeholder-gray-500"
                                rows="1"
                            />
                            <button
                                onClick={sendMessage}
                                disabled={isLoading || !input.trim()}
                                className="p-2 bg-kaal-accent rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-kaal-accent/80 transition-colors"
                            >
                                <Send className="h-5 w-5 text-white" />
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default AIChat;
