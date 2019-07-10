from glob import glob
from pip import _internal as pip
from setuptools import setup
from subprocess import check_output

#imports for determining the git hash and time of build
import time
import git

repo = git.Repo('./');
repo_state = "clean"
if(repo.is_dirty()):
	repo_state = "dirty"
git_hash = repo.head.object.hexsha.strip()
git_branch_name = repo.active_branch.name;

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

try:
    pip.main(['install', _dependencies])
except Exception:
    pass

setup(
    name='corr2',
    description='Interfaces to MeerKAT CBF',
    long_description=open('README.md').read(),
    license='GPL',
    author='Paul Prozeskyaa',
    author_email='paulp at ska.ac.za',
    version="{}-{}-{}-{}".format(time.strftime('%Y-%m-%d_%Hh%M'),git_branch_name,git_hash,repo_state),
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
    #use_katversion=True,
    entry_points={
        "metadata": [
            "foo_bar = setuptools.dist:assert_string_list",
        ],
    },
)

# end
