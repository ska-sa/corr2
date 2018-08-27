from glob import glob
from pip import _internal as pip
from setuptools import setup
from subprocess import check_output

try:
    branch = check_output(['git', 'symbolic-ref', '--short', 'HEAD'])
    assert not (branch == 'HEAD')
    branch = 'devel'
except Exception:
    branch = 'master'

_dependencies = 'https://github.com/ska-sa/casperfpga/archive/{branch}.zip#egg=casperfpga'.format(
    **locals())
_install_requires = [
    'casperfpga',
    'h5py',
    'iniparse',
    'katcp>=0.6.2',
    'matplotlib==2.0.2',
    'numpy',
    'spead2',
    'tornado>=4.3']

try:
    pip.main(['install', _dependencies])
except Exception:
    pass

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
    install_requires=_install_requires,
    dependency_links=[_dependencies],
    provides=['corr2'],
    packages=['corr2'],
    package_dir={'corr2': 'src'},
    scripts=glob('scripts/*'),
    setup_requires=['katversion'],
    use_katversion=True,
)

# end
