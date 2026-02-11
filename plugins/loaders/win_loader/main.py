from core.plugin_base import LoaderPlugin
from pathlib import Path

class WindowsLoader(LoaderPlugin):
    @property
    def id(self): return "win_loader"
    @property
    def name(self): return "Windows KAAL Loader"
    @property
    def version(self): return "1.0.0"
    @property
    def type(self): return "loader"

    def generate(self, target_platform: str, output_dir: str) -> str:
        if target_platform != "windows":
            raise ValueError("Platform mismatch")
        src = Path(__file__).parent / "src" / "bootstrap.c"
        dst = Path(output_dir) / "loader.c"
        dst.write_text(src.read_text())
        return str(dst)
