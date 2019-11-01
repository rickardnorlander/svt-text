import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="svt-text",
    version="0.1.0",
    author="Rickard Norlander",
    author_email="rickard@rinor.se",
    description="Displays SVT-text in a terminal",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rickardnorlander/svt-text",
    packages=["svt_text"],
    entry_points={
        "console_scripts": [
            "svt-text = svt_text.svt_text:main",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires = ["requests"]
)
