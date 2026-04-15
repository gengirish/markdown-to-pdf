import os

from setuptools import find_packages, setup

_ROOT = os.path.dirname(os.path.abspath(__file__))
_README = os.path.join(_ROOT, "README.md")
_long_description = ""
if os.path.isfile(_README):
    with open(_README, encoding="utf-8") as f:
        _long_description = f.read()

setup(
    name="intelliforge",
    version="2.0.0",
    description="Python SDK for the IntelliForge Certificate API",
    long_description=_long_description,
    long_description_content_type="text/markdown",
    url="https://md2pdf.intelliforge.tech",
    packages=find_packages(include=["intelliforge", "intelliforge.*"]),
    python_requires=">=3.9",
    install_requires=["httpx>=0.24.0,<1.0.0"],
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Typing :: Typed",
    ],
)
