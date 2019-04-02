import time;
sensor_call_gap_time_s = 0.0025;
sensor_loop_runtime = 0;
sensor_loop_running_tasks = 0;

class SensorTask:
    def __init__(self,function_name):
        self.last_runtime = 0
        self.executed = False;
        self.name = function_name;

    def getNextSensorCallTime(self,current_function_runtime=0):
        global sensor_loop_runtime;
        global sensor_call_gap_time_s;
        global sensor_loop_running_tasks
        last_runtime = self.last_runtime;
        if(self.executed == False):
            self.executed = True;
            sensor_loop_running_tasks+=1
        current_runtime = current_function_runtime
        self.last_runtime = current_runtime

        sensor_loop_runtime = sensor_loop_runtime - last_runtime + current_runtime;
        nextSensorCallTime = time.time() + sensor_loop_runtime + sensor_loop_running_tasks*sensor_call_gap_time_s
        return nextSensorCallTime
        
    
    
