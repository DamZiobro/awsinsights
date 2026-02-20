#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2021 Damian Ziobro - XMementoIT Limited <damian@xmementoit.com>
#
# Distributed under terms of the MIT license.

"""Setup script for awsinsights"""

import os.path
from setuptools import setup

# The directory containing this file
HERE = os.path.abspath(os.path.dirname(__file__))

# The text of the README file
with open(os.path.join(HERE, "README.md")) as fid:
    README = fid.read()

# This call to setup() does all the work
setup(
    name="awsinsights",
    version="1.0.5",
    description="Get, sort and analyse AWS CloudWatch logs from multiple log groups using AWS CloudWatch Insights service",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/DamZiobro/awsinsights",
    author="Damian Ziobro",
    author_email="damian@xmementoit.com",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
    packages=["awsinsights"],
    include_package_data=True,
    install_requires=[
        'boto3>=1.13.5',
    ],
    entry_points={"console_scripts": ["awsinsights=awsinsights.__main__:main"]},
    python_requires='>=3.3',
)
