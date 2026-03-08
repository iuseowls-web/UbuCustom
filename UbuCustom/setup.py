#!/usr/bin/env python3
"""
Setup script for UbuCustom - Custom Ubuntu ISO Creator
"""

from setuptools import setup, find_packages
import os

# Read README
readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
if os.path.exists(readme_path):
    with open(readme_path, 'r', encoding='utf-8') as f:
        long_description = f.read()
else:
    long_description = "UbuCustom - A tool for creating custom Ubuntu ISO images"

setup(
    name='ubucustom',
    version='1.0.0',
    author='UbuCustom Team',
    author_email='ubucustom@example.com',
    description='Custom Ubuntu ISO Creator - A tool similar to Cubic',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/yourusername/ubucustom',
    packages=find_packages(),
    scripts=[
        'bin/ubucustom',
        'bin/ubucustom-gui',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: System :: Operating System',
        'Topic :: Utilities',
    ],
    python_requires='>=3.8',
    install_requires=[
        # No external Python dependencies required
        # Uses only standard library
    ],
    extras_require={
        'dev': [
            'pytest',
            'pytest-cov',
            'flake8',
            'mypy',
        ],
    },
    entry_points={
        'console_scripts': [
            'ubucustom=ubucustom.cli:main',
            'ubucustom-gui=ubucustom.gui:main',
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
