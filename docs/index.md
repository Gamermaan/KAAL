# KAAL Framework Documentation

## Overview

KAAL (Kernel-Aware Administrative Link) is a modern remote administration framework designed for authorized security testing and system administration.

## Features

- **Multi-platform support**: Windows, Linux, Android
- **No inbound connections**: Operates via relay channels (Telegram, Discord, GitHub)
- **Polymorphic code generation**: AI-powered and rule-based code transformation
- **Plugin architecture**: Extensible design with drop-in plugins
- **AI assistant**: Local LLM with RAG for contextual help

## Quick Links

- [Installation Guide](../README.md#installation)
- [Plugin Development](../README.md#plugin-development)
- [Testing Guide](../README.md#testing--debugging)
- [Configuration Reference](../config.yaml)

## Architecture

The framework consists of several core components:

1. **Core** - Plugin system, configuration, logging, state management
2. **CLI** - Command-line interface for all operations
3. **Console** - Relay management for agent communication
4. **Compat** - Code transformation engines (rule-based and AI-powered)
5. **Builder** - Cross-platform compilation system
6. **Assistant** - AI copilot with RAG indexing
7. **Web** - Optional web dashboard for visualization

## Security Considerations

- All agent communications are XOR-encrypted
- Environment detection prevents automated analysis
- Relay channels provide operational security
- No direct inbound connections required

## Legal Notice

Use only on authorized systems. Unauthorized access is illegal.
