from setuptools import setup, find_packages

setup(
    name="openscad-batch-export",
    version="2.0.0",
    description="Batch export STL files from OpenSCAD using CSV or JSON parameters, and convert between CSV and JSON.",
    author="Cameron K. Brooks",
    author_email="cambrooks3393@gmail.com",
    url="https://github.com/yourusername/OpenSCAD-Batch-Export",
    packages=find_packages(),
    # Removed py_modules since 'export' and 'gui' are part of the 'openscad_export' package
    entry_points={
        "console_scripts": [
            "openscad-export=openscad_export.export:main",
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
