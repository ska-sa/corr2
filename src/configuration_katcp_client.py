import logging
LOGGER = logging.getLogger(__name__)

import iniparse, katcp, types
from corr2 import async_requester
from misc import log_runtime_error, log_io_error, log_not_implemented_error, log_value_error

#TODO
def get_remote_config(host, katcp_port):
    '''Connects to katcp daemon on remote host and gets config, constructing dictionary
    '''
    log_runtime_error(LOGGER, 'Can''t get remote config yet')

class ConfigurationKatcpClient(async_requester.AsyncRequester, katcp.CallbackClient):
    '''A container class for accessing configuration information. 
    '''
    def __init__(self, config_host=None, katcp_port=None, config_file=None):
        '''Constructor
        @param config_host: host name of server containing daemon serving configuration information via katcp
        @param katcp_port: port number configuration daemon is listening on
        @param config_file: file containing configuration information (overrides katcp)
        '''
        if config_file == None and (host == None or katcp_port == None):
            log_runtime_error(LOGGER, 'Need a configuration file name or katcp host location')
            
        self.source = None
        self.config_host = ''
        self.katcp_port = 0

        if config_file != None:
            try:
                fptr = open(config_file, 'r')
            except:
                log_io_error(LOGGER, 'Configuration file \'%s\' cannot be opened.' % filename)
            self.config = iniparse.INIConfig(fptr)
            fptr.close()
            self.source = 'file'
        else:  
            self.config = None
            if (not isinstance(config_host, str)):
                log_runtime_error(LOGGER, 'config_host must be a string')
            self.config_host = config_host
            if (not isinstance(katcp_port, int)):
                log_runtime_error(LOGGER, 'katcp_port must be an int')
            self.katcp_port = katcp_port
            self.config = get_remote_config(self.config_host, self.katcp_port)
            self.source = 'katcp'      

        self.get_config()

    def get_config(self):
        # if getting from file, maintain our own host pool
        if self.source == 'file':
            host_types = self.get_str_list(['hosts', 'types'])
            self.host_pool = {}
            for host_type in host_types:
                self.host_pool[host_type] = self.get_str_list(['%s'%host_type, 'pool'])            

    def get_hosts(self, host_type='roach2', number=None, hostnames=None):
        ''' Request hosts for use
        @param hostnames: specific host names
        @param host_type: type of host if not specific
        @param number: number of type if not specific
        @return hostnames if available or empty list if not
        '''
        if self.source == 'file':
            hosts = list()
            if hostnames==None:
                avail_hosts = self.host_pool['%s'%host_type]
                hosts.extend(avail_hosts[0:number])
                avail_hosts = avail_hosts[number:len(avail_hosts)]
                self.host_pool['%s'%host_type] = avail_hosts
                return hosts
            else:
                log_runtime_error(LOGGER, 'Don''t know how to get specific hostnames yet')
                #TODO
        else:
            log_runtime_error(LOGGER, 'Don''t know how to get hosts via katcp yet')
 
    def return_hosts(self, hostnames, host_type='roach2'):
        ''' Return hosts to the pool
        '''
        #check type
        if self.source == 'file':
            self.host_pool['%s'%host_type].extend(hostnames)
        else:
            log_runtime_error(LOGGER, 'Don''t know how to return hosts via katcp yet ')
            #TODO katcp stuff

    def get_string(self, target, fail_hard=True):
        '''Get configuration string 
        @param target: list describing parameter
        @param fail_hard: throw exception on failure to locate target
        '''
        if not isinstance(target, list):
            log_runtime_error(LOGGER, 'Configuration target must be a list in the form [section, name]')
        
        if len(target) != 2:
            log_runtime_error(LOGGER, 'Configuration target must be a list in the form [section, name]')

        # if a file then we have an iniparse structure
        if self.source == 'file':
            if not isinstance(target[0], str) or not isinstance(target[1], str):
                log_runtime_error(LOGGER, 'target must be strings in form [section, parameter]')

            section = self.config[target[0]]
            if isinstance(section, iniparse.config.Undefined):
                string = None
                msg = 'Asked for unknown section \'%s\''% (target[0])
                if fail_hard==True:
                    log_runtime_error(LOGGER, msg)
                else:
                    LOGGER.warning(msg)
            else:
                string = section[target[1]]
                if isinstance(string, iniparse.config.Undefined):
                    string = None
                    msg = 'Asked for unknown parameter \'%s\' in section \'%s\''% (target[1], target[0])
                    if fail_hard==True:
                        log_runtime_error(LOGGER, msg)
                    else:
                        LOGGER.warning(msg)
        # if katcp we have config in a dict
        elif self.source == 'katcp':
            log_runtime_error(LOGGER, 'Can''t get configuration via katcp yet')
        else:
            log_runtime_error(LOGGER, 'Unknown configuration source')
        return string

    def get_str_list(self, target, fail_hard=True): 
        '''Get configuration list
        '''
        string = self.get_string(target, fail_hard)

        if string != None:
            try:
                value = string.split(types.LISTDELIMIT)
            except ValueError:
                log_value_error(LOGGER, 'Error converting \'%s\' to list while getting config item %s' %(string, str(target)))
            return value
        else:
            return None

    def get_int(self, target, fail_hard=True): 
        '''Get configuration int
        '''
        string = self.get_string(target, fail_hard)
        if string != None:
            try:
                value = int(string)
            except ValueError:
                log_value_error(LOGGER, 'Error converting \'%s\' to integer while getting config item %s' %(string, str(target)))
            return value
        else:
            return None

    def get_int_list(self, target, fail_hard=True): 
        '''Get configuration list
        '''
        string = self.get_string(target, fail_hard)

        if string != None:
            try:
                str_list = string.split(types.LISTDELIMIT)
            except ValueError:
                log_value_error(LOGGER, 'Error converting \'%s\' to list while getting config item %s' %(string, str(target)))

            int_list = list()
            for index, string in enumerate(str_list):
                try:
                    int_val = int(string)
                except ValueError:
                    log_value_error(LOGGER, 'Error converting \'%s\' to integer while creating int list from %s' %(string, str(target)))
                int_list.append(int_val)
            return int_list
        else:
            return None


    def get_float(self, target, fail_hard=True): 
        '''Get configuration float
        '''
        string = self.get_string(target, fail_hard)
        if string != None:
            try:
                value = float(string)
            except ValueError:
                log_value_error(LOGGER, 'Error converting \'%s\' to float while getting config item %s' %(string, str(target)))
            return value
        else:
            return None
