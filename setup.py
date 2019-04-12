import sys
import setuptools
from red_star.rs_version import version

if sys.version_info < (3, 7, 0):
    raise RuntimeError("Red Star requires Python version 3.7 or greater.")


def get_requirements():
    with open("requirements.txt", encoding="utf-8") as fd:
        return fd.read()


def long_description():
    with open("README.md", encoding="utf-8") as fd:
        return fd.read()


setuptools.setup(
    name='red_star',
    version=version,
    description='Red Star - A general-purpose Discord bot with bonus shouting.',
    url='https://github.com/medeor413/Red_Star',
    author="Medeor",
    author_email="me@medeor.me",
    long_description=long_description(),
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    package_data={'red_star': ['_default_files/*.json']},
    license='MIT',
    platforms='any',
    install_requires=get_requirements(),
    entry_points={
        'console_scripts': ['red_star = red_star.__main__:main']
    },
    zip_safe=False,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Framework :: AsyncIO",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.7",
        "Topic :: Communications :: Chat"
    ]
)
