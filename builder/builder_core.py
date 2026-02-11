import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any
from core.config import Config
from core.plugin_loader import PluginLoader
from compat.hybrid_generator import HybridGenerator
from core.logger import setup_logger

log = setup_logger("builder")

class KAALBuilder:
    """Compiles agent modules and loaders for various platforms."""
    def __init__(self, config: Config):
        self.config = config
        self.plugins = PluginLoader([Path("plugins")]).discover()
        self.generator = HybridGenerator()
        if config.get("ai.deepseek_key"):
            self.generator.enable_deepseek(config.get("ai.deepseek_key"))
        if config.get("ai.ollama", False):
            self.generator.enable_ollama()

    def build_module(self, plugin_id: str, platform: str,
                     output_dir: str, mutate: bool = True) -> str:
        """Build an agent module from a plugin."""
        if plugin_id not in self.plugins["module"]:
            raise ValueError(f"Module plugin {plugin_id} not found")
        plugin = self.plugins["module"][plugin_id]
        log.info(f"Building module {plugin_id} for {platform}")

        build_dir = Path(output_dir) / plugin_id
        build_dir.mkdir(parents=True, exist_ok=True)

        plugin_path = Path(f"plugins/modules/{plugin_id}")
        src_dir = plugin_path / "src"
        if not src_dir.exists():
            raise FileNotFoundError(f"Source directory {src_dir} not found")

        # Copy source files
        for src_file in src_dir.glob("*.[ch]*"):
            shutil.copy(src_file, build_dir)

        # Locate main source file
        main_src = None
        for ext in ['.cpp', '.c']:
            candidate = build_dir / f"agent{ext}"
            if candidate.exists():
                main_src = candidate
                break
        if not main_src:
            raise FileNotFoundError("No main source file found (agent.cpp/c)")

        # Apply compatibility transformations if requested
        if mutate:
            log.info("Applying compatibility transformations...")
            with open(main_src, 'r') as f:
                code = f.read()
            use_ds = self.config.get("ai.use_deepseek", False)
            use_ol = self.config.get("ai.use_ollama", False)
            mutated = self.generator.mutate(code, platform,
                                           use_deepseek=use_ds,
                                           use_ollama=use_ol)
            with open(main_src, 'w') as f:
                f.write(mutated)

        # Compile
        if platform == 'windows':
            out_file = build_dir / "agent.exe"
            cmd = [
                "x86_64-w64-mingw32-g++",
                "-Os", "-s", "-static-libgcc", "-static-libstdc++",
                "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                "-lwininet", "-ladvapi32", "-luser32", "-lgdi32", "-lws2_32",
                str(main_src), "-o", str(out_file)
            ]
        elif platform == 'linux':
            out_file = build_dir / "agent.elf"
            cmd = [
                "g++", "-Os", "-s", "-static",
                "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                str(main_src), "-o", str(out_file)
            ]
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        log.debug(f"Compile command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"Compilation failed: {result.stderr}")
            raise RuntimeError("Compilation failed")

        log.info(f"Agent module built: {out_file}")
        return str(out_file)
