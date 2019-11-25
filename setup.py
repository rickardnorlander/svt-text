import setuptools
import svt_text.svt_text as impl

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="svt-text",
    version=impl.__version__,
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
    python_requires=">=3.5",
    install_requires = ["requests"]
)
