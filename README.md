# KAAL v3.0 – Kernel‑Aware Administrative Link

**KAAL** is a modern, extensible remote administration framework designed for security professionals, system administrators, and authorized penetration testers. It enables secure, efficient management of remote systems through encrypted relay channels, with AI‑assisted automation and cross‑platform support.

## 🔒 Ethical Use Warning

KAAL is intended **only** for use on systems you own or have explicit written permission to test. Unauthorized access to computer systems is illegal. The developers assume no liability and are not responsible for any misuse or damage caused by this program.

## ✨ Features

- **No inbound connections** – Agents communicate via Telegram, Discord, or GitHub Gist relays. Your administration console stays hidden.
- **Polymorphic code generator** – Rule‑based + AI (DeepSeek/Ollama) transformations create unique binaries every build, defeating static signatures.
- **Plugin architecture** – Every component (agents, loaders, assessment modules, utilities) is a drop‑in plugin.
- **Offline AI Copilot** – Local LLM with RAG answers questions, generates scripts, and provides contextual assistance.
- **Dual‑mode interface** – Fast CLI for scripting, optional web dashboard for rich visualisation.
- **Cross‑platform** – Supports Windows, Linux, and Android (extensible to macOS/iOS via plugins).

## 🚀 Quick Start

### Installation

1. **Install dependencies:**
   ```bash
   pip install -e .
   ```

2. **Configure relay endpoints:**
   Edit `config.yaml` and add your Telegram/Discord tokens and channel IDs.

### Basic Usage

1. **Build a Windows agent:**
   ```bash
   kaal build --platform windows --module windows_agent --output ./build
   ```

2. **Start the administration console with Telegram relay:**
   ```bash
   kaal console --relay telegram --token YOUR_BOT_TOKEN --channel YOUR_CHAT_ID
   ```

3. **Launch the web dashboard:**
   ```bash
   kaal gui
   ```

4. **Ask the AI assistant:**
   ```bash
   kaal ask "how do I create a custom loader?"
   ```

## 🧪 Testing & Debugging

### Running Unit Tests

Execute the test suite:
```bash
python -m unittest discover tests
```

Or with pytest:
```bash
pytest tests/
```

### Debugging with Verbose Mode

Enable debug logging for all operations:
```bash
kaal --verbose build --platform windows
```

### Log Files

All operations are logged to `~/.kaal/logs/`. Each component has its own log file:
- `builder.log` – Compilation and build errors
- `console.log` – Relay communications and agent messages
- `compat.log` – Code transformation operations

### Common Issues & Solutions

**Issue: MinGW compiler not found**
- Solution: Install MinGW-w64 and add to PATH
- Linux: `apt-get install mingw-w64`
- Windows: Download from mingw-w64.org

**Issue: Agent not connecting to console**
- Check firewall rules for console port (default 8080)
- Verify relay credentials in config.yaml
- Check agent logs for HTTP errors

**Issue: AI Copilot not responding**
- Ensure Ollama is running: `ollama serve`
- Pull the model: `ollama pull deepseek-coder:6.7b`
- Check Ollama URL in assistant/ai_copilot.py

**Issue: Build fails with "plugin not found"**
- Run `kaal plugin list` to see available plugins
- Check plugin.json manifest syntax
- Ensure plugin directory structure matches spec

### Component Testing

**Test Plugin Loader:**
```bash
python -c "from core.plugin_loader import PluginLoader; from pathlib import Path; print(PluginLoader([Path('plugins')]).discover())"
```

**Test Relay Manager:**
```bash
python -c "from console.relay_manager import RelayManager; mgr = RelayManager(); print('Relay manager initialized')"
```

**Test Code Transformation:**
```bash
python -c "from compat.rule_generator import RuleGenerator; rg = RuleGenerator(); print('Generator ready')"
```

## 🧩 Plugin Development

### Creating a New Agent Module

1. Create plugin directory: `plugins/modules/my_agent/`
2. Add `plugin.json`:
   ```json
   {
       "id": "my_agent",
       "name": "My Custom Agent",
       "version": "1.0.0",
       "type": "module",
       "module_type": "agent",
       "platforms": ["windows"],
       "entry": "main.py",
       "class": "MyAgent"
   }
   ```
3. Create `main.py` implementing `ModulePlugin`
4. Add source code to `src/agent.cpp`
5. Test: `kaal build --platform windows --module my_agent`

### Plugin Architecture

All plugins inherit from base classes in `core/plugin_base.py`:
- `ModulePlugin` – Agent modules (remote admin agents)
- `LoaderPlugin` – Bootstrap loaders (initial deployment)
- `AssessmentPlugin` – Post-deployment assessment tasks
- `UtilityPlugin` – Miscellaneous utilities

See existing plugins in `plugins/` for examples.

## 📁 Directory Structure

```
kaal/
├── core/           # Plugin system, config, logging, state
├── cli/            # Command-line interface
├── console/        # Relay management (Telegram, Discord, GitHub)
├── compat/         # Code transformation engines
├── builder/        # Compilation system
├── assistant/      # AI copilot with RAG
├── web/            # Web dashboard (FastAPI)
├── plugins/        # All plugins
│   ├── modules/    # Agent modules
│   ├── loaders/    # Bootstrap loaders
│   ├── assessment/ # Assessment plugins
│   └── autostart/  # Auto-start mechanisms
├── tests/          # Unit and integration tests
├── data/           # Runtime data (gitignored)
├── logs/           # Log files (gitignored)
├── config.yaml     # Main configuration
└── setup.py        # Package definition
```

## 🔧 Advanced Configuration

### Using AI Code Transformation

Enable DeepSeek API transformation in `config.yaml`:
```yaml
ai:
  deepseek_key: "your-api-key-here"
  use_deepseek: true
```

Or use local Ollama:
```yaml
ai:
  ollama: true
  use_ollama: true
```

### Custom Relay Endpoints

Configure multiple relay channels:
```yaml
console:
  relays:
    telegram_token: "123456:ABC-DEF"
    telegram_chat: "@your_channel"
    discord_token: "your_discord_bot_token"
    discord_channel: 1234567890
```

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📄 License

MIT License. See [LICENSE](LICENSE) file for details.

## ⚠️ Legal Disclaimer

This software is provided for educational and authorized security testing purposes only. The authors and contributors:
- Do NOT endorse or encourage any illegal activities
- Are NOT responsible for any misuse or damage caused by this software
- Require users to comply with all applicable laws and regulations
- Emphasize that unauthorized computer access is a criminal offense

Use this tool responsibly and only on systems you own or have explicit written permission to test.

---

**KAAL – Your remote administration toolkit. Use responsibly.** 🛡️
