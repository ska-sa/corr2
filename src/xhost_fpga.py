__author__ = 'paulp'

import time

from host_fpga import FpgaHost


class FpgaXHost(FpgaHost):
    """
    A Host, that hosts Xengines, that is a CASPER KATCP FPGA.
    """
    def __init__(self, host, katcp_port=7147, boffile=None, connect=True, config=None):
        FpgaHost.__init__(self, host, katcp_port=katcp_port, boffile=boffile, connect=connect)
        self.config = config
        if self.config is not None:
            self.vacc_len = int(self.config['xeng_accumulation_len'])
            self.x_per_fpga = int(self.config['x_per_fpga'])

        # TODO - and if there is no config and this was made on a running device? something like set it to -1, if it's accessed when -1 then try and discover it
        self.x_per_fpga = 4

    @classmethod
    def from_config_source(cls, hostname, katcp_port, config_source):
        boffile = config_source['bitstream']
        return cls(hostname, katcp_port=katcp_port, boffile=boffile, connect=True, config=config_source)

    def get_system_information(self, filename=None, fpg_info=None):
        """
        Overload the KatcpFpga function. We want more from the bof file.
        :param filename:
        :param fpg_info:
        :return:
        """
        FpgaHost.get_system_information(self, filename, fpg_info)

    def vacc_accumulations_per_second(self, xnum=-1):
        """
        Get the number of accumulatons per second.
        :param xnum: specify an xengine, by index number, otherwise read from all of them
        :return: the vaccs per second for the specified xengines on this host
        """
        def accspersec(_xengnum):
            tic = self.registers['vacccnt%d' % _xengnum].read()['data']['reg']
            time.sleep(1)
            toc = self.registers['vacccnt%d' % _xengnum].read()['data']['reg']
            return toc - tic
        """
        How many accumulations per second are happening on the x-engines?
        :param xnum:
        :return: a List of integers
        """
        if xnum > -1:
            return [accspersec(xnum)]
        else:
            rvs = []
            for xnum in range(0, self.x_per_fpga):
                rvs.append(accspersec(xnum))
            return rvs

    def vacc_okay(self, xnum=-1):
        """
        Are the vaccs, or one vacc, okay?
        :param xnum: a specific xengine's vacc
        :return: True or False
        """
        if xnum > -1:
            return self.registers['vaccerr%d' % xnum].read()['data']['reg'] == 0
        else:
            for xnum in range(0, self.x_per_fpga):
                if self.registers['vaccerr%d' % xnum].read()['data']['reg'] > 0:
                    return False
            return True

    def vacc_get_status(self):
        """
        Read the vacc status registers, error count, accumulation count and load status
        :return: tuple with errors, count, arm count and load count
        """
        stats = []
        for xnum in range(0, self.x_per_fpga):
            xengdata = {'errors': self.registers['vaccerr%d' % xnum].read()['data']['reg'],
                        'count': self.registers['vacccnt%d' % xnum].read()['data']['reg']}
            temp = self.registers['vacc_ld_status%i' % xnum].read()['data']
            if 'reg' in temp.keys():
                xengdata['armcount'] = temp['reg'] >> 16
                xengdata['loadcount'] = temp['reg'] & 0xffff
            else:
                xengdata['armcount'] = temp['armcnt']
                xengdata['loadcount'] = temp['ldcnt']
            stats.append(xengdata)
        return stats

    def vacc_get_error_detail(self):
        """
        Read the vacc error counter registers
        :return: dictionary with error counters
        """
        errors = []
        for xnum in range(0, self.x_per_fpga):
            temp = self.registers['vacc_errors%i' % xnum].read()['data']
            errors.append(temp)
        return errors

    def vacc_check_arm_load_counts(self):
        status = self.vacc_get_status()
        reset_required = False
        for xengctr, xengdata in enumerate(status):
            if xengdata['armcount'] != xengdata['loadcount']:
                # self.logger.warning('vacc on xengine %i needs resetting, '
                #                     'armcount(%i) loadcount(%i).' % (xengctr, xengdata['armcount'],
                #                                                      xengdata['loadcount']))
                reset_required = True
                break
        return reset_required

    def vacc_check_reset_status(self):
        status = self.vacc_get_status()
        reset_okay = True
        for xengctr, xengdata in enumerate(status):
            if (xengdata['armcount'] != 0) or (xengdata['loadcount'] != 0):
                # self.logger.warning('vacc on xengine %i failed to reset.' % xengctr)
                reset_okay = False
                break
        return reset_okay

    def vacc_reset(self):
        """
        Reset the vector accumulator
        :return:
        """
        self.registers.control.write(vacc_rst='pulse')

    def vacc_arm(self):
        """
        Arm the vaccs on this host
        :return:
        """
        self.registers.vacc_time_msw.write(arm='pulse')

    def vacc_set_loadtime(self, loadtime):
        """
        Set the vacc load time on this xengine board
        :param loadtime:
        :return:
        """
        ldtime_msw = loadtime >> 32
        ldtime_lsw = loadtime & 0xffffffff
        self.registers.vacc_time_lsw.write(lsw=ldtime_lsw)
        self.registers.vacc_time_msw.write(msw=ldtime_msw)

    def set_accumulation_length(self, accumulation_length, issue_meta=True):
        """ Set the accumulation time for the vector accumulator
        @param accumulation_length: the accumulation time in spectra.
        @param issue_meta: issue SPEAD meta data indicating the change in time
        @returns: the actual accumulation time in seconds
        """
        vacc_len = self.config['vacc_len']
        acc_len = self.config['acc_len']
        # figure out how many pre-accumulated spectra this is (rounding up)
        vacc_len = numpy.ceil(float(vacc_len)/float(acc_len))
        self.vacc_len.write(reg=vacc_len)

        return vacc_len*acc_len

    def get_accumulation_length(self):
        """ Get the current accumulation time of the vector accumulator
        @returns: the accumulation time in spectra
        """
        acc_len = self.config['acc_len']
        vacc_len = self.vacc_len.read()['data']['reg']
        return vacc_len * acc_len
