'''
Created on Feb 28, 2013

@author: paulp
'''

import logging, katcp, struct
import Host, AsyncRequester, Register, Snap, Memory
from Misc import log_runtime_error

logger = logging.getLogger(__name__)

# if __name__ == '__main__':
#     print 'Hello World'

class KatcpClientFpga(Host.Host, AsyncRequester.AsyncRequester, katcp.CallbackClient):
    '''
    A Roach(2) board - there is a KATCP client running on the PowerPC on the board.
    '''
    def __init__(self, host, ip, katcp_port=7147, timeout=5.0, connect=True, design_xml=None):
        '''Constructor.
        '''
        Host.Host.__init__(self, host, ip, katcp_port)
        AsyncRequester.AsyncRequester.__init__(self, self.callback_request, max_requests=100)
        katcp.CallbackClient.__init__(self, host, katcp_port, tb_limit=20, timeout=timeout, logger=logger, auto_reconnect=True)
        
        # registers and snap blocks
        self.registers = {}
        self.snapshots = {}
        self.memory = {}
        
        # ten gbe ports
        self.tengbes = {}
        
        # process the auto-generated XML configuration
        #self.process_xml_config(design_xml)
        self.process_new_core_info(design_xml)
        self.design_xml = design_xml
        self.running_bof = ''
        
        # start katcp daemon
        self._timeout = timeout
        if connect: self.start(daemon = True)

        logger.info('%s:%s created%s.' % (host, katcp_port, ' & daemon started' if connect else ''))

    def connect(self):
        logger.info('%s: daemon started' % self.host)
        self.start(daemon = True)

    def disconnect(self):
        logger.info('%s: daemon stopped' % self.host)
        self.stop()

    def __str__(self):
        return 'KatcpFpga(%s)@%s:%i engines(%i) regs(%i) snaps(%i) - %s' % (self.host, self.ip, self.port, len(self.engines), len(self.registers),
                                                                       len(self.snapshots), 'connected' if self.is_connected() else 'disconnected')

    def _request(self, name, request_timeout = -1, *args):
        """Make a blocking request and check the result.
        
           Raise an error if the reply indicates a request failure.

           @param self  This object.
           @param name  String: name of the request message to send.
           @param request_timeout  Int: number of seconds after which the request must time out
           @param args  List of strings: request arguments.
           @return  Tuple: containing the reply and a list of inform messages.
           """
        if request_timeout == -1: request_timeout = self._timeout
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

    def progdev(self, boffile):
        """Program the FPGA with the specified boffile.

           @param self  This object.
           @param boffile  String: name of the BOF file.
           @return  String: device status.
           """
        if boffile=='' or boffile==None:
            reply, informs = self._request("progdev", self._timeout, '')
            if reply.arguments[0] == 'ok':
                self.running_bof = ''
            logger.info("Deprogramming FPGA %s... %s." % (self.host, reply.arguments[0]))
        else:
            if boffile != self.bofname:
                logger.warning('Programming BOF file %s, config BOF file %s' % (boffile, self.bofname))
            reply, informs = self._request("progdev", self._timeout, boffile)
            if reply.arguments[0] == 'ok':
                self.running_bof = boffile
            logger.info("Programming FPGA %s with %s... %s."%(self.host, boffile, reply.arguments[0]))
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
    
    def read(self, device_name, size, offset=0):
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
    
    def bulkread(self, device_name, size, offset=0):
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
    
    def upload_bof(self, bof_file, port, force_upload=False, timeout=30):
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
                result = self._request('uploadbof', timeout, port, filename)
                if(result[0].arguments[0] == katcp.Message.OK):
                    result_queue.put('')
                else:
                    result_queue.put('Request to client returned, but not Message.OK.')
            except:
                result_queue.put('Request to client failed.')
        def uploadbof(filename, result_queue):
            upload_socket = socket.socket()
            stime = time.time()
            connected = False
            while (not connected) and (time.time() - stime < 2):
                try:
                    upload_socket.connect((self.host, port))
                    connected = True
                except:
                    time.sleep(0.1)
            if not connected:
                result_queue.put('Could not connect to upload port.')
            try:
                upload_socket.send(open(filename).read())
            except:
                result_queue.put('Could not send file to upload port.')
            result_queue.put('')
        # request thread
        request_queue = Queue.Queue()
        request_thread = threading.Thread(target = makerequest, args = (request_queue,))
        # upload thread
        upload_queue = Queue.Queue()
        upload_thread = threading.Thread(target = uploadbof, args = (bof_file, upload_queue,))
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
        debugstr = "Bof file upload for '", bof_file,"': request (", request_result, "), uploaded (", upload_result,")" 
        self._logger.info(debugstr)
        return

    def read_dram(self, size, offset=0,verbose=False):
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
        data=[]
        n_reads=0
        last_dram_page = -1

        dram_indirect_page_size=(64*1024*1024)
        #read_chunk_size=(1024*1024)
        if verbose: print 'Reading a total of %8i bytes from offset %8i...' % (size, offset)

        while n_reads < size:
            dram_page=(offset+n_reads)/dram_indirect_page_size
            local_offset = (offset+n_reads)%(dram_indirect_page_size)
            #local_reads = min(read_chunk_size,size-n_reads,dram_indirect_page_size-(offset%dram_indirect_page_size))
            local_reads = min(size-n_reads,dram_indirect_page_size-(offset%dram_indirect_page_size))
            if verbose: print 'Reading %8i bytes from indirect address %4i at local offset %8i...' % (local_reads, dram_page, local_offset),
            if last_dram_page != dram_page: 
                self.write_int('dram_controller',dram_page)
                last_dram_page = dram_page
            local_data=(self.bulkread('dram_memory',local_reads,local_offset))
            data.append(local_data)
            if verbose: print 'done.'
            n_reads += local_reads
        return ''.join(data)

    def write_dram(self, data, offset=0,verbose=False):
        """Writes data to a ROACH's DRAM. Writes are done up to 512KiB at a time.
           The 64MB indirect address register is automatically incremented as necessary.
           ROACH has a fixed device name for the DRAM (dram memory) and so the user does not need to specify the write register.

           @param self    This object.
           @param data    Binary packed string to write.
           @param offset  Integer: offset to read data from (in bytes).
           @return  Binary string: data read.
        """
        size=len(data)
        n_writes=0
        last_dram_page = -1

        dram_indirect_page_size=(64*1024*1024)
        write_chunk_size=(1024*512)
        if verbose: print 'writing a total of %8i bytes from offset %8i...'%(size,offset)

        while n_writes < size:
            dram_page=(offset+n_writes)/dram_indirect_page_size
            local_offset = (offset+n_writes)%(dram_indirect_page_size)
            local_writes = min(write_chunk_size,size-n_writes,dram_indirect_page_size-(offset%dram_indirect_page_size))
            if verbose: print 'Writing %8i bytes from indirect address %4i at local offset %8i...'%(local_writes,dram_page,local_offset)
            if last_dram_page != dram_page: 
                self.write_int('dram_controller',dram_page)
                last_dram_page = dram_page

            self.blindwrite('dram_memory',data[n_writes:n_writes+local_writes],local_offset)
            n_writes += local_writes

    def write(self, device_name, data, offset=0):
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

            unpacked_wrdata=struct.unpack('>L',data[0:4])[0]
            unpacked_rddata=struct.unpack('>L',new_data[0:4])[0]

            self._logger.error("Verification of write to %s at offset %d failed. Wrote 0x%08x... but got back 0x%08x..."
                % (device_name, offset, unpacked_wrdata, unpacked_rddata))
            raise RuntimeError("Verification of write to %s at offset %d failed. Wrote 0x%08x... but got back 0x%08x..."
                % (device_name, offset, unpacked_wrdata, unpacked_rddata))

    def blindwrite(self, device_name, data, offset=0):
        """Unchecked data write.

           @see write
           @param self  This object.
           @param device_name  String: name of device / register to write to.
           @param data  Byte string: data to write.
           @param offset  Integer: offset to write data to (in bytes)
           """
        assert (type(data)==str) , 'You need to supply binary packed string data!'
        assert (len(data)%4) ==0 , 'You must write 32bit-bounded words!'
        assert ((offset%4) ==0) , 'You must write 32bit-bounded words!'
        self._request("write", self._timeout, device_name, str(offset), data)

    def read_int(self, device_name):
        """Calls .read() command with size=4, offset=0 and
           unpacks returned four bytes into signed 32bit integer.

           @see read
           @param self  This object.
           @param device_name  String: name of device / register to read.
           @return  Integer: value read.
           """
        data = self.read(device_name, 4, 0)
        return struct.unpack(">i", data)[0]

    def write_int(self, device_name, integer, blindwrite=False, offset=0):
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
            self.blindwrite(device_name,data,offset*4)
            self._logger.debug("Blindwrite %8x to register %s at offset %d done."
                % (integer, device_name, offset))
        else:
            self.write(device_name, data, offset*4)
            self._logger.debug("Write %8x to register %s at offset %d ok."
                % (integer, device_name, offset))

    def read_uint(self, device_name,offset=0):
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
        super(KatcpClientFpga,self).stop()
        self.join(timeout=self._timeout)

    def est_brd_clk(self):
        """Returns the approximate clock rate of the FPGA in MHz."""
        import time
        firstpass=self.read_uint('sys_clkcounter')
        time.sleep(2)
        secondpass=self.read_uint('sys_clkcounter')
        if firstpass>secondpass: secondpass=secondpass+(2**32)
        return (secondpass-firstpass)/2000000.

    def qdr_status(self,qdr):
        """Checks QDR status (PHY ready and Calibration). NOT TESTED.
           @param qdr integer QDR controller to query.
           @return dictionary of calfail and phyrdy boolean responses."""
        #offset 0 is reset (write 0x111111... to reset). offset 4, bit 0 is phyrdy. bit 8 is calfail.
        assert((type(qdr)==int))
        qdr_ctrl = struct.unpack(">I",self.read('qdr%i_ctrl'%qdr, 4, 4))[0]
        return {'phyrdy':bool(qdr_ctrl&0x01),'calfail':bool(qdr_ctrl&(1<<8))}

    def qdr_rst(self,qdr):
        """Performs a reset of the given QDR controller (tries to re-calibrate). NOT TESTED.
           @param qdr integer QDR controller to query.
           @returns nothing."""
        assert((type(qdr)==int))
        self.write_int('qdr%i_ctrl'%qdr,0xffffffff,blindwrite=True)

    def get_rcs(self, rcs_block_name='rcs'):
        """Retrieves and decodes a revision control block."""
        rv={}
        rv['user']=self.read_uint(rcs_block_name+'_user')
        app=self.read_uint(rcs_block_name+'_app')
        lib=self.read_uint(rcs_block_name+'_lib')
        if lib&(1<<31): 
            rv['compile_timestamp']=lib&((2**31)-1)
        else: 
            if lib&(1<<30):
                #type is svn
                rv['lib_rcs_type']='svn'
            else:
                #type is git
                rv['lib_rcs_type']='git'
            if lib&(1<<28):
                #dirty bit
                rv['lib_dirty']=True
            else:
                rv['lib_dirty']=False
            rv['lib_rev']=lib&((2**28)-1)
        if app&(1<<31): 
            rv['app_last_modified']=app&((2**31)-1)
        else: 
            if app&(1<<30):
                #type is svn
                rv['app_rcs_type']='svn'
            else:
                #type is git
                rv['app_rcs_type']='git'
            if app&(1<<28):
                #dirty bit
                rv['app_dirty']=True
            else:
                rv['lib_dirty']=False
            rv['app_rev']=app&((2**28)-1)
        return rv

    def _snapshot_get(self, dev_name, man_trig=False, man_valid=False, wait_period=1, offset=-1, circular_capture=False, get_extra_val=False):
        raise NotImplementedError

    def process_xml_config(self, design_info):
        # does the file exists
        if not isinstance(design_info, str): return
        try:
            open(design_info)
        except:
            log_runtime_error(logger, 'Cannot open design_info file %s' % design_info)
        import xml.etree.ElementTree as ElementTree
        try:
            doc = ElementTree.parse(design_info)
        except:
            log_runtime_error(logger, 'design_info file %s does not seem to be valid XML?' % design_info)
        rootnode = doc.getroot()
        self.build_date = rootnode.attrib['datestr']
        self.sysname = rootnode.attrib['system']
        self.version = rootnode.attrib['version']
        from os import path
        self.bofname = path.basename(design_info).replace('.xml','.bof')
        def process_object(doc_node, objclass, storage):
            for node in list(doc_node):
                obj = objclass(parent=self, xml_node=node)
                storage[obj.name] = obj
        # iterate through the tags in the root node
        design_info_node = None;
        for node in list(rootnode):
            if node.tag == 'memory':
                process_object(node, Memory.Memory, self.memory)
            elif node.tag == 'device_class':
                if node.attrib['class'] == 'register':
                    process_object(node, Register.Register, self.registers)
                elif node.attrib['class'] == 'snapshot':
                    process_object(node, Snap.Snap, self.snapshots)
                else:
                    log_runtime_error(logger, 'Unknown node class %s in XML?' % node['class'])
            elif node.tag == 'design_info':
                design_info_node = node;
            else:
                log_runtime_error(logger, 'Unknown XML tag in design file?')
        if (design_info_node == None) and (len(self.snapshots) > 0):
            log_runtime_error(logger, 'Snapshots found, but not design info to complete them?')
        # put the extra info into a dictionary
        self.design_info = {}
        for n in list(design_info_node):
            self.design_info[n.attrib['name']] = n.attrib['info']
        # reconcile snap info blocks with their snap blocks
        for s in self.snapshots.values():
            print s.name, s.blockpath
            info_dict = {key.replace(s.blockpath + '/', ''):value for key,value in self.design_info.iteritems() if key.startswith(s.blockpath + '/')};
            try:
                extra_reg = self.registers[s.name + '_val']
            except KeyError:
                extra_reg = None
            s.add_snap_info(info_dict, extra_reg);

    def process_new_core_info(self, design_info):
        # does the file exists
        if not isinstance(design_info, str): return
        try:
            open(design_info)
        except:
            log_runtime_error(logger, 'Cannot open design_info file %s' % design_info)
        import xml.etree.ElementTree as ElementTree
        try:
            doc = ElementTree.parse(design_info)
        except:
            log_runtime_error(logger, 'design_info file %s does not seem to be valid XML?' % design_info)
        rootnode = doc.getroot()
        self.build_date = rootnode.attrib['datestr']
        self.sysname = rootnode.attrib['system']
        self.version = rootnode.attrib['version']
        from os import path
        self.bofname = path.basename(design_info).replace('.xml','.bof')
        # get registers, snapblocks, brams, etc from the XML file
        register_paths = []
        snapshot_paths = []
        sbram_names = []
        info_nodes = []
        for node in list(rootnode):
            if node.tag == 'design_info':
                for infonode in list(node):
                    if infonode.attrib['owner'] == "":
                        if infonode.attrib['param'] == "registers":
                            register_paths = infonode.attrib['value'].split(',')
                        if infonode.attrib['param'] == "snapshots":
                            snapshot_paths = infonode.attrib['value'].split(',')
                    elif infonode.attrib['owner'] == self.sysname:
                        info_nodes.append(infonode)
        self.registers = {}
        for reg_path in register_paths:
            reg_name = reg_path.replace('/','_')
            register = Register.Register(parent=self, name=reg_name)
            register._update_from_new_coreinfo_xml(xml_root_node = rootnode)
            self.registers[register.name] = register
        self.snapshots = {}
        for snap_path in snapshot_paths:
            snap_name = snap_path.replace('/','_')
            snap = Snap.Snap(parent=self, name=snap_name)
            snap._update_from_new_coreinfo_xml(xml_root_node = rootnode)
            snap._update_control_registers(self.registers)
            self.snapshots[snap.name] = snap
#         for b in sbram_names:
#             bram = Brams(parent = mock_fpga, name=s)
#             bram._update_from_new_coreinfo_xml(xml_root_node = rootnode)
        self.design_info = {}
        for n in info_nodes:
            self.design_info[n.attrib['param']] = n.attrib['value']

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
#         self.sysname = rootnode.attrib['system']
#         self.version = rootnode.attrib['version']
#         from os import path
#         self.bofname = path.basename(design_info).replace('.xml','.bof')
#         # get registers, snapblocks, brams, etc from the XML file
#         register_paths = []
#         snapshot_paths = []
#         sbram_names = []
#         for node in rootnode.getChildren():
#             if node.tag == 'design_info':
#                 for infonode in node.getChildren():
#                     if infonode.attrib('owner') == "":
#                         if infonode.attrib('param') == "registers":
#                             register_paths = infonode.attrib('value').split(',')
#                         if infonode.attrib('param') == "snapshots":
#                             snapshot_paths = infonode.attrib('value').split(',')
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
#         if (design_info_node == None) and (len(self.snaps) > 0):
#             log_runtime_error(logger, 'Snapshots found, but not design info to complete them?')
#         # put the extra info into a dictionary
#         self.design_info = {}
#         for n in list(design_info_node):
#             self.design_info[n.attrib['name']] = n.attrib['info']
#         # reconcile snap info blocks with their snap blocks
#         for s in self.snaps.values():
#             print s.name, s.blockpath
#             info_dict = {key.replace(s.blockpath + '/', ''):value for key,value in self.design_info.iteritems() if key.startswith(s.blockpath + '/')};
#             try:
#                 extra_reg = self.registers[s.name + '_val']
#             except KeyError:
#                 extra_reg = None
#             s.add_snap_info(info_dict, extra_reg);

# end
