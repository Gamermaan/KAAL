import { create } from 'zustand';

export const useAgentStore = create((set) => ({
    agents: [],
    selectedAgent: null,
    setAgents: (agents) => set({ agents }),
    addAgent: (agent) => set((state) => ({
        agents: [...state.agents, agent]
    })),
    updateAgent: (updatedAgent) => set((state) => ({
        agents: state.agents.map(agent =>
            agent.id === updatedAgent.id ? updatedAgent : agent
        )
    })),
    removeAgent: (agentId) => set((state) => ({
        agents: state.agents.filter(agent => agent.id !== agentId)
    })),
    selectAgent: (agentId) => set((state) => ({
        selectedAgent: state.agents.find(agent => agent.id === agentId)
    })),
    tasks: {},
    addTask: (agentId, task) => set((state) => {
        const agentTasks = state.tasks[agentId] || [];
        // Ensure new tasks are at the start (history view)
        return { tasks: { ...state.tasks, [agentId]: [task, ...agentTasks] } };
    }),
    updateTaskStatus: (agentId, taskId, status, extraData = {}) => set((state) => {
        const agentTasks = state.tasks[agentId] || [];
        const updatedTasks = agentTasks.map(t =>
            t.id === taskId ? { ...t, status, ...extraData } : t
        );
        return { tasks: { ...state.tasks, [agentId]: updatedTasks } };
    }),
}));
