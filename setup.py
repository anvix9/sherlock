from setuptools import setup, find_packages

setup(
    name="sherlock",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        # List your package dependencies here
        "requests>=2.25.1",
        "docling",
        "arxiv",
        "ollama",
    ],
    python_requires=">=3.8",
)


