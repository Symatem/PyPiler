# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name = 'PyPiler',
    version = '0.0.1',
    license = 'MIT',
    description = 'DAG based data-flow and control-flow representation for meta programming',
    python_requires = '>=3.3',
    author = 'Alexander Meißner',
    author_email = 'AlexanderMeissner@gmx.net',
    url = 'https://github.com/Symatem/PiPiler',
    packages = ['PyPiler'],
    install_requires = ['tree_sitter >= 0.0.8']
)
