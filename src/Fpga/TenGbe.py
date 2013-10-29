'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
logger = logging.getLogger(__name__)

from Misc import log_runtime_error

def mac2str(mac):
    mac_pieces = []
    mac_pieces.append(mac & ((1<<48)-(1<<40))) >> 40
    mac_pieces.append(mac & ((1<<40)-(1<<32))) >> 32
    mac_pieces.append(mac & ((1<<32)-(1<<24))) >> 24
    mac_pieces.append(mac & ((1<<24)-(1<<16))) >> 16
    mac_pieces.append(mac & ((1<<16)-(1<<8))) >> 8
    mac_pieces.append(mac & ((1<<8)-(1<<0))) >> 0
    return "%02X:%02X:%02X:%02X:%02X:%02X" % (mac_pieces[0],mac_pieces[1],mac_pieces[2],mac_pieces[3],mac_pieces[4],mac_pieces[5])

def ip2str(ip):
    ip_pieces = []
    ip_pieces.append(ip/(2**24))
    ip_pieces.append(ip%(2**24))/(2**16)
    ip_pieces.append(ip%(2**16))/(2**8)
    ip_pieces.append(ip%(2**8))
    return "%i.%i.%i.%i" % (ip_pieces[0],ip_pieces[1],ip_pieces[2],ip_pieces[3])

class TenGbe(object):
    '''To do with the CASPER ten GBE yellow block implemented on FPGAs.
    '''
    def __init__(self, parent, name, **kwargs):
        '''
        @param dev_name string: Name of the core.
        '''
        self.parent = parent
        self.name = name
        self._device = None
        self.core_details = None
        self.options = {}

    def update_info(self, info):
        '''Set this memory's extra information.
        '''
        self.options = info

    def tap_start(self, tap_dev, device, mac, ip, port):
        """Program a 10GbE device and start the TAP driver.

            @param self  This object.
            @param device  String: name of the device (as in simulink name).
            @param tap_dev  String: name of the tap device (a Linux identifier). If you want to destroy a device later, you need to use this name.
            @param mac   integer: MAC address, 48 bits.
            @param ip    integer: IP address, 32 bits.
            @param port  integer: port of fabric interface (16 bits).

            Please note that the function definition changed from corr-0.4.0 to corr-0.4.1 to include the tap_dev identifier.
           """
        if len(tap_dev) > 8:
            log_runtime_error(logger, "Tap device identifier must be shorter than 9 characters. You specified %s for device %s." % (tap_dev, device))
        mac_str = mac2str(mac)
        ip_str = ip2str(ip)
        port_str = "%i" % port
        logger.info("Starting tgtap driver instance for %s: %s %s %s %s %s" % ("tap-start", tap_dev, device, ip_str, port_str, mac_str))
        reply, informs = self.parent._request("tap-start", -1, tap_dev, device, ip_str, port_str, mac_str)
        if reply.arguments[0] != 'ok':
            log_runtime_error(logger, "Failure starting tap device %s with mac %s, %s:%s" % (device, mac_str, ip_str, port_str))
        self._device = device

    def tap_stop(self, device):
        """Stop a TAP driver.

           @param self  This object.
           @param device  String: name of the device you want to stop.
        """
        if device != self._device:
            logger.warning('Stopping tap device %s, but set to %s?' % (device, self._device))
        reply, informs = self.parent._request("tap-stop", -1, device)
        if reply.arguments[0] != 'ok':
            log_runtime_error(logger, "Failure stopping tap device %s." % device)

    def get_10gbe_core_details(self, arp=False, cpu=False):
        """Prints 10GbE core details. 
        """
        '''
        assemble struct for header stuff...
        0x00 - 0x07: MAC address
        0x08 - 0x0b: Not used
        0x0c - 0x0f: Gateway addr
        0x10 - 0x13: IP addr
        0x14 - 0x17: Not assigned
        0x18 - 0x1b: Buffer sizes
        0x1c - 0x1f: Not assigned
        0x20    :    Soft reset (bit 0)
        0x21    :    Fabric enable (bit 0)
        0x22 - 0x23: Fabric port 
        0x24 - 0x27: XAUI status (bit 2,3,4,5 = lane sync, bit6 = chan_bond)
        0x28 - 0x2b: PHY config
        0x28    :    RX_eq_mix
        0x29    :    RX_eq_pol
        0x2a    :    TX_preemph
        0x2b    :    TX_diff_ctrl
        0x1000  :    CPU TX buffer
        0x2000  :    CPU RX buffer
        0x3000  :    ARP tables start
        '''
        rv = {}
        from struct import unpack
        port_dump = list(unpack('>16384B', self.parent.read(self.dev_name, 16384)))
        rv['ip_prefix'] = '%3d.%3d.%3d.' % (port_dump[0x10], port_dump[0x11], port_dump[0x12])
        rv['ip'] = [port_dump[0x10], port_dump[0x11], port_dump[0x12], port_dump[0x13]]
        rv['mac'] = [port_dump[0x02], port_dump[0x03], port_dump[0x04], port_dump[0x05], port_dump[0x06], port_dump[0x07]]
        rv['gateway_ip'] = [port_dump[0x0c], port_dump[0x0d], port_dump[0x0e], port_dump[0x0f]]
        rv['fabric_port'] = ((port_dump[0x22]<<8) + (port_dump[0x23]))
        rv['fabric_en'] = bool(port_dump[0x21]&1)
        rv['xaui_lane_sync'] = [bool(port_dump[0x27]&4), bool(port_dump[0x27]&8), bool(port_dump[0x27]&16), bool(port_dump[0x27]&32)]
        rv['xaui_status'] = [port_dump[0x24], port_dump[0x25], port_dump[0x26], port_dump[0x27]]
        rv['xaui_chan_bond'] = bool(port_dump[0x27]&64)
        rv['xaui_phy'] = {}
        rv['xaui_phy']['rx_eq_mix'] = port_dump[0x28]
        rv['xaui_phy']['rx_eq_pol'] = port_dump[0x29]
        rv['xaui_phy']['tx_preemph'] = port_dump[0x2a]
        rv['xaui_phy']['tx_swing'] = port_dump[0x2b]
        if arp:
            rv['arp'] = []
            for i in range(256):
                mac = []
                for m in range(2,8): mac.append(port_dump[0x3000+i*8+m])
                rv['arp'].append(mac)
        if cpu:
            rv['cpu_tx'] = {}
            for i in range(4096/8):
                tmp = []
                for j in range(8): tmp.append(port_dump[4096+8*i+j])
                rv['cpu_tx'][i*8] = tmp
            rv['cpu_rx_buf_unack_data'] = port_dump[6*4+3]
            rv['cpu_rx'] = {}
            for i in range(port_dump[6*4+3]+8):
                tmp = []
                for j in range(8): tmp.append(port_dump[8192+8*i+j])
                rv['cpu_rx'][i*8] = tmp
        self.core_details = rv
        return rv

    def print_10gbe_core_details(self, arp=False, cpu=False, refresh=True):
        """Prints 10GbE core details. 
          @param arp boolean: Include the ARP table
          @param cpu boolean: Include the CPU packet buffers
        """
        if refresh or (self.core_details == None):
            self.get_10gbe_core_details(arp, cpu)
        print '------------------------'
        print '%s configuration...', self.dev_name
        print 'My MAC: ',
        for j in self.core_details['mac']: print '%02X' % j,
        print ''
        print 'Gateway: ',
        for j in self.core_details['gateway_ip']: print '%3d' % j,
        print ''
        print 'This IP: ',
        for j in self.core_details['ip']: print '%3d' % j,
        print ''
        print 'Fabric Port: ',
        print '%5d' % self.core_details['fabric_port'],
        print 'Fabric interface is currently:', 'Enabled' if self.core_details['fabric_en'] else 'Disabled' 
        print 'XAUI Status: ',
        for j in self.core_details['xaui_status']: print '%02X' % j,
        print ''
        for i in range(0, 4): print '\tlane sync %i:  %i' % (i, self.core_details['xaui_lane_sync'][i])
        print '\tChannel bond: %i' % self.core_details['xaui_chan_bond']
        print 'XAUI PHY config: '
        print '\tRX_eq_mix: %2X' % self.core_details['xaui_phy']['rx_eq_mix']
        print '\tRX_eq_pol: %2X' % self.core_details['xaui_phy']['rx_eq_pol']
        print '\tTX_pre-emph: %2X' % self.core_details['xaui_phy']['tx_preemph']
        print '\tTX_diff_ctrl: %2X' % self.core_details['xaui_phy']['tx_swing']
        if arp:
            print 'ARP Table: '
            for i in range(256):
                print 'IP: %s%3d: MAC:' % (self.core_details['ip_prefix'], i),
                for m in range(0, 6): print '%02X' % self.core_details['arp'][i][m],
                print ''
        if cpu:
            print 'CPU TX Interface (at offset 4096 bytes):'
            print 'Byte offset: Contents (Hex)'
            for k, v in self.core_details['cpu_tx'].iteritems():
                print '%04i:    ' % k,
                for j in v: print '%02x' % j,
                print ''
            print '------------------------'
        
            print 'CPU RX Interface (at offset 8192bytes):'
            print 'CPU packet RX buffer unacknowledged data: %i' % self.core_details['cpu_rx_buf_unack_data']
            print 'Byte offset: Contents (Hex)'
            for k, v in self.core_details['cpu_rx'].iteritems():
                print '%04i:    ' % k,
                for j in v: print '%02x' % j,
                print ''
            print '------------------------'

# end