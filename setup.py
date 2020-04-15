from glob import glob
from pip import _internal as pip
from setuptools import setup
from subprocess import check_output

_install_requires = [
    'casperfpga',
    'pkginfo',
    'h5py',
    'iniparse',
    'katcp>=0.6.2',
    'matplotlib==2.0.2',
    'numpy',
    'spead2',
    'coloredlogs',
    'tornado>=4.3',
    'lazy-import>=0.2.2'
]

setup(
    name='corr2',
    description='Interfaces to MeerKAT CBF',
    long_description=open('README.md').read(),
    license='GPL',
    author='Tyrone van Balla',
    author_email='tvanballa at ska.ac.za',
    url='https://github.com/ska-sa/corr2',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Topic :: Scientific/Engineering :: Astronomy',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    install_requires=_install_requires,
    provides=['corr2'],
    packages=['corr2'],
    package_dir={'corr2': 'src'},
    scripts=glob('scripts/*'),
    setup_requires=['katversion'],
    use_katversion=True,
    entry_points={
        "metadata": [
            "foo_bar = setuptools.dist:assert_string_list",
        ],
    },
)

# end
