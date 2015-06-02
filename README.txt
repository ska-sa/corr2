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
    - 2015-05-21: requires rootfs
      roach2-root-unknown-katonly-private-5911330-2015-05-19.romfs or newer for
      the IGMP protocol version setting to work. Roach file-system 'keep' file
      must be removed, or (after installing above romfs or newer), the
      ?reset-config request can be issued followed by a reboot.

    - 2015-05-29: Needs DEng version  r2_deng_tvg_2015_May_21_1535.fpg or later
      for dsimengine to work properly
