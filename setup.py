from setuptools import setup, find_packages

setup(
    name="promptkit",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "anthropic>=0.40.0",
        "pyyaml>=6.0",
        "click>=8.1",
        "rich>=13.0",
        "pydantic>=2.0",
    ],
    entry_points={
        "console_scripts": [
            "promptkit=promptkit.cli:cli",
        ],
    },
    python_requires=">=3.10",
)
