#!/usr/bin/env python

from setuptools import setup

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup(
    name="chimenea",
    version="0.1.0",
    packages=['chimenea'],
    description="Automated image-synthesis of multi-epoch radio-telescope data.",
    author="Tim Staley",
    author_email="timstaley337@gmail.com",
    url="https://github.com/timstaley/chimenea",
    install_requires=required,
)
