#!/usr/bin/env python

from setuptools import setup, find_packages

tests_require = [
    'hypothesis',
    'pycodestyle',
    'pylint',
    'pytest',
    'pytest-cov',
    'pytest-timeout',
    'pytest-httpserver',
    'moto',
]
doc_require = [
    'Sphinx',
    'sphinx_rtd_theme',
    'sphinx_autodoc_typehints',  # Propagate mypy info into docs
    'sphinx-click',
    'recommonmark',
    'setuptools',  # version related dependencies
    'setuptools_scm[toml]',
]

extras_require = {
    'performance': ['ciso8601', 'bottleneck'],
    'distributed': ['distributed', 'dask[distributed]'],
    'doc': doc_require,
    's3': ['boto3', 'botocore'],
    'test': tests_require,
    'cf': ['compliance-checker>=4.0.0'],
}

extras_require['dev'] = sorted(set(sum([extras_require[k] for k in [
    'test',
    'doc',
    'performance',
    's3',
    'distributed',
]], [])))

# An 'all' option, following ipython naming conventions.
extras_require['all'] = sorted(set(sum(extras_require.values(), [])))

extra_plugins = dict(read=[], write=[], index=[])

setup(
    name='datacube_sp',
    python_requires='>=3.8.0',

    url='https://github.com/xwl742/datacubesp01',
    author='Open Data Cube',
    maintainer='Open Data Cube',
    maintainer_email='',
    description='An analysis environment for satellite and other earth observation data',
    long_description=open('README.rst').read(),
    long_description_content_type='text/x-rst',
    license='Apache License 2.0',
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Operating System :: POSIX :: BSD",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Scientific/Engineering :: GIS",
        "Topic :: Scientific/Engineering :: Information Analysis",
    ],

    packages=find_packages(
        exclude=('tests', 'tests.*',
                 'integration_tests', 'integration_tests.*')
    ),
    package_data={
        '': ['*.yaml', '*/*.yaml'],
        'datacube_sp': ['py.typed'],
    },
    scripts=[],
    install_requires=[
        'affine',
        'pyproj>=2.5',
        'shapely>=1.6.4',
        'cachetools',
        'click>=5.0',
        'cloudpickle>=0.4',
        'dask[array]',
        'distributed',
        'jsonschema',
        'netcdf4',
        'numpy',
        'psycopg2',
        'lark',
        'pandas',
        'python-dateutil',
        'pyyaml',
        'rasterio>=1.3.2',  # Warping broken in 1.3.0 and 1.3.1
        'sqlalchemy',
        'GeoAlchemy2',
        'toolz',
        'xarray>=0.9,<2022.6',  # >0.9 fixes most problems with `crs` attributes being lost
    ],
    extras_require=extras_require,
    tests_require=tests_require,

    entry_points={
        'console_scripts': [
            'datacube_sp = datacube_sp.scripts.cli_app:cli',
            'datacube_sp-search = datacube_sp.scripts.search_tool:cli',
            'datacube_sp-worker = datacube_sp.execution.worker:main',
        ],
        'datacube_sp.plugins.io.read': [
            'netcdf = datacube_sp.drivers.netcdf.driver:reader_driver_init',
            *extra_plugins['read'],
        ],
        'datacube_sp.plugins.io.write': [
            'netcdf = datacube_sp.drivers.netcdf.driver:writer_driver_init',
            *extra_plugins['write'],
        ],
        'datacube_sp.plugins.index': [
            'default = datacube_sp.index.postgres.index:index_driver_init',
            'null = datacube_sp.index.null.index:index_driver_init',
            'memory = datacube_sp.index.memory.index:index_driver_init',
            'postgis = datacube_sp.index.postgis.index:index_driver_init',
            *extra_plugins['index'],
        ],
    },
)
