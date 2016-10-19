from data_stream import DataStream, DIGITISER_ADC_SAMPLES


class DigitiserStream(DataStream):
    """
    A DataStream from a Digitiser.
    """
    def __init__(self, name, input_number, destination):
        self.input_number = input_number
        super(DigitiserStream, self).__init__(
            name, DIGITISER_ADC_SAMPLES, destination)

    def __str__(self):
        return 'DigitiserStream(%s:%i:%i), data(%s)' % (
            self.name, self.input_number, self.category, self.destination)

# end
