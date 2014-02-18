# pylint: disable-msg=C0103
# pylint: disable-msg=C0301

'''
Created on Feb 28, 2013

@author: paulp
'''

import logging
logger = logging.getLogger(__name__)

from Misc import log_runtime_error

class Mac(object):
    '''A MAC address.
    '''
    def __init__(self, mac):
        mac_str = None
        mac_int = None
        if isinstance(mac, Mac): mac_str = str(mac)
        elif isinstance(mac, str): mac_str = mac
        elif isinstance(mac, int): mac_int = mac
        if (mac_str==None) and (mac_int==None):
            log_runtime_error(logger, 'Cannot make a MAC with no value.')
        elif mac_str != None:
            self.mac_str = mac_str
            self.mac = str2mac(mac_str)
        elif mac_int != None:
            self.mac = mac_int
            self.mac_str = mac2str(mac_int)
    def __str__(self):
        return self.mac_str

class IpAddress(object):
    '''An IP address.
    '''
    def __init__(self, ip):
        ip_str = None
        ip_int = None
        if isinstance(ip, IpAddress): ip_str = str(ip)
        elif isinstance(ip, str): ip_str = ip
        elif isinstance(ip, int): ip_int = ip
        if (ip_str==None) and (ip_int==None):
            log_runtime_error(logger, 'Cannot make an IP with no value.')
        elif ip_str != None:
            self.ip_str = ip_str
            self.ip_int = str2ip(ip_str)
        elif ip_int != None:
            self.ip_int = ip_int
            self.ip_str = ip2str(ip_int)
    def __str__(self):
        return self.ip_str

def mac2str(mac):
    '''Convert a MAC in integer form to a HR string.
    '''
    mac_pieces = []
    mac_pieces.append((mac & ((1<<48)-(1<<40))) >> 40)
    mac_pieces.append((mac & ((1<<40)-(1<<32))) >> 32)
    mac_pieces.append((mac & ((1<<32)-(1<<24))) >> 24)
    mac_pieces.append((mac & ((1<<24)-(1<<16))) >> 16)
    mac_pieces.append((mac & ((1<<16)-(1<<8))) >> 8)
    mac_pieces.append((mac & ((1<<8)-(1<<0))) >> 0)
    return "%02X:%02X:%02X:%02X:%02X:%02X" % (mac_pieces[0], mac_pieces[1],
                                              mac_pieces[2], mac_pieces[3],
                                              mac_pieces[4], mac_pieces[5])
def str2mac(mac_str):
    '''Convert an HR MAC string to an integer.
    '''
    mac = 0
    if mac_str.count(':') != 5:
        raise RuntimeError('A MAC address must be of the form xx:xx:xx:xx:xx:xx')
    offset = 40
    for byte_str in mac_str.split(':'):
        value = int(byte_str, base=16)
        mac = mac + (value << offset)
        offset = offset - 8
    return mac

def ip2str(ip_addr):
    '''Convert an IP in integer form to a HR string.
    '''
    ip_pieces = []
    ip_pieces.append(ip_addr / (2**24))
    ip_pieces.append(ip_addr % (2**24)/(2**16))
    ip_pieces.append(ip_addr % (2**16)/(2**8))
    ip_pieces.append(ip_addr % (2**8))
    return "%i.%i.%i.%i" % (ip_pieces[0], ip_pieces[1],
                            ip_pieces[2], ip_pieces[3])
def str2ip(ip_str):
    '''Convert an HR IP string to an integer.
    '''
    ip_addr = 0
    if ip_str.count('.') != 3:
        raise RuntimeError('An IP address must be of the form xxx.xxx.xxx.xxx')
    offset = 24
    for octet in ip_str.split('.'):
        value = int(octet)
        ip_addr = ip_addr + (value << offset)
        offset = offset - 8
    return ip_addr

class TenGbe(object):
    '''To do with the CASPER ten GBE yellow block implemented on FPGAs,
    and interfaced-to via KATCP memory reads/writes.
    '''
    def __init__(self, parent, name, mac, ip_address, port):
        '''
        @param parent object: The KATCP client device that owns this ten gbe
        interface.
        @param name string: Name of the tengbe device in Simulink.
        @param mac string: A xx:xx:xx:xx:xx string representation of the MAC
        address for this interface.
        @param ip_address string: a xxx.xxx.xxx.xxx string representation of
        the IP address for this interface.
        @param port integer: the port this interface should use.
        '''
        # TODO: tengbe is just a Memory device, as is anything with which we interact via katcp
        self.parent = parent
        self.name = name
        self.setup(mac, ip_address, port)
        self.core_details = None
        self._check()

    def setup(self, mac, ip, port):
        self.mac = Mac(mac)
        self.ip_address = IpAddress(ip)
        self.port = port

    def _check(self):
        '''Does this device exist on the parent?
        '''
        try:
            self.parent.read(self.name, 1)
        except Exception:
            log_runtime_error(logger, 'Cannot connect to 10Gbe interface \'%s\'' % self.name)

    def __str__(self):
        '''String representation of this 10Gbe interface.
        '''
        return '%s: MAC(%s) IP(%s) Port(%s)' % (self.name, str(self.mac), str(self.ip_address), str(self.port))

    def tap_start(self, restart=False):
        '''Program a 10GbE device and start the TAP driver.
        @param self  This object.
        '''
        if len(self.name) > 8:
            log_runtime_error(logger, "Tap device identifier must be shorter than 9 characters. You specified %s for device %s." % (self.name, self.name))
        if restart:
            self.tap_stop()
        if self.tap_running():
            logger.info("Tap already running on %s." % str(self))
            return
        logger.info("Starting tap driver instance for %s." % str(self))
        reply, informs = self.parent._request("tap-start", -1, self.name, self.name, str(self.ip_address), str(self.port), str(self.mac))
        if reply.arguments[0] != 'ok':
            log_runtime_error(logger, "Failure starting tap driver instance for %s." % str(self))

    def tap_stop(self):
        '''Stop a TAP driver.
        @param self  This object.
        @param device  String: name of the device you want to stop.
        '''
        if self.tap_running() == False:
            return
        logger.info("Stopping tap driver instance for %s." % str(self))
        reply, informs = self.parent._request("tap-stop", -1, self.name)
        if reply.arguments[0] != 'ok':
            log_runtime_error(logger, "Failure stopping tap device for %s." % str(self))

    def tap_info(self):
        '''Get info on the tap instance running on this interface.
        @param self  This object.
        '''
        uninforms = []
        def handle_inform(msg):
            uninforms.append(msg)
        self.parent.unhandled_inform_handler = handle_inform
        reply, informs = self.parent._request("tap-info", -1, self.name)
        self.parent.unhandled_inform_handler = None
        if reply.arguments[0] != 'ok':
            log_runtime_error(logger, "Failure getting tap info for device %s." % str(self))
        return uninforms

    def tap_running(self):
        '''Determine if an instance if tap is already running on for this Ten GBE interface.
        @param self  This object.
        '''
        uninforms = self.tap_info()
        if len(uninforms) == 0:
            return False
        return True

#==============================================================================
# NOT NEEDED
#     def multicast_send(self, ip_str):
#         reply, informs = self.parent._request("tap-multicast-add", self.parent._timeout, self.name, 'send', str2ip(ip_str))
#         if reply.arguments[0] == 'ok':
#             return
#         else:
#             raise RuntimeError("Failed adding multicast destination address %s to tap device %s" % (str2ip(ip_str)))
#==============================================================================

    def multicast_receive(self, ip_str, group_size):
        '''Send a request to KATCP to have this tap instance send a multicast group join request.
        @param self  This object.
        @param ip_str  A dotted decimal string representation of the base mcast IP address.
        @param group_size  An integer for how many mcast addresses from base to respond to.
        '''
        #mask = 255*(2**24) + 255*(2**16) + 255*(2**8) + (255-group_size)
        #self.parent.write_int(self.name, str2ip(ip_str), offset = 12)
        #self.parent.write_int(self.name, mask, offset = 13)
        mcast_group_string = ip_str + '+' + str(group_size)
        print 'mcast_group:', mcast_group_string
        reply, informs = self.parent._request("tap-multicast-add", self.parent._timeout, self.name, 'recv', mcast_group_string)
        if reply.arguments[0] == 'ok':
            return
        else:
            raise RuntimeError("Failed adding multicast receive %s to tap device %s" % (mcast_group_string, self.name))

    def multicast_remove(self, ip_str):
        '''Send a request to be removed from a multicast group.
        @param self  This object.
        @param ip_str  A dotted decimal string representation of the base mcast IP address.
        '''
        reply, informs = self.parent._request("tap-multicast-remove", self.parent._timeout, self.name, str2ip(ip_str))
        if reply.arguments[0] == 'ok':
            return
        else:
            raise RuntimeError("Failed removing multicast address %s to tap device %s" % (str2ip(ip_str)))

    def get_10gbe_core_details(self, read_arp=False, read_cpu=False):
        '''Prints 10GbE core details.
        '''
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
        returnval = {}
        import struct
        port_dump = list(struct.unpack('>16384B', self.parent.read(self.name, 16384)))
        returnval['ip_prefix'] = '%3d.%3d.%3d.' % (port_dump[0x10], port_dump[0x11], port_dump[0x12])
        returnval['ip'] = [port_dump[0x10], port_dump[0x11], port_dump[0x12], port_dump[0x13]]
        returnval['mac'] = [port_dump[0x02], port_dump[0x03], port_dump[0x04], port_dump[0x05], port_dump[0x06], port_dump[0x07]]
        returnval['gateway_ip'] = [port_dump[0x0c], port_dump[0x0d], port_dump[0x0e], port_dump[0x0f]]
        returnval['fabric_port'] = ((port_dump[0x22]<<8) + (port_dump[0x23]))
        returnval['fabric_en'] = bool(port_dump[0x21]&1)
        returnval['xaui_lane_sync'] = [bool(port_dump[0x27]&4), bool(port_dump[0x27]&8), bool(port_dump[0x27]&16), bool(port_dump[0x27]&32)]
        returnval['xaui_status'] = [port_dump[0x24], port_dump[0x25], port_dump[0x26], port_dump[0x27]]
        returnval['xaui_chan_bond'] = bool(port_dump[0x27]&64)
        returnval['xaui_phy'] = {}
        returnval['xaui_phy']['rx_eq_mix'] = port_dump[0x28]
        returnval['xaui_phy']['rx_eq_pol'] = port_dump[0x29]
        returnval['xaui_phy']['tx_preemph'] = port_dump[0x2a]
        returnval['xaui_phy']['tx_swing'] = port_dump[0x2b]
        if read_arp:
            returnval['arp'] = self.get_arp_details(port_dump)
        if read_cpu:
            returnval.update(self.get_cpu_details(port_dump))
        self.core_details = returnval
        return returnval

    def get_arp_details(self, port_dump=None):
        '''Get ARP details from this interface.
        @param port_dump list: A list of raw bytes from interface memory.
        '''
        if port_dump == None:
            import struct
            port_dump = list(struct.unpack('>16384B', self.parent.read(self.name, 16384)))
        returnval = []
        for addr in range(256):
            mac = []
            for ctr in range(2, 8):
                mac.append(port_dump[0x3000+(addr*8)+ctr])
            returnval.append(mac)
        return returnval

    def get_cpu_details(self, port_dump):
        if port_dump == None:
            import struct
            port_dump = list(struct.unpack('>16384B', self.parent.read(self.name, 16384)))
        returnval = {}
        returnval['cpu_tx'] = {}
        for ctr in range(4096/8):
            tmp = []
            for j in range(8):
                tmp.append(port_dump[4096+(8*ctr)+j])
            returnval['cpu_tx'][ctr*8] = tmp
        returnval['cpu_rx_buf_unack_data'] = port_dump[6*4+3]
        returnval['cpu_rx'] = {}
        for ctr in range(port_dump[6*4+3]+8):
            tmp = []
            for j in range(8):
                tmp.append(port_dump[8192+(8*ctr)+j])
            returnval['cpu_rx'][ctr*8] = tmp
        return returnval

    def print_10gbe_core_details(self, arp=False, cpu=False, refresh=True):
        '''Prints 10GbE core details.
        @param arp boolean: Include the ARP table
        @param cpu boolean: Include the CPU packet buffers
        '''
        if refresh or (self.core_details == None):
            self.get_10gbe_core_details(arp, cpu)
        print '------------------------'
        print '%s configuration:' % self.name
        print 'MAC: ',
        for mac in self.core_details['mac']:
            print '%02X' % mac,
        print ''
        print 'Gateway: ',
        for gw_ip in self.core_details['gateway_ip']:
            print '%3d' % gw_ip,
        print ''
        print 'IP: ',
        for ip_addr in self.core_details['ip']:
            print '%3d' % ip_addr,
        print ''
        print 'Fabric port: ',
        print '%5d' % self.core_details['fabric_port']
        print 'Fabric interface is currently:', 'Enabled' if self.core_details['fabric_en'] else 'Disabled'
        print 'XAUI Status: ',
        for xaui_status in self.core_details['xaui_status']:
            print '%02X' % xaui_status,
        print ''
        for i in range(0, 4):
            print '\tlane sync %i:  %i' % (i, self.core_details['xaui_lane_sync'][i])
        print '\tChannel bond: %i' % self.core_details['xaui_chan_bond']
        print 'XAUI PHY config: '
        print '\tRX_eq_mix: %2X' % self.core_details['xaui_phy']['rx_eq_mix']
        print '\tRX_eq_pol: %2X' % self.core_details['xaui_phy']['rx_eq_pol']
        print '\tTX_pre-emph: %2X' % self.core_details['xaui_phy']['tx_preemph']
        print '\tTX_diff_ctrl: %2X' % self.core_details['xaui_phy']['tx_swing']
        if arp:
            self.print_arp_details(refresh=refresh, only_hits=True)
        if cpu:
            self.print_cpu_details(refresh=refresh)

    def print_arp_details(self, refresh=False, only_hits=False):
        if refresh or (self.core_details == None):
            self.get_10gbe_core_details(read_arp=True)
        print 'ARP Table: '
        for ip_address in range(256):
            all_fs = True
            if only_hits:
                for mac in range(0, 6):
                    if self.core_details['arp'][ip_address][mac] != 255:
                        all_fs = False
                        break
            printmac = True
            if only_hits and all_fs:
                printmac = False
            if printmac:
                print 'IP: %s%3d: MAC:' % (self.core_details['ip_prefix'], ip_address),
                for mac in range(0, 6):
                    print '%02X' % self.core_details['arp'][ip_address][mac],
                print ''

    def print_cpu_details(self, refresh=False):
        if refresh or (self.core_details == None):
            self.get_10gbe_core_details(read_cpu=True)
        print 'CPU TX Interface (at offset 4096 bytes):'
        print 'Byte offset: Contents (Hex)'
        for key, value in self.core_details['cpu_tx'].iteritems():
            print '%04i:    ' % key,
            for val in value:
                print '%02x' % val,
            print ''
        print '------------------------'

        print 'CPU RX Interface (at offset 8192bytes):'
        print 'CPU packet RX buffer unacknowledged data: %i' % self.core_details['cpu_rx_buf_unack_data']
        print 'Byte offset: Contents (Hex)'
        for key, value in self.core_details['cpu_rx'].iteritems():
            print '%04i:    ' % key,
            for val in value:
                print '%02x' % val,
            print ''
        print '------------------------'

# end
