import sys
import setuptools
from red_star.rs_version import version

if sys.version_info < (3, 6, 0):
    raise RuntimeError("Red Star requires Python version 3.6 or greater.")


def get_requirements():
    with open("requirements.txt", encoding="utf-8") as fd:
        return fd.read()


setuptools.setup(
    name='red_star',
    version=version,
    description='Red Star - A general-purpose Discord bot with bonus shouting.',
    url='https://github.com/medeor413/Red_Star',
    long_description='',
    packages=setuptools.find_packages(),
    package_data={'red_star': ['_default_files/*.json']},
    license='MIT',
    platforms='any',
    install_requires=get_requirements(),
    dependency_links=['https://github.com/Rapptz/discord.py/archive/rewrite.zip#egg=discord.py'],
    entry_points={
        'console_scripts': ['red_star = red_star:main']
    },
    zip_safe=False
)
