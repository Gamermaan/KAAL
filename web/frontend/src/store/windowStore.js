import { create } from 'zustand';

export const useWindowStore = create((set, get) => ({
    windows: [
        { id: 'dashboard', title: 'Dashboard', type: 'dashboard', closable: false }
    ],
    activeWindowId: 'dashboard',

    openWindow: (window) => {
        const { windows, activeWindowId } = get();
        const existing = windows.find(w => w.id === window.id);

        if (existing) {
            set({ activeWindowId: window.id });
        } else {
            set({
                windows: [...windows, { ...window, closable: window.closable !== false }],
                activeWindowId: window.id
            });
        }
    },

    closeWindow: (id) => {
        const { windows, activeWindowId } = get();
        const newWindows = windows.filter(w => w.id !== id);

        // If we closed the active window, switch to the last one
        let newActiveId = activeWindowId;
        if (activeWindowId === id) {
            newActiveId = newWindows[newWindows.length - 1]?.id || 'dashboard';
        }

        set({ windows: newWindows, activeWindowId: newActiveId });
    },

    focusWindow: (id) => set({ activeWindowId: id }),

    closeAll: () => set({
        windows: [{ id: 'dashboard', title: 'Dashboard', type: 'dashboard', closable: false }],
        activeWindowId: 'dashboard'
    })
}));
