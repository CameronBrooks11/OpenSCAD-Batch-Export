from setuptools import setup, find_packages

setup(
    name="openscad-batch-export",
    version="1.0.0",
    description="Batch export STL files from OpenSCAD using CSV parameters.",
    author="Cameron K. Brooks",
    author_email="cambrooks3393@gmail.com",
    url="https://github.com/yourusername/OpenSCAD-Batch-Export",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "openscad-export=openscad_export.export:batch_export",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: AGPL 3 License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
