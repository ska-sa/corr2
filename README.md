# CORR2

[![Codacy Badge](https://api.codacy.com/project/badge/Grade/dc5e1d1d17024777a43aa2c47da03f02)](https://app.codacy.com/app/mmphego/corr2?utm_source=github.com&utm_medium=referral&utm_content=ska-sa/corr2&utm_campaign=Badge_Grade_Dashboard)

This package provides interfaces and functions to configure MeerKAT packetised digital backend; FX correlators, beamformers and other real-time instrumentation.

## Installation:
Do the normal
```bash 
$ sudo python setup.py install
```

### Usage

```python
import corr2
c = corr2.fxcorrelator.FxCorrelator('Corr', '/etc/corr/correlator_config.ini')
c.initialise()
```

## ToDo:
    - Make it work!

Release Notes:
- 2015-07-08: Updated for new DEng registers, requires a DEng build newer
      than around 2015-07-01 to work.
- 2015-05-21: requires rootfs
      roach2-root-unknown-katonly-private-5911330-2015-05-19.romfs or newer for
      the IGMP protocol version setting to work. Roach file-system 'keep' file
      must be removed, or (after installing above romfs or newer), the
      ?reset-config request can be issued followed by a reboot.
- 2015-05-29: Needs DEng version  r2_deng_tvg_2015_May_21_1535.fpg or later
      for dsimengine to work properly
- 2015-06-10ish - new_transport_check branch created that breaks interface
      with earlier f-engines
