#!/usr/bin/env python

###################################################################
#
#   WXT520 Weather Station Monitor
#
#   2011-05-09  Todd Valentic
#               Initial implementation
#
#   2013-03-04  Todd Valentic
#               Migrate to DataMonitorComponent
#               Power on PC104 stack
#
#   2016-07-14  Todd Valentic
#               Adjust resouces for SnowLeopard systems
#
###################################################################

from DataMonitor import DataMonitorComponent
from pack import packFloat

import wxt520
import struct

class WXT520Monitor(DataMonitorComponent):

    def __init__(self,*pos,**kw):
        DataMonitorComponent.__init__(self,*pos,**kw)

        self.cache  = self.connect('cache')

        self.powerupDelay   = self.getDeltaTime('powerup.delay','1:00')
        self.powerupTimeout = self.getDeltaTime('powerup.timeout','5:00')
        self.device         = self.get('device')

        self.wxt520 = None

    def sample(self):
        self.setResources()
        self.wxt520.port.flushInput()
        self.wxt520.port.flushOutput()
        data = self.wxt520.values()
        self.setResources()
        return data

    def startup(self):
        self.setResources()
        self.wait(self.powerupDelay)
        self.wxt520 = wxt520.WXT520(self.device)
        try:
            data = self.wxt520.values()
        except:
            self.log.error('Problem in startup')
        self.log.info('startup complete')
        self.setResources('')

    def write(self,output,timestamp,data):

        version = 0x01      # Increment when format changes

        output.write(struct.pack('!B',version))
        output.write(struct.pack('!i',timestamp))
        output.write(packFloat(data['Dn']))
        output.write(packFloat(data['Dm']))
        output.write(packFloat(data['Dx']))
        output.write(packFloat(data['Sn']))
        output.write(packFloat(data['Sm']))
        output.write(packFloat(data['Sx']))
        output.write(packFloat(data['Ta']))
        output.write(packFloat(data['Ua']))
        output.write(packFloat(data['Pa']))
        output.write(packFloat(data['Rc']))
        output.write(packFloat(data['Rd']))
        output.write(packFloat(data['Ri']))
        output.write(packFloat(data['Hc']))
        output.write(packFloat(data['Hd']))
        output.write(packFloat(data['Hi']))
        output.write(packFloat(data['Rp']))
        output.write(packFloat(data['Hp']))
        output.write(packFloat(data['Th']))
        output.write(packFloat(data['Vh']))
        output.write(packFloat(data['Vs']))
        output.write(packFloat(data['Vr']))

