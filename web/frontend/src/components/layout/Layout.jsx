import React, { useEffect } from 'react';
import Sidebar from './Sidebar';
import WorkspaceArea from './WorkspaceArea';
import { useWindowStore } from '../../store/windowStore';

const Layout = () => {
    const { windows, openWindow } = useWindowStore();

    useEffect(() => {
        // Force open dashboard if empty
        if (windows.length === 0) {
            openWindow({ id: 'dashboard', title: 'COMMAND CENTER', type: 'dashboard', closable: false });
        }
    }, [windows, openWindow]);

    return (
        <div style={{
            width: '100vw',
            height: '100vh',
            background: '#222',
            color: 'white',
            display: 'flex',
            position: 'fixed',
            top: 0,
            left: 0,
            zIndex: 99999
        }}>
            {/* DEBUG MODE - NO EFFECTS */}
            <div style={{ padding: '20px', borderRight: '5px solid red', background: '#333' }}>
                <h3 style={{ color: 'red' }}>SIDEBAR CONTAINER</h3>
                <Sidebar />
            </div>
            <div style={{ flex: 1, padding: '20px', position: 'relative', border: '5px solid blue' }}>
                <h1 style={{ color: 'cyan', fontSize: '32px', background: 'black', padding: '10px' }}>
                    VORTEX DEBUG MODE
                </h1>
                <p>If you see this, React is working.</p>
                <div style={{ border: '5px solid lime', height: '80%', padding: '10px', background: '#111' }}>
                    <h3 style={{ color: 'lime' }}>WORKSPACE CONTAINER</h3>
                    <WorkspaceArea />
                </div>
            </div>
        </div>
    );
};

export default Layout;
