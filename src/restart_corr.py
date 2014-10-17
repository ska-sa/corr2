import fxcorrelator, logging
logging.basicConfig(level=logging.INFO)
c = fxcorrelator.FxCorrelator('rts correlator', config_source='/home/paulp/code/corr2.ska.github/src/fxcorr.ini')
c.initialise()

