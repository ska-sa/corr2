from logging import INFO
from casperfpga import utils as fpgautils

import fxcorrelator_speadops as speadops
from data_stream import SPEADStream, BEAMFORMER_FREQUENCY_DOMAIN
from utils import parse_output_products
# from corr2LogHandlers import getLogger
import delay as delayops

THREADED_FPGA_OP = fpgautils.threaded_fpga_operation
THREADED_FPGA_FUNC = fpgautils.threaded_fpga_function


class Beam(SPEADStream):
    def __init__(self, name, index, destination, max_pkt_size, *args, **kwargs):
        """
        A frequency-domain tied-array beam
        :param name - a string for the beam name
        :param index - the numerical beam index on the bhosts
        :param destination - where should the beam data go?
        :return:
        """
        self.index = index
        self.hosts = []
        self.xeng_acc_len = None
        self.chans_total = None
        self.beng_per_host = None
        self.chans_per_partition = None
        self.speadops = None
        self.polarisation = None
        self.last_delays = None 

        # This will always be a kwarg
        self.getLogger = kwargs['getLogger']
        # Why is logging defaulted to INFO, what if I do not want to see the info logs?
        logLevel = kwargs.get('logLevel', INFO)

        result, self.logger = self.getLogger(logger_name=name,
                                        log_level=logLevel, **kwargs)
        if not result:
            # Problem
            errmsg = 'Unable to create logger for {}'.format(logger_name)
            raise ValueError(errmsg)

        super(Beam, self).__init__(name, BEAMFORMER_FREQUENCY_DOMAIN,
                                   destination, max_pkt_size=max_pkt_size,
                                   **kwargs)

        self.logger.info('created okay')

    @classmethod
    def from_config(cls, beam_key, bhosts, config, fengops, speadops,
                    max_pkt_size, *args, **kwargs):
        """

        :param beam_key:
        :param bhosts:
        :param config:
        :param fengops:
        :param speadops:
        :return:
        """
        # number of b-engines in the system
        num_beng = int(config['xengine']['x_per_fpga']) * len(bhosts)

        # look for the section matching the name
        beam_dict = config[beam_key]

        beam_product, beam_stream_address = parse_output_products(beam_dict)
        assert len(beam_product) == 1, 'Currently only single beam products ' \
                                       'supported.'
        beam_name = beam_product[0]
        beam_address = beam_stream_address[0]
        if beam_address.ip_range != 1:
            raise RuntimeError(
                'The beam\'s given address range (%s) must be one, a starting'
                'base address.' % beam_address)
        beam_address.ip_range = num_beng

        obj = cls(beam_name, int(beam_dict['stream_index']), beam_address,
                  max_pkt_size=max_pkt_size,
                  instrument_descriptor=fengops.corr.descriptor,
                  *args, **kwargs)
        obj.config = beam_dict
        obj.hosts = bhosts
        obj.speadops = speadops

        obj.polarisation = obj.index%2
        n_ants=int(config['FxCorrelator']['n_ants'])
        obj.source_indices = range(obj.polarisation,(n_ants*2)+(obj.polarisation),2)
        obj.outbits = int(beam_dict['beng_outbits'])
        obj.xeng_acc_len = int(config['xengine']['xeng_accumulation_len'])
        obj.chans_total = int(config['fengine']['n_chans'])
        obj.beng_per_host = int(config['xengine']['x_per_fpga'])
        chans_per_host = obj.chans_total / len(obj.hosts)
        obj.chans_per_partition = chans_per_host / obj.beng_per_host
        obj.set_source(fengops.data_stream.destination)
        obj.descriptors_setup()
        return obj

    def __str__(self):
        return 'Beam %i:%s -> %s' % (self.index, self.name, self.destination)

    def initialise(self):
        """
        Set up the beam for first operation after programming.
        Anything that needs to be done EVERY TIME a new correlator is
        instantiated should go in self.configure
        :return:
        """
        self.tx_disable()
        # set the beam destination registers
        self.write_destination()

        self.logger.info('initialised okay')

    def configure(self):
        """
        Does nothing at the moment!
        :return:
        """
        return

    def tx_enable(self):
        """
        Start transmission of data streams from the b-engines
        :return:
        """
        self.descriptors_issue()
        THREADED_FPGA_FUNC(self.hosts, 5, ('tx_enable',
                                           [self.index], {}))
        self.tx_enabled = True
        self.logger.info('output enabled.')

    def tx_disable(self):
        """
        Stop transmission of data streams from the b-engines
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, 5, ('tx_disable',
                                           [self.index], {}))
        self.tx_enabled = False
        self.logger.info('output disabled.')

    def descriptors_setup(self):
        """
        Set up the data descriptors for this B-engine stream.
        :return:
        """
        if not self.xeng_acc_len:
            # wait until it's been set up
            return
        speadops.item_0x1600(self.descr_ig)
        # id is 0x5 + 12 least sig bits id of each beam
        beam_data_id = 0x5000
        speadops.add_item(
            self.descr_ig,
            name='bf_raw', id=beam_data_id,
            description='Channelised complex data. Real comes before imaginary.'
                        'A number of consecutive samples from each channel are '
                        'in the same packet. The heap offset and frequency '
                        'SPEAD items can be used to calculate the exact '
                        'frequency in relation to the spectrum',
            #dtype=numpy.int8,
            format=[('i', self.outbits)],
            shape=[self.chans_per_partition, self.xeng_acc_len, 2])

        speadops.add_item(
            self.descr_ig, name='frequency', id=0x4103,
            description=
            'Identifies the first channel in the band of frequency channels '
            'in the SPEAD heap',
            shape=[], format=[('u', speadops.SPEAD_ADDRSIZE)])

    def write_destination(self):
        """
        Write the destination to the hardware.
        :return:
        """
        THREADED_FPGA_FUNC(self.hosts, 5, ('beam_destination_set', [self], {}))
        self.logger.info('destination set to %s.' % (self.destination))

#    @property
#    def source_names(self):
#        tmp = [source.name for source in self.source_streams.keys()]
#        tmp.sort()
#        return tmp
#        return self.
