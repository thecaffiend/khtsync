#!/usr/bin/env python

from setuptools import setup, find_packages

from khtsync.version import __version__

setup(
    name="khtsync",
    version=__version__,
    description="Syncing library using pure python rsync over ssh. Fork of the khtsync gitorious project http://gitorious.org/khtsync",
    author="L. Drew Pihera",
    author_email="dpihera@gmail.com",
    url="",
    packages=find_packages(exclude=["ez_setup", "examples", "tests"]),
    include_package_data=True,
    install_requires=['paramiko'],
    zip_safe=False,
)
