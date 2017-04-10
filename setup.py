from distutils.core import setup
import glob

setup(name='corr2',
      description='Interfaces to MeerKAT CBF',
      long_description='Provides interfaces and functions to '
                       'configure MeerKAT packetised digital backend; '
                       'FX correlators, beamformers and other realtime '
                       'instrumentation.',
      license='GPL',
      author='Paul Prozesky',
      author_email='paulp at ska.ac.za',
      url='http://pypi.python.org/pypi/corr2',
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Developers',
          'Operating System :: OS Independent',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Topic :: Scientific/Engineering :: Astronomy',
          'Topic :: Software Development :: Libraries :: Python Modules',
      ],
      install_requires=['casperfpga', 'katcp', 'matplotlib', 'iniparse',
                        'numpy', 'spead2', 'h5py'],
      provides=['corr2'],
      packages=['corr2'],
      package_dir={'corr2': 'src'},
      scripts=glob.glob('scripts/*'),
      setup_requires=['katversion'],
      use_katversion=True,
      )

# end
