from data_stream import SPEADStream, DIGITISER_ADC_SAMPLES, StreamAddress


class DigitiserStream(SPEADStream):
    """
    A SPEADStream from a Digitiser.
    It has an input number associated with it.
    """
    def __init__(self, name, destination, input_number, correlator):
        self.input_number = input_number
        self.correlator = correlator
        super(DigitiserStream, self).__init__(
            name, DIGITISER_ADC_SAMPLES, destination)

    def __str__(self):
        return 'DigitiserStream(%s:%i:%i) -> %s' % (
            self.name, self.input_number, self.category, self.destination)

    def descriptors_setup(self):
        """
        Set up the data descriptors for an X-engine stream.
        :return:
        """
        return
        # spead_add_item(
        #     sig=self.descr_ig, stx=None,
        #     name='timestamp', id=0x1600,
        #     description='Timestamp of start of this integration. uint '
        #                 'counting multiples of ADC samples since last sync '
        #                 '(sync_time, id=0x1027). Divide this number by '
        #                 'timestamp_scale (id=0x1046) to get back to seconds '
        #                 'since last sync when this integration was actually '
        #                 'started.',
        #     shape=[], format=[('u', SPEAD_ADDRSIZE)])
        #
        # spead_add_item(
        #     sig=self.descr_ig, stx=None,
        #     name='digitiser_id', id=0x3101,
        #     description='3 numbers identifying the digitiser: ID, '
        #                 'frequency_band, receptor. The frequency_band has the '
        #                 'following four values defined for MeerKAT: 0 '
        #                 'L-Band Digitiser, 1 UHF-Band Digitiser, '
        #                 '2 X-Band Digitiser, 3 S-Band Digitiser, '
        #                 '4 - 255 Reserved.',
        #     shape=[], format=[('u', SPEAD_ADDRSIZE)])
        #
        # spead_add_item(
        #     sig=self.descr_ig, stx=None,
        #     name='digitiser_status', id=0x3102,
        #     description='Bitfield indicating the status of the digitiser. LSb '
        #                 '(bit0): noise_diode. bit1: adc_saturate. '
        #                 'Other bits reserved for future use.',
        #     shape=[], format=[('u', SPEAD_ADDRSIZE)])
        #
        # spead_add_item(
        #     sig=self.descr_ig, stx=None,
        #     name='raw_ant_data', id=0x3300,
        #     description='Raw 10-bit samples from the Meerkat ADC.',
        #     shape=(512,), dtype='i10')

    def set_destination(self, new_dest):
        """
        Set the destination on this digitiser stream.
        :param new_dest: The new destinaton to set on this device.
        :return:
        """
        if new_dest is None:
            self.correlator.logger.warning(
                '%s: stream destination not set' % self.name)
            return
        if not hasattr(new_dest, 'ip_address'):
            new_dest = StreamAddress.from_address_string(new_dest)
        self.destination = new_dest

    def tx_enable(self):
        """
        Enable TX for this data stream
        :return:
        """
        self.correlator.logger.info('{}: Digitiser streams cannot be '
                                    'started.'.format(self.name))

    def tx_disable(self):
        """
        Disable TX for this data stream
        :return:
        """
        self.correlator.logger.info('{}: Digitiser streams cannot be '
                                    'stopped.'.format(self.name))

# end
