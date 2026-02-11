# Contributing to KAAL

Thank you for your interest in contributing to the KAAL framework!

## Code of Conduct

- Use this framework ethically and legally
- Only test on authorized systems
- Follow responsible disclosure practices
- Respect intellectual property rights

## How to Contribute

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/my-feature`
3. **Make your changes** with clear, documented code
4. **Add tests** for new functionality
5. **Run the test suite**: `python -m unittest discover tests`
6. **Commit your changes**: `git commit -m "Add feature X"`
7. **Push to your fork**: `git push origin feature/my-feature`
8. **Submit a pull request**

## Coding Standards

- Follow PEP 8 for Python code
- Use descriptive variable and function names
- Add docstrings to all public functions
- Keep functions focused and modular
- Add logging at appropriate levels (DEBUG, INFO, ERROR)

## Plugin Development

New plugins are welcomed! See the [Plugin Development Guide](README.md#plugin-development) for details.

### Required Files

- `plugin.json` - Plugin manifest
- `main.py` - Plugin wrapper class
- Implementation files in `src/`

### Testing Plugins

- Test plugin discovery: `kaal plugin list`
- Test building: `kaal build --module your_plugin`
- Add unit tests to `tests/`

## Reporting Issues

- Use GitHub Issues
- Provide clear reproduction steps
- Include system information (OS, Python version)
- Attach relevant log files from `~/.kaal/logs/`

## Security

If you discover a security vulnerability:
1. **Do NOT** open a public issue
2. Contact maintainers privately
3. Provide detailed information
4. Allow time for a fix before disclosure

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
