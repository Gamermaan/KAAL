# KAAL v3.0 - Project Structure

This file provides an overview of the KAAL framework directory structure.

```
kaal/
├── core/                      # Core framework components
│   ├── __init__.py
│   ├── plugin_base.py        # Plugin base classes
│   ├── plugin_loader.py      # Plugin discovery and loading
│   ├── logger.py             # Centralized logging
│   ├── config.py             # YAML configuration manager
│   └── state_manager.py      # Shared state for CLI/Web/AI
│
├── cli/                       # Command-line interface
│   ├── __init__.py
│   └── main.py               # Click-based CLI commands
│
├── console/                   # Agent communication relays
│   ├── __init__.py
│   ├── relay_manager.py      # Relay orchestrator
│   ├── telegram_relay.py     # Telegram Bot API relay
│   ├── discord_relay.py      # Discord bot relay
│   └── github_relay.py       # GitHub Gist dead-drop
│
├── compat/                    # Code transformation engines
│   ├── __init__.py
│   ├── rule_generator.py     # Rule-based transformations
│   ├── deepseek_generator.py # DeepSeek API integration
│   ├── ollama_generator.py   # Local Ollama integration
│   └── hybrid_generator.py   # Orchestrates all generators
│
├── builder/                   # Compilation system
│   ├── __init__.py
│   └── builder_core.py       # Cross-platform builder
│
├── assistant/                 # AI copilot
│   ├── __init__.py
│   ├── rag_indexer.py        # RAG with ChromaDB
│   └── ai_copilot.py         # Ollama integration
│
├── web/                       # Web dashboard
│   ├── __init__.py
│   └── server.py             # FastAPI server
│
├── plugins/                   # All plugins
│   ├── modules/              # Agent modules
│   │   ├── windows_agent/    # Windows agent (complete)
│   │   ├── linux_agent/      # Linux agent (placeholder)
│   │   └── android_agent/    # Android agent (placeholder)
│   ├── loaders/              # Bootstrap loaders
│   │   ├── win_loader/       # Windows loader (complete)
│   │   └── lin_loader/       # Linux loader (placeholder)
│   ├── assessment/           # Assessment plugins (placeholder)
│   ├── autostart/            # Auto-start plugins (placeholder)
│   ├── compatibility/        # Compatibility plugins (placeholder)
│   └── ai_engines/           # AI engine plugins (placeholder)
│
├── tests/                     # Test suite
│   ├── __init__.py
│   ├── test_core.py          # Core component tests
│   ├── test_plugin_loader.py # Plugin loader tests
│   ├── test_compat.py        # Compatibility tests
│   ├── test_relays.py        # Relay encryption tests
│   └── test_builder.py       # Builder tests
│
├── docs/                      # Documentation
│   └── index.md              # Documentation index
│
├── data/                      # Runtime data (gitignored)
├── logs/                      # Log files (gitignored)
├── config.yaml               # Main configuration
├── setup.py                  # Package definition
├── README.md                 # Project README
├── LICENSE                   # MIT License
└── .gitignore                # Git exclusions
```

## Component Overview

### Core Framework
- **plugin_base.py**: Abstract base classes for all plugin types
- **plugin_loader.py**: Dynamic plugin discovery and instantiation
- **logger.py**: File and console logging with DEBUG level
- **config.py**: YAML configuration with dot notation access
- **state_manager.py**: WebSocket state for real-time updates

### CLI
- Commands: `build`, `gui`, `console`, `plugin`, `ask`
- Global `--verbose` flag for debug logging

### Console Relays
- Telegram Bot API polling
- Discord channel monitoring  
- GitHub Gist dead-drop
- XOR encryption for all messages

### Compatibility Generators
- Rule-based: variable renaming, function reordering, dead code, string encryption
- DeepSeek API: AI-powered code transformation
- Ollama: Local AI transformation
- Hybrid: Combines all methods

### Builder
- MinGW for Windows (cross-compilation)
- GCC for Linux
- Applies code transformations before compilation
- Size optimization flags

### Plugins
- **windows_agent**: Full C++ agent with HTTP, cmd exec, screen capture
- **win_loader**: 3KB bootstrap with environment detection
- Placeholders for Linux, Android, and other platforms
