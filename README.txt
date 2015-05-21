CORR2

This package provides functions to control MeerKAT's packetised, FPGA-based correlator/beamformer (CBF). Analoguous to KAT-7's original corr package.

Installation:
Do the normal
    sudo python setup.py install

Usage:

Requires:
    - iniparse, numpy, matplotlib (if plotting outputs), katcp, PySPEAD, construct

Recommended:
    - katsdisp, the standalone KAT signal display package for visualising output.

ToDo:
    - Make it work!


Release Notes:
    - 2015-05-21: Needs DEng version r2_deng_tvg_2015_May_20_1353.fpg or later
      for dsimengine to work properly
