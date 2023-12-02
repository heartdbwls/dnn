from setuptools import setup, find_packages, Extension

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="dnn",
    version="0.1.dev1",
    author="Shivam Shrirao",
    description="A high level deep learning library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/heartdbwls/dnn",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 1 - Planning",
        "Environment :: GPU :: NVIDIA CUDA",
    ],
    python_requires='>=3.6',
    package_data={"": ["libctake.so"]}
)