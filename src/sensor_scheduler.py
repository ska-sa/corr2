import time;
sensor_call_gap_time_s = 0.003;
sensor_loop_runtime = 0;
sensor_loop_running_tasks = 0;
sensor_loop_start_time = round(time.time())+4;
sensor_loop_flow_control_padding = 0;
logger = None;

class SensorTask:
    def __init__(self,function_name):
        self.last_runtime_length = 0
        self.last_runtime_utc = 0;
        self.executed = False;
        self.name = function_name;
        self.num_time_overruns = 0;
        self.flow_control_increments = 0;
        logger.debug(self.name)
        #print(function_name)

    def getNextSensorCallTime(self,current_function_runtime=0):
        global sensor_loop_runtime;
        global sensor_call_gap_time_s;
        global sensor_loop_running_tasks;
        global sensor_loop_start_time;
        global sensor_loop_flow_control_padding;
        global logger
        
        #printTime = False;
        last_runtime_length = self.last_runtime_length;
        if(self.executed == False):
            self.executed = True;
            sensor_loop_running_tasks+=1
            self.last_runtime_utc = sensor_loop_start_time;
        #    printTime = True;

        self.last_runtime_length = current_function_runtime
        
        next_sensor_call_time = self.last_runtime_utc + (sensor_loop_running_tasks+sensor_loop_flow_control_padding)*sensor_call_gap_time_s
        self.last_runtime_utc = next_sensor_call_time

        #Network Flow Control
        if(current_function_runtime>sensor_call_gap_time_s*(self.flow_control_increments+1)):
            self.num_time_overruns+=1;
        elif(current_function_runtime<sensor_call_gap_time_s*(self.flow_control_increments)):
            self.num_time_overruns-=1;
        else:
            self.num_time_overruns=0
        
        if(self.num_time_overruns > 5):
            #print("%s took %fs longer to run than allocated - this occured five times in a row, performing flow control"%(self.name,current_function_runtime-(1+self.flow_control_increments)*sensor_call_gap_time_s))
            self.num_time_overruns=0
            self.flow_control_increments+=1
            sensor_loop_flow_control_padding+=1

        if(self.num_time_overruns < -5):
            #print("%s took %fs less to run than allocated - this occured five times in a row, performing flow control"%((1+self.flow_control_increments)*sensor_call_gap_time_s)-self.name,current_function_runtime)
            self.num_time_overruns=0
            self.flow_control_increments-=1
            sensor_loop_flow_control_padding-=1

        logger.debug('{0:} finished at {1:.4f}. Next Call:{2:.4f} Runtime: {3:.5f}.'.format(self.name,time.time(),next_sensor_call_time,current_function_runtime))
        #if(printTime):
        #    print ("Sensor function: {0:} First Call: {1:.4f} Next Call: {2:.4f}".format(self.name,time.time(),next_sensor_call_time))
        return next_sensor_call_time

        
    
    
