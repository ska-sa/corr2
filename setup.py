import glob
from setuptools import setup

setup(
    name='corr2',
    description='Interfaces to MeerKAT CBF',
    long_description=open('README.md').read(),
    license='GPL',
    author='Paul Prozesky',
    author_email='paulp at ska.ac.za',
    url='https://github.com/ska-sa/corr2',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Topic :: Scientific/Engineering :: Astronomy',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    install_requires=[
        'casperfpga==3.1', 'katcp>=0.6.2', 'matplotlib==2.0.2', 'iniparse', 'numpy', 'spead2',
        'h5py', 'tornado>=4.3'],
    dependency_links=['git+https://github.com/ska-sa/casperfpga@master#egg=casperfpga==3.1'],
    provides=['corr2'],
    packages=['corr2'],
    package_dir={'corr2': 'src'},
    scripts=glob.glob('scripts/*'),
    setup_requires=['katversion'],
    use_katversion=True,
)

# end
