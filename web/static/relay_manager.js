// Relay Management Functions

async function loadRelayList() {
    try {
        const response = await fetch('/api/relay/list');
        const data = await response.json();
        const relays = data.relays || [];

        // Also load proxy agents
        const agentResp = await fetch('/api/relay/agents');
        const agentData = await agentResp.json();
        const proxyAgents = agentData.agents || {};

        const container = document.getElementById('relayListContainer');

        if (relays.length === 0) {
            container.innerHTML = `
                <table class="agent-table">
                    <thead>
                        <tr>
                            <th>Relay ID</th>
                            <th>Type</th>
                            <th>Agents</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 40px;">
                                <i class="fas fa-info-circle"></i> No relays configured. Click "Add Relay" to add Telegram or Discord relay.
                            </td>
                        </tr>
                    </tbody>
                </table>
            `;
        } else {
            const rows = relays.map(relay => {
                const agentCount = Object.values(proxyAgents).filter(a =>
                    a.relay_type === relay.type && a.relay_id === relay.id
                ).length;

                return `
                    <tr>
                        <td>${relay.id}</td>
                        <td><i class="fab fa-${relay.type}"></i> ${relay.type.charAt(0).toUpperCase() + relay.type.slice(1)}</td>
                        <td>${agentCount} agent(s)</td>
                        <td><span class="status-dot online"></span> Active</td>
                        <td>
                            <button class="btn btn-danger" style="font-size: 12px; padding: 6px 12px;" onclick="removeRelay('${relay.type}', '${relay.id}')">
                                <i class="fas fa-trash"></i> Remove
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

            container.innerHTML = `
                <table class="agent-table">
                    <thead>
                        <tr>
                            <th>Relay ID</th>
                            <th>Type</th>
                            <th>Agents</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            `;
        }
    } catch (error) {
        console.error('Load relay list error:', error);
        document.getElementById('relayListContainer').innerHTML = `
            <p style="text-align: center; color: var(--color-danger); padding: 40px;">
                <i class="fas fa-exclamation-triangle"></i> Failed to load relays
            </p>
        `;
    }
}

function showAddRelayModal() {
    const modal = document.createElement('div');
    modal.style = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 10000; display: flex; align-items: center; justify-content: center;';
    modal.innerHTML = `
        <div style="background: var(--surface-secondary); padding: 30px; border-radius: 12px; max-width: 500px; width: 90%;">
            <h3 style="margin-bottom: 20px;"><i class="fas fa-plus-circle"></i> Add Relay</h3>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px;">Relay Type</label>
                <select id="relayType" class="form-input" onchange="updateRelayFields()">
                    <option value="telegram">Telegram</option>
                    <option value="discord">Discord</option>
                </select>
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px;">Relay ID</label>
                <input type="text" id="relayId" class="form-input" placeholder="e.g., my-telegram-relay" />
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px;">Bot Token</label>
                <input type="text" id="relayToken" class="form-input" placeholder="Bot token from @BotFather or Discord Developer Portal" />
            </div>
            
            <div id="chatIdField" style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px;">Chat ID (Telegram)</label>
                <input type="text" id="relayChatId" class="form-input" placeholder="Your Telegram chat ID" />
            </div>
            
            <div id="channelIdField" style="margin-bottom: 20px; display: none;">
                <label style="display: block; margin-bottom: 8px;">Channel ID (Discord)</label>
                <input type="text" id="relayChannelId" class="form-input" placeholder="Discord channel ID" />
            </div>
            
            <div style="display: flex; gap: 10px; margin-top: 30px;">
                <button class="btn btn-primary" onclick="submitAddRelay()"><i class="fas fa-check"></i> Add Relay</button>
                <button class="btn btn-secondary" onclick="closeModal()"><i class="fas fa-times"></i> Cancel</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    window.currentModal = modal;
}

function updateRelayFields() {
    const type = document.getElementById('relayType').value;
    document.getElementById('chatIdField').style.display = type === 'telegram' ? 'block' : 'none';
    document.getElementById('channelIdField').style.display = type === 'discord' ? 'block' : 'none';
}

function closeModal() {
    if (window.currentModal) {
        window.currentModal.remove();
        window.currentModal = null;
    }
}

async function submitAddRelay() {
    const type = document.getElementById('relayType').value;
    const relayId = document.getElementById('relayId').value.trim();
    const token = document.getElementById('relayToken').value.trim();
    const chatId = document.getElementById('relayChatId').value.trim();
    const channelId = document.getElementById('relayChannelId').value.trim();

    if (!relayId || !token) {
        alert('Relay ID and Token are required!');
        return;
    }

    if (type === 'telegram' && !chatId) {
        alert('Chat ID is required for Telegram!');
        return;
    }

    if (type === 'discord' && !channelId) {
        alert('Channel ID is required for Discord!');
        return;
    }

    const payload = {
        relay_type: type,
        relay_id: relayId,
        token: token
    };

    if (type === 'telegram') payload.chat_id = chatId;
    if (type === 'discord') payload.channel_id = channelId;

    try {
        const response = await fetch('/api/relay/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            alert(`✅ Relay "${relayId}" added successfully! Agents using this relay will appear in the agent list automatically.`);
            closeModal();
            loadRelayList(); // Refresh list
        } else {
            const error = await response.json();
            alert(`❌ Failed to add relay: ${error.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Add relay error:', error);
        alert('❌ Failed to add relay. Check console for details.');
    }
}

async function removeRelay(type, relayId) {
    if (!confirm(`Remove relay "${relayId}"? Connected agents will become unreachable.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/relay/${type}/${relayId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            alert(`✅ Relay "${relayId}" removed`);
            loadRelayList();
        } else {
            alert('❌ Failed to remove relay');
        }
    } catch (error) {
        console.error('Remove relay error:', error);
        alert('❌ Failed to remove relay');
    }
}
