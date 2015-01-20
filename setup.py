#!/usr/bin/env python

from setuptools import setup


requirements = ['simplejson',
                'drive-casa>=0.6',
                'tkp>=2.0,<3'
]


setup(
    name="chimenea",
    version="0.1.0",
    packages=['chimenea'],
    description="Automated image-synthesis of multi-epoch radio-telescope data.",
    author="Tim Staley",
    author_email="timstaley337@gmail.com",
    url="https://github.com/timstaley/chimenea",
    install_requires=requirements,
)
