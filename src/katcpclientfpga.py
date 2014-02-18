# pylint: disable-msg=C0301

'''
Created on Feb 28, 2013

@author: paulp
'''

import logging, katcp, struct
from fpga import Register, Sbram, Snap, KatAdc, TenGbe, Memory
import host, asyncrequester
from misc import log_runtime_error

logger = logging.getLogger(__name__)

# if __name__ == '__main__':
#     print 'Hello World'

class KatcpClientFpga(host.Host, asyncRequester.AsyncRequester, katcp.CallbackClient):
    '''
    A FPGA host board that has a KATCP server running on it.
    '''
    def __init__(self, host, ip, katcp_port = 7147, timeout = 5.0, connect = True):
        '''
        '''
        host.Host.__init__(self, host, ip, katcp_port)
        asyncRequester.AsyncRequester.__init__(self, self.callback_request, max_requests = 100)
        katcp.CallbackClient.__init__(self, host, katcp_port, tb_limit = 20, timeout = timeout, logger = logger, auto_reconnect = True)

        # device lists
        self.devices = {}
        self.dev_registers = []
        self.dev_snapshots = []
        self.dev_sbrams = []
        self.dev_tengbes = []
        self.dev_adcs = []

        self.system_info = {}

        self.system_name = None
        self.running_bof = ''
        self.bofname = ''

        self.unhandled_inform_handler = None

        # start katcp daemon
        self._timeout = timeout
        if connect:
            self.start(daemon = True)

        logger.info('%s:%s created%s.' % (host, katcp_port, ' & daemon started' if connect else ''))

    def unhandled_inform(self, msg):
        '''What do we do with unhandled KATCP inform messages that this device receives?
        '''
        if self.unhandled_inform_handler != None:
            self.unhandled_inform_handler(msg)

    def __getattribute__(self, name):
        if name == 'registers':
            return {self.devices[r].name:self.devices[r] for r in self.dev_registers}
        elif name == 'snapshots':
            return {self.devices[r].name:self.devices[r] for r in self.dev_snapshots}
        elif name == 'sbrams':
            return {self.devices[r].name:self.devices[r] for r in self.dev_sbrams}
        elif name == 'tengbes':
            return {self.devices[r].name:self.devices[r] for r in self.dev_tengbes}
        return object.__getattribute__(self, name)

    def connect(self):
        logger.info('%s: daemon started' % self.host)
        self.start(daemon = True)

    def disconnect(self):
        logger.info('%s: daemon stopped' % self.host)
        self.stop()

    def __str__(self):
        return 'KatcpFpga(%s)@%s:%i engines(%i) regs(%i) snaps(%i) sbrams(%i) adcs(%i) tengbes(%i) - %s' % (self.host, self.ip, self.katcp_port,
                                                                                                            len(self.engines), len(self.dev_registers), len(self.dev_snapshots),
                                                                                                            len(self.dev_sbrams), len(self.dev_adcs), len(self.dev_tengbes),
                                                                                                            'connected' if self.is_connected() else 'disconnected')

    def _request(self, name, request_timeout = -1, *args):
        """Make a blocking request and check the result.

           Raise an error if the reply indicates a request failure.

           @param self  This object.
           @param name  String: name of the request message to send.
           @param request_timeout  Int: number of seconds after which the request must time out
           @param args  List of strings: request arguments.
           @return  Tuple: containing the reply and a list of inform messages.
           """
        if request_timeout == -1:
            request_timeout = self._timeout
        request = katcp.Message.request(name, *args)
        reply, informs = self.blocking_request(request, timeout = request_timeout)
        if reply.arguments[0] != katcp.Message.OK:
            log_runtime_error(logger, "Request %s failed.\n\tRequest: %s\n\tReply: %s" % (request.name, request, reply))
        return reply, informs

    def listdev(self):
        """Return a list of register / device names.

           @param self  This object.
           @return  A list of register names.
           """
        reply, informs = self._request("listdev", self._timeout)
        return [i.arguments[0] for i in informs]

    def listbof(self):
        """Return a list of executable files.

           @param self  This object.
           @return  List of strings: list of executable files.
           """
        reply, informs = self._request("listbof", self._timeout)
        return [i.arguments[0] for i in informs]

    def listcmd(self):
        """Return a list of available commands. this should not be made
           available to the user, but can be used internally to query if a
           command is supported.

           @todo  Implement or remove.
           @param self  This object.
           """
        raise NotImplementedError("LISTCMD not implemented by client.")

    def deprogram(self):
        '''Deprogram the FPGA.
        '''
        reply, informs = self._request("progdev", self._timeout)
        if reply.arguments[0] == 'ok':
            self.running_bof = ''
        logger.info("Deprogramming FPGA %s... %s." % (self.host, reply.arguments[0]))

    def program(self, boffile = None):
        """Program the FPGA with the specified boffile.

           @param self  This object.
           @param boffile  String: name of the BOF file.
           @return  String: device status.
           """
        if boffile == None:
            boffile = self.bofname
        elif boffile != self.bofname:
            logger.warning('Programming BOF file %s, config BOF file %s' % (boffile, self.bofname))
        reply, informs = self._request("progdev", self._timeout, boffile)
        if reply.arguments[0] == 'ok':
            self.running_bof = boffile
        logger.info("Programming FPGA %s with %s... %s." % (self.host, boffile, reply.arguments[0]))
        return reply.arguments[0]

    def status(self):
        """Return the status of the FPGA.
           @param self  This object.
           @return  String: FPGA status.
           """
        reply, informs = self._request("status", self._timeout)
        return reply.arguments[1]

    def ping(self):
        """Tries to ping the FPGA.
           @param self  This object.
           @return  boolean: ping result.
           """
        reply, informs = self._request("watchdog", self._timeout)
        if reply.arguments[0] == 'ok':
            logger.info('katcp ping okay')
            return True
        else:
            logger.error('katcp connection failed')
            return False

    def read(self, device_name, size, offset = 0):
        """Return size_bytes of binary data with carriage-return
           escape-sequenced.

           @param self  This object.
           @param device_name  String: name of device / register to read from.
           @param size  Integer: amount of data to read (in bytes).
           @param offset  Integer: offset to read data from (in bytes).
           @return  Bindary string: data read.
           """
        reply, informs = self._request("read", self._timeout, device_name, str(offset), str(size))
        return reply.arguments[1]

    def bulkread(self, device_name, size, offset = 0):
        """Return size_bytes of binary data with carriage-return escape-sequenced.
           Uses much fast bulkread katcp command which returns data in pages
           using informs rather than one read reply, which has significant buffering
           overhead on the ROACH.

           @param self  This object.
           @param device_name  String: name of device / register to read from.
           @param size  Integer: amount of data to read (in bytes).
           @param offset  Integer: offset to read data from (in bytes).
           @return  Bindary string: data read.
           """
        reply, informs = self._request("bulkread", self._timeout, device_name, str(offset), str(size))
        return ''.join([i.arguments[0] for i in informs])

    def upload_bof(self, bof_file, port, force_upload = False, timeout = 30):
        """Upload a BORPH file to the ROACH board for execution.
           @param self  This object.
           @param bof_file  The path and/or filename of the bof file to upload.
           @param port  The port to use for uploading.
           @param force_upload  Force the upload even if the bof file is already on the filesystem.
           @param timeout  The timeout to use for uploading.
           @return
        """
        # does the bof file exist?
        import os
        try:
            os.path.getsize(bof_file)
            filename = bof_file.split("/")[-1]
        except:
            raise IOError('BOF file not found.')
        # is it on the FPGA already?
        if not force_upload:
            bofs = self.listbof()
            if bofs.count(filename) == 1:
                return
        import time, threading, socket, Queue
        def makerequest(result_queue):
            try:
                result = self._request('upload', timeout, port, filename)
                if(result[0].arguments[0] == katcp.Message.OK):
                    result_queue.put('')
                else:
                    result_queue.put('Request to client returned, but not Message.OK.')
            except Exception:
                result_queue.put('Request to client failed.')
        def uploadbof(filename, result_queue):
            upload_socket = socket.socket()
            stime = time.time()
            connected = False
            while (not connected) and (time.time() - stime < 2):
                try:
                    upload_socket.connect((self.host, port))
                    connected = True
                except Exception:
                    time.sleep(0.1)
            if not connected:
                result_queue.put('Could not connect to upload port.')
            try:
                upload_socket.send(open(filename).read())
            except Exception:
                result_queue.put('Could not send file to upload port.')
            result_queue.put('')
        # request thread
        request_queue = Queue.Queue()
        request_thread = threading.Thread(target = makerequest, args = (request_queue, ))
        # upload thread
        upload_queue = Queue.Queue()
        upload_thread = threading.Thread(target = uploadbof, args = (bof_file, upload_queue, ))
        # start the threads and join
        old_timeout = self._timeout
        self._timeout = timeout
        request_thread.start()
        upload_thread.start()
        request_thread.join()
        self._timeout = old_timeout
        request_result = request_queue.get()
        upload_result = upload_queue.get()
        if (request_result != '') or (upload_result != ''):
            raise Exception('Error: request(%s), upload(%s)' %(request_result, upload_result))
        #self._logger.info("Bof file upload for '", bof_file, "': request (", request_result, "), uploaded (", upload_result, ")")
        return

    def read_dram(self, size, offset = 0, verbose = False):
        """Reads data from a ROACH's DRAM. Reads are done up to 1MB at a time.
           The 64MB indirect address register is automatically incremented as necessary.
           It returns a string, as per the normal 'read' function.
           ROACH has a fixed device name for the DRAM (dram memory).
           Uses bulkread internally.

           @param self    This object.
           @param size    Integer: amount of data to read (in bytes).
           @param offset  Integer: offset to read data from (in bytes).
           @return  Binary string: data read.
        """
        #Modified 2010-01-07 to use bulkread.
        data = []
        n_reads = 0
        last_dram_page = -1

        dram_indirect_page_size = (64*1024*1024)
        #read_chunk_size = (1024*1024)
        if verbose:
            print 'Reading a total of %8i bytes from offset %8i...' % (size, offset)

        while n_reads < size:
            dram_page = (offset+n_reads)/dram_indirect_page_size
            local_offset = (offset+n_reads)%(dram_indirect_page_size)
            #local_reads = min(read_chunk_size, size-n_reads, dram_indirect_page_size-(offset%dram_indirect_page_size))
            local_reads = min(size-n_reads, dram_indirect_page_size-(offset%dram_indirect_page_size))
            if verbose:
                print 'Reading %8i bytes from indirect address %4i at local offset %8i...' % (local_reads, dram_page, local_offset),
            if last_dram_page != dram_page:
                self.write_int('dram_controller', dram_page)
                last_dram_page = dram_page
            local_data = (self.bulkread('dram_memory', local_reads, local_offset))
            data.append(local_data)
            if verbose:
                print 'done.'
            n_reads += local_reads
        return ''.join(data)

    def write_dram(self, data, offset = 0, verbose = False):
        """Writes data to a ROACH's DRAM. Writes are done up to 512KiB at a time.
           The 64MB indirect address register is automatically incremented as necessary.
           ROACH has a fixed device name for the DRAM (dram memory) and so the user does not need to specify the write register.

           @param self    This object.
           @param data    Binary packed string to write.
           @param offset  Integer: offset to read data from (in bytes).
           @return  Binary string: data read.
        """
        size = len(data)
        n_writes = 0
        last_dram_page = -1

        dram_indirect_page_size = (64*1024*1024)
        write_chunk_size = (1024*512)
        if verbose:
            print 'writing a total of %8i bytes from offset %8i...' % (size, offset)

        while n_writes < size:
            dram_page = (offset+n_writes)/dram_indirect_page_size
            local_offset = (offset+n_writes)%(dram_indirect_page_size)
            local_writes = min(write_chunk_size, size-n_writes, dram_indirect_page_size-(offset % dram_indirect_page_size))
            if verbose:
                print 'Writing %8i bytes from indirect address %4i at local offset %8i...' % (local_writes, dram_page, local_offset)
            if last_dram_page != dram_page:
                self.write_int('dram_controller', dram_page)
                last_dram_page = dram_page

            self.blindwrite('dram_memory', data[n_writes:n_writes+local_writes], local_offset)
            n_writes += local_writes

    def write(self, device_name, data, offset = 0):
        """Should issue a read command after the write and compare return to
           the string argument to confirm that data was successfully written.

           Throw exception if not match. (alternative command 'blindwrite' does
           not perform this confirmation).

           @see blindwrite
           @param self  This object.
           @param device_name  String: name of device / register to write to.
           @param data  Byte string: data to write.
           @param offset  Integer: offset to write data to (in bytes)
           """
        self.blindwrite(device_name, data, offset)
        new_data = self.read(device_name, len(data), offset)
        if new_data != data:

            unpacked_wrdata = struct.unpack(' > L', data[0:4])[0]
            unpacked_rddata = struct.unpack(' > L', new_data[0:4])[0]

            self._logger.error("Verification of write to %s at offset %d failed. Wrote 0x%08x... but got back 0x%08x..."
                % (device_name, offset, unpacked_wrdata, unpacked_rddata))
            raise RuntimeError("Verification of write to %s at offset %d failed. Wrote 0x%08x... but got back 0x%08x..."
                % (device_name, offset, unpacked_wrdata, unpacked_rddata))

    def blindwrite(self, device_name, data, offset = 0):
        """Unchecked data write.

           @see write
           @param self  This object.
           @param device_name  String: name of device / register to write to.
           @param data  Byte string: data to write.
           @param offset  Integer: offset to write data to (in bytes)
           """
        assert (type(data) == str) , 'You need to supply binary packed string data!'
        assert (len(data)%4) == 0 , 'You must write 32-bit-bounded words!'
        assert ((offset%4) == 0) , 'You must write 32-bit-bounded words!'
        self._request("write", self._timeout, device_name, str(offset), data)

    def read_int(self, device_name):
        """Calls .read() command with size = 4, offset = 0 and
           unpacks returned four bytes into signed 32-bit integer.

           @see read
           @param self  This object.
           @param device_name  String: name of device / register to read.
           @return  Integer: value read.
           """
        data = self.read(device_name, 4, 0)
        return struct.unpack(">i", data)[0]

    def write_int(self, device_name, integer, blindwrite = False, offset = 0):
        """Calls .write() with optional offset and integer packed into 4 bytes.

           @see write
           @param self  This object.
           @param device_name  String: name of device / register to write to.
           @param integer  Integer: value to write.
           @param blindwrite  Boolean: if true, don't verify the write (calls blindwrite instead of write function).
           @param offset  Integer: position in 32-bit words where to write data.
           """
        # careful of packing input data into 32 bit - check range: if
        # negative, must be signed int; if positive over 2^16, must be unsigned
        # int.
        if integer < 0:
            data = struct.pack(">i", integer)
        else:
            data = struct.pack(">I", integer)
        if blindwrite:
            self.blindwrite(device_name, data, offset*4)
            self._logger.debug("Blindwrite %8x to register %s at offset %d done."
                % (integer, device_name, offset))
        else:
            self.write(device_name, data, offset*4)
            self._logger.debug("Write %8x to register %s at offset %d ok."
                % (integer, device_name, offset))

    def read_uint(self, device_name, offset = 0):
        """As in .read_int(), but unpack into 32 bit unsigned int. Optionally read at an offset 32-bit register.

           @see read_int
           @param self  This object.
           @param device_name  String: name of device / register to read from.
           @return  Integer: value read.
           """
        data = self.read(device_name, 4, offset*4)
        return struct.unpack(">I", data)[0]

    def stop(self):
        """Stop the client.

           @param self  This object.
           """
        super(KatcpClientFpga, self).stop()
        self.join(timeout = self._timeout)

    def est_brd_clk(self):
        """Returns the approximate clock rate of the FPGA in MHz."""
        import time
        firstpass = self.read_uint('sys_clkcounter')
        time.sleep(2)
        secondpass = self.read_uint('sys_clkcounter')
        if firstpass > secondpass:
            secondpass = secondpass+(2**32)
        return (secondpass-firstpass)/2000000.

    def qdr_status(self, qdr):
        """Checks QDR status (PHY ready and Calibration). NOT TESTED.
           @param qdr integer QDR controller to query.
           @return dictionary of calfail and phyrdy boolean responses."""
        #offset 0 is reset (write 0x111111... to reset). offset 4, bit 0 is phyrdy. bit 8 is calfail.
        assert((type(qdr) == int))
        qdr_ctrl = struct.unpack(">I", self.read('qdr%i_ctrl'%qdr, 4, 4))[0]
        return {'phyrdy':bool(qdr_ctrl&0x01), 'calfail':bool(qdr_ctrl&(1<<8))}

    def qdr_rst(self, qdr):
        """Performs a reset of the given QDR controller (tries to re-calibrate). NOT TESTED.
           @param qdr integer QDR controller to query.
           @returns nothing."""
        assert((type(qdr) == int))
        self.write_int('qdr%i_ctrl'%qdr, 0xffffffff, blindwrite = True)

    def get_rcs(self, rcs_block_name = 'rcs'):
        """Retrieves and decodes a revision control block."""
        rv = {}
        rv['user'] = self.read_uint(rcs_block_name+'_user')
        app = self.read_uint(rcs_block_name+'_app')
        lib = self.read_uint(rcs_block_name+'_lib')
        if lib&(1<<31):
            rv['compile_timestamp'] = lib&((2**31)-1)
        else:
            if lib&(1<<30):
                #type is svn
                rv['lib_rcs_type'] = 'svn'
            else:
                #type is git
                rv['lib_rcs_type'] = 'git'
            if lib&(1<<28):
                #dirty bit
                rv['lib_dirty'] = True
            else:
                rv['lib_dirty'] = False
            rv['lib_rev'] = lib&((2**28)-1)
        if app&(1<<31):
            rv['app_last_modified'] = app&((2**31)-1)
        else:
            if app&(1<<30):
                #type is svn
                rv['app_rcs_type'] = 'svn'
            else:
                #type is git
                rv['app_rcs_type'] = 'git'
            if app&(1<<28):
                #dirty bit
                rv['app_dirty'] = True
            else:
                rv['lib_dirty'] = False
            rv['app_rev'] = app&((2**28)-1)
        return rv

    def _read_system_info(self):
        '''Katcp request for extra system information embedded in the boffile.
        '''
        # TODO - read the system info from the FPGA via KATCP
        raise NotImplementedError

    def _read_system_info_FILE(self, filename):
        '''Katcp request for extra system information embedded in the boffile.
        '''
        if filename != None:
            fptr = open(filename, 'r')
            lines = fptr.readlines()
            fptr.close()
        info_items = {}
        for line in lines:
            line = line.replace('\_', ' ')
            name, tag, param, value = line.replace('\n', '').split('\t')
            name = name.replace('/', '_')
            if not info_items.has_key(name):
                info_items[name] = {}
            try:
                info_items[name]['tag']
            except KeyError:
                info_items[name]['tag'] = tag
            if info_items[name]['tag'] != tag:
                raise RuntimeError('Different tags - %s, %s - for the same item %s' % (info_items[name]['tag'], tag, name))
            info_items[name][param] = value
        return info_items

    def get_system_information(self, filename):
        '''Get and process the extra system information from the bof file.
        '''
        if False:
        #if not self.is_running():
            log_runtime_error(logger, 'This can only be run on a running device.')
        ################
        # TODO - This should be from the boffile, not from the file.
        device_info = self._read_system_info_FILE(filename)
        ################
        self.system_info = device_info['']

        self.devices = {}

        self.dev_registers = []
        self.dev_snapshots = []
        self.dev_sbrams = []
        self.dev_tengbes = []
        self.dev_adcs = []

        self.__create_devices(device_info)
        if self.is_connected():
            listdev = self.listdev()
            for dev_name, dev in self.devices.items():
                if isinstance(dev, Memory.Memory) and not isinstance(dev, Snap.Snap):
                    try:
                        listdev.index(dev_name)
                    except Exception:
                        log_runtime_error(logger, 'Memory device %s could not be found on parent %s.' % (dev_name, self.parent.name))
        # link snapshot control registers to the snapshots themselves
        for snap in self.dev_snapshots:
            self.devices[snap].link_control_registers(self.registers)

    def remove_device(self, device_name):
        '''
        Remove a specified device from the list of devices present on this design.
        '''
        try:
            self.devices.pop(device_name)
        except:
            log_runtime_error(logger, 'No such device to remove - %s.' % device_name)

    def add_device(self, obj):
        '''
        Add an object to the device list, throwing an exception if it's not an object known to this version.
        '''
        if obj == None:
            log_runtime_error(logger, 'Calling add_device on None type?')
        if self.devices.has_key(obj.name):
            log_runtime_error(logger, 'Device %s of type %s already exists in devices list.' % (obj.name, type(obj)))
        self.devices[obj.name] = obj
        # categorise it
        if isinstance(obj, Register.Register):
            self.dev_registers.append(obj.name)
        elif isinstance(obj, Snap.Snap):
            self.dev_snapshots.append(obj.name)
        elif isinstance(obj, Sbram.Sbram):
            self.dev_sbrams.append(obj.name)
        elif isinstance(obj, TenGbe.TenGbe):
            self.dev_tengbes.append(obj.name)
        elif isinstance(obj, KatAdc.KatAdc):
            self.dev_adcs.append(obj.name)
        else:
            log_runtime_error(logger, 'Unknown device %s of type %s' % (obj.name, type(obj)))

    def __create_devices(self, devices):
        '''Set up devices on this FPGA from a list of design information, from XML or from KATCP.
        '''
        for dev_name, dev_info in devices.items():
            if dev_name != '':
                if self.devices.has_key(dev_name):
                    log_runtime_error(logger, 'Already have device %s, trying to add another with the same name?' % dev_name)
                new_object = None
                if dev_info['tag'] == 'xps:sw_reg':
                    new_object = Register.Register(parent = self, name = dev_name, info = dev_info)
                elif dev_info['tag'] == 'casper:snapshot':
                    new_object = Snap.Snap(parent = self, name = dev_name, info = dev_info)
                elif dev_info['tag'] == 'xps:bram':
                    new_object = Sbram.Sbram(parent = self, name = dev_name, info = dev_info)
                elif dev_info['tag'] == 'xps:tengbe_v2':
                    fabric_ip = dev_info['fab_ip']
                    if fabric_ip.find('(2^24) + ') != -1:
                        dev_info['fab_ip'] = fabric_ip.replace('*(2^24) + ', '.').replace('*(2^16) + ', '.').replace('*(2^8) + ', '.').replace('*(2^0)', '')
                    fabric_mac = dev_info['fab_mac']
                    if fabric_mac.find('hex2dec') != -1:
                        fabric_mac = fabric_mac.replace('hex2dec(\'', '').replace('\')', '')
                        dev_info['fab_mac'] = fabric_mac[0:2] + ':' + fabric_mac[2:4] + ':' + fabric_mac[4:6] + ':' + fabric_mac[6:8] + ':' + fabric_mac[8:10] + ':' + fabric_mac[10:]
                    new_object = TenGbe.TenGbe(parent = self, name = dev_name,
                                               mac = dev_info['fab_mac'],
                                               ip_address = dev_info['fab_ip'],
                                               port = dev_info['fab_udp'])
                elif dev_info['tag'] == 'xps:katadc':
                    new_object = KatAdc.KatAdc(parent = self, name = dev_name, info = dev_info)
                else:
                    logger.info('Unhandled device %s of type %s' % (dev_name, dev_info['tag']))
                # add it to the list of devices
                if new_object != None:
                    self.add_device(new_object)

    def get_static_info(self, param):
        '''Get an info item from this FPGA. One that was stored in the coreinfo.tab and accessed via KATCP on startup.
        '''
        if not self.design_info.has_key(param):
            log_runtime_error(logger, 'Asking FPGA %s for design_info %s, which doesn\'t exist.' % (self.host, param))
        return self.design_info[param]

    def set_bof(self, bofname):
        '''Set the name of the bof file that will be used on this FPGA host.
        '''
        self.bofname = bofname

#     def process_xml_config(self, design_info):
#         '''Read design information from an XML file generated during casper_xps.
#         '''
#         # does the file exists
#         if not isinstance(design_info, str): return
#         try:
#             open(design_info)
#         except:
#             log_runtime_error(logger, 'Cannot open design_info file %s' % design_info)
#         import xml.etree.ElementTree as ElementTree
#         try:
#             doc = ElementTree.parse(design_info)
#         except:
#             log_runtime_error(logger, 'design_info file %s does not seem to be valid XML?' % design_info)
#         rootnode = doc.getroot()
#         self.build_date = rootnode.attrib['datestr']
#         self.system_name = rootnode.attrib['system']
#         self.version = rootnode.attrib['version']
#         from os import path
#         self.bofname = path.basename(design_info).replace('.xml', '.bof')
#         def process_object(doc_node, objclass, storage):
#             for node in list(doc_node):
#                 obj = objclass(parent = self, xml_node = node)
#                 storage[obj.name] = obj
#         # iterate through the tags in the root node
#         design_info_node = None;
#         for node in list(rootnode):
#             if node.tag == 'memory':
#                 process_object(node, Memory.Memory, self.memory)
#             elif node.tag == 'device_class':
#                 if node.attrib['class'] == 'register':
#                     process_object(node, Register.Register, self.registers)
#                 elif node.attrib['class'] == 'snapshot':
#                     process_object(node, Snap.Snap, self.dev_snapshots)
#                 else:
#                     log_runtime_error(logger, 'Unknown node class %s in XML?' % node['class'])
#             elif node.tag == 'design_info':
#                 design_info_node = node;
#             else:
#                 log_runtime_error(logger, 'Unknown XML tag in design file?')
#         if (design_info_node == None) and (len(self.dev_snapshots)  >  0):
#             log_runtime_error(logger, 'Snapshots found, but not design info to complete them?')
#         # put the extra info into a dictionary
#         self.design_info = {}
#         for n in list(design_info_node):
#             self.design_info[n.attrib['name']] = n.attrib['info']
#         # reconcile snap info blocks with their snap blocks
#         for s in self.dev_snapshots.values():
#             print s.name, s.blockpath
#             info_dict = {key.replace(s.blockpath + '/', ''):value for key, value in self.design_info.iteritems() if key.startswith(s.blockpath + '/')};
#             try:
#                 extra_reg = self.registers[s.name + '_val']
#             except KeyError:
#                 extra_reg = None
#             s.add_snap_info(info_dict, extra_reg)

#     def process_new_core_info(self, design_info):
#         # does the file exists
#         if not isinstance(design_info, str): return
#         try:
#             open(design_info)
#         except:
#             log_runtime_error(logger, 'Cannot open design_info file %s' % design_info)
#         import xml.etree.ElementTree as ElementTree
#         try:
#             doc = ElementTree.parse(design_info)
#         except:
#             log_runtime_error(logger, 'design_info file %s does not seem to be valid XML?' % design_info)
#         rootnode = doc.getroot()
#         self.build_date = rootnode.attrib['datestr']
#         self.system_name = rootnode.attrib['system']
#         self.version = rootnode.attrib['version']
#         from os import path
#         self.bofname = path.basename(design_info).replace('.xml', '.bof')
#         # get registers, snapblocks, brams, etc from the XML file
#         register_paths = []
#         snapshot_paths = []
#         sbram_names = []
#         for node in rootnode.getChildren():
#             if node.tag == 'design_info':
#                 for infonode in node.getChildren():
#                     if infonode.attrib('owner') == "":
#                         if infonode.attrib('param') == "registers":
#                             register_paths = infonode.attrib('value').split(', ')
#                         if infonode.attrib('param') == "snapshots":
#                             snapshot_paths = infonode.attrib('value').split(', ')
#
#         print register_paths
#         print snapshot_paths
#
#         return
#
#
#         design_info_node = None;
#         for node in rootnode.getChildren():
#             if node.tag == 'memory':
#                 process_object(node, Memory.Memory, self.memory)
#             elif node.tag == 'device_class':
#                 if node.attrib['class'] == 'register':
#                     process_object(node, Register.Register, self.registers)
#                 elif node.attrib['class'] == 'snapshot':
#                     process_object(node, Snap.Snap, self.snaps)
#                 else:
#                     log_runtime_error(logger, 'Unknown node class %s in XML?' % node['class'])
#             elif node.tag == 'design_info':
#                 design_info_node = node;
#             else:
#                 log_runtime_error(logger, 'Unknown XML tag in design file?')
#         if (design_info_node == None) and (len(self.snaps)  >  0):
#             log_runtime_error(logger, 'Snapshots found, but not design info to complete them?')
#         # put the extra info into a dictionary
#         self.design_info = {}
#         for n in list(design_info_node):
#             self.design_info[n.attrib['name']] = n.attrib['info']
#         # reconcile snap info blocks with their snap blocks
#         for s in self.snaps.values():
#             print s.name, s.blockpath
#             info_dict = {key.replace(s.blockpath + '/', ''):value for key, value in self.design_info.iteritems() if key.startswith(s.blockpath + '/')};
#             try:
#                 extra_reg = self.registers[s.name + '_val']
#             except KeyError:
#                 extra_reg = None
#             s.add_snap_info(info_dict, extra_reg);

#     def process_new_core_info_xml(self, design_info):
#         '''Read design info from a XML file.
#         This is be superceded by read_new_core_info, which will get it from a KATCP request.
#         So this is only for development.
#         @param design_info: The filename for the design information XML file, as generated by the casper_xps process.
#         '''
#         if not isinstance(design_info, str): return
#         try:
#             open(design_info)
#         except:
#             log_runtime_error(logger, 'Cannot open design_info file %s' % design_info)
#
#         # set the bofname
#         from os import path
#         self.bofname = path.basename(design_info).replace('_info.xml', '.bof')
#
#         # open the XML file
#         import xml.etree.ElementTree as ElementTree
#         try:
#             doc = ElementTree.parse(design_info)
#         except:
#             log_runtime_error(logger, 'design_info file %s does not seem to be valid XML?' % design_info)
#         rootnode = doc.getroot()
#         self.build_date = rootnode.attrib['datestr']
#         self.system_name = rootnode.attrib['system']
#         self.version = rootnode.attrib['version']
#
#         # get the info node
#         infonode = None
#         for node in list(rootnode):
#             if node.tag == 'design_info':
#                 infonode = node
#                 break
#         memorynode = None
#         for node in list(rootnode):
#             if node.tag == 'memory':
#                 memorynode = node
#                 break
#
#         # get simulink block info from the XML file
#         tags = {}
#         def __get_info_param(param):
#             for inode in list(infonode):
#                 if (inode.attrib['owner'] == "") and (inode.attrib['param'] == param):
#                     return inode
#             raise RuntimeError('No such parameter in info: %s' % param)
#
#         def __build_device_by_owner(owner):
#             d = {}
#             for inode in list(infonode):
#                 if inode.attrib['owner'] == owner:
#                     d[inode.attrib['param']] = inode.attrib['value']
#             return d
#         tags_node = __get_info_param('tags')
#         temptags = tags_node.attrib['value'].split(', ')
#         for t in temptags:
#             tags[t] = {}
#         if len(tags.keys()) == 0:
#             log_runtime_error(logger, 'Could not find any tags in file info?')
#         # make lists of tags
#         for tag in tags.keys():
#             tag_node = __get_info_param(tag)
#             if tag_node.attrib['value'] == '':
#                 tags[tag] = []
#             else:
#                 tags[tag] = tag_node.attrib['value'].split(', ')
#
#         # build the objects in the design from the info nodes, indexed by tag, then by name
#         devices = {}
#         for tag, item_list in tags.items():
#             for item in item_list:
#                 obj = __build_device_by_owner(item)
#                 devices[item] = obj
#                 devices[item]['tag'] = tag
#
#         # now make a dictionary from the memory nodes, index by name
#         memory_info = {}
#         for mem in memorynode:
#             mem_owner = mem.attrib['owner']
#             if not memory_info.has_key(mem_owner):
#                 memory_info[mem_owner] = {}
#             memory_info[mem_owner][mem.attrib['name']] = mem.attrib
#             try: devices[mem_owner]
#             except Exception: raise
#
#         # create devices found on this FPGA
#         self.__create_devices(devices, memory_info)
#         # now categorise the devices
#         self.__categorise_devices()

# end
