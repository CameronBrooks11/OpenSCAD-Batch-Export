from setuptools import setup, find_packages

setup(
    name="openscad-batch-export",
    version="1.0.0",
    description="Batch export STL files from OpenSCAD using CSV or JSON parameters, and convert between CSV and JSON.",
    author="Cameron K. Brooks",
    author_email="cambrooks3393@gmail.com",
    url="https://github.com/CameronBrooks11/OpenSCAD-Batch-Export",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "openscad-export=openscad_export.export:main",
        ],
        "gui_scripts": [
            "openscad-export-gui=openscad_export.gui:main",
        ],
    },
    install_requires=[],
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: AGPL 3 License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
)
