#!/usr/bin/env python

##################################################################
#
#   Sample sensors via sbcctl
#
#   2016-07-15  Todd Valentic
#               Initial implementation. Based on TS7260 code.
#
##################################################################

from DataMonitor import DataMonitorComponent

import struct

# Binary output file section IDs

SECTION_END         = 0
SECTION_GPIO        = 1
SECTION_SENSORS     = 2

class SBCMonitor(DataMonitorComponent):

    def __init__(self,*pos,**kw):
        DataMonitorComponent.__init__(self,*pos,**kw)

    def sample(self):
        return self.getStatus()

    def encodeDIO(self,config,section):

        pins = 0

        for pin in range(8):
            try:
                value = config.getint(section,'Pin %d' % pin)
                if value:
                    pins |= 2**pin
            except:
                continue

        return pins

    def encodeSensors(self,config,section):

        values = []

        for sensor in range(5):
            key = 'temp%d_input'
            try:
                value = config.getfloat(section,key % (sensor+1))
            except:
                value = 0
            values.append(value)

        return values

    def write(self,output,timestamp,config):

        version = 0x01

        pins = self.encodeDIO(config,'GPIO')
        sensors = self.encodeSensors(config,'sensors')

        output.write(struct.pack('!B',version))
        output.write(struct.pack('!i',timestamp))
        output.write(struct.pack('!B',SECTION_GPIO))
        output.write(struct.pack('!H',pins))
        output.write(struct.pack('!B',SECTION_SENSORS))
        output.write(struct.pack('!%df' % len(sensors),*sensors))
        output.write(struct.pack('!B',SECTION_END))


