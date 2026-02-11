#!/usr/bin/env python3
import click
from pathlib import Path
from core.config import Config
from builder.builder_core import KAALBuilder
from console.relay_manager import RelayManager

@click.group()
@click.option('--verbose', is_flag=True, help='Enable verbose debug logging')
@click.pass_context
def cli(ctx, verbose):
    """KAAL v3.0 – Remote Administration & Security Assessment Framework"""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)


@cli.command()
@click.option('--platform', default='windows', help='Target platform (windows, linux, android)')
@click.option('--module', default='windows_agent', help='Agent module plugin ID')
@click.option('--output', default='./build', help='Output directory')
@click.option('--no-compat', is_flag=True, help='Disable compatibility (polymorphic) generation')
@click.pass_context
def build(ctx, platform, module, output, no_compat):
    """Build a remote administration agent module."""
    config = Config()
    builder = KAALBuilder(config)
    out = builder.build_module(module, platform, output, mutate=not no_compat)
    click.secho(f"[+] Agent module built: {out}", fg='green')


@cli.command()
def gui():
    """Launch the web‑based administration dashboard."""
    import uvicorn
    from web.server import app
    click.secho("[*] Starting KAAL Web Console at http://localhost:5000", fg='blue')
    uvicorn.run(app, host="127.0.0.1", port=5000)


@cli.command()
@click.option('--relay', help='Relay type (telegram, discord, github)')
@click.option('--token', help='API token for the relay')
@click.option('--channel', help='Channel/chat identifier')
def console(relay, token, channel):
    """Start the administration console with message relays."""
    from console.relay_manager import RelayManager
    mgr = RelayManager()
    if relay == 'telegram' and token and channel:
        mgr.init_telegram(token, channel)
    elif relay == 'discord' and token and channel:
        mgr.init_discord(token, int(channel))
    elif relay == 'github' and token and channel:
        mgr.init_github(token, channel)
    else:
        click.secho("[-] Please specify a valid relay with --relay, --token, --channel", fg='red')
        return

    mgr.start_pollers()
    click.secho("[*] Administration console running. Press Ctrl+C to stop.", fg='blue')
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.secho("[!] Shutting down...", fg='yellow')


@cli.group()
def plugin():
    """Manage KAAL plugins."""
    pass


@plugin.command('list')
def plugin_list():
    """List all installed plugins."""
    from core.plugin_loader import PluginLoader
    loader = PluginLoader([Path("plugins")])
    plugins = loader.discover()
    for ptype, plist in plugins.items():
        click.secho(f"\n[{ptype.upper()}]", fg='cyan')
        for pid, p in plist.items():
            click.echo(f"  {pid} v{p.version} – {p.name}")


@plugin.command('install')
@click.argument('path')
def plugin_install(path):
    """Install a plugin from a directory or zip file."""
    import shutil
    src = Path(path)
    if not src.exists():
        click.secho("[-] Path not found", fg='red')
        return
    dst = Path("plugins") / src.name
    if dst.exists():
        click.secho("[-] Plugin already exists", fg='red')
        return
    shutil.copytree(src, dst)
    click.secho(f"[+] Plugin installed to {dst}", fg='green')


@cli.command()
@click.argument('question', nargs=-1)
def ask(question):
    """Ask the AI assistant a question."""
    q = ' '.join(question)
    if not q:
        click.echo("Usage: kaal ask 'your question'")
        return
    from assistant.ai_copilot import AICopilot
    ai = AICopilot()
    ans = ai.ask(q)
    click.echo(ans)


if __name__ == '__main__':
    cli()
