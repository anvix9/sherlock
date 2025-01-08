from setuptools import setup, find_packages

setup(
    name="sherlock-lit",
    version="0.1.3",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        # List your package dependencies here
        "requests>=2.25.1",
        "docling",
        "arxiv",
        "ollama",
    ],
    python_requires=">=3.11",
    entry_points={
        'console_scripts': [
            'sherlock_lit=sherlock_lit.cli:main'
            ]
        },
)


