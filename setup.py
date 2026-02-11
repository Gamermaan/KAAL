from setuptools import setup, find_packages

setup(
    name="kaal-framework",
    version="3.0.0",
    description="KAAL – Modern Remote Administration & Security Assessment Framework",
    author="KAAL Team",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "click>=8.1.0",
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "websockets>=12.0",
        "requests>=2.31.0",
        "pyyaml>=6.0",
        "sentence-transformers>=2.2.2",
        "chromadb>=0.4.18",
        "pefile>=2023.2.7",
        "capstone>=5.0.1",
        "textual>=0.41.0"
    ],
    entry_points={
        "console_scripts": [
            "kaal = cli.main:cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: System :: Systems Administration",
        "Topic :: Security",
    ],
    python_requires=">=3.8",
)
