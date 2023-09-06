#!/usr/bin/env python

###################################################################
#
#   GPS Data Monitor
#
#   2009-11-05  Todd Valentic
#               Initial implementation
#
#   2009-11-11  Todd Valentic
#               Use setResources/clearResources
#
#   2009-11-16  Todd Valentic
#               Use new GPS function names
#
#   2009-11-17  Todd Valentic
#               Added powerup.timeout to wait for valid GPS
#                   data at start
#
#   2009-11-19  Todd Valentic
#               Move gps port open/close to match powering
#                   up of device.
#
#   2010-01-22  Todd Valentic
#               Use getStatus()
#
#   2010-03-17  Todd Valentic
#               Remove isOn() check (use default of True) since
#                   we control power during sample routine.
#
#   2010-03-23  Todd Valentic
#               Send setup commands to GPS at power up. We have
#                   seen cases where the GPS forgets its setup
#                   after being powered off for long periods of
#                   time. This change ensures that the reporting
#                   commands are sent.
#
#   2011-04-04  Todd Valentic
#               Add ability to force the setting of the GPS
#                   position at startup.
#
#   2011-04-05  Todd Valentic
#               Fix problem in update() - was only using force data
#
#   2013-05-11  Todd Valentic
#               Replace dio1[7]=off -> gps=on
#
#   2016-07-13  Todd Valentic
#               Add Ettus GPSDO support
#
###################################################################

from DataMonitor import DataMonitor
from pack import packFloat

import sys
import gps
import struct

class GPSMonitor(DataMonitor):

    def __init__(self,argv):
        DataMonitor.__init__(self,argv)

        self.cache  = self.connect('cache')

        self.powerupDelay = self.getDeltaTime('powerup.delay','1:00')
        self.powerupTimeout = self.getDeltaTime('powerup.timeout','5:00')
        self.sharedfile = self.get('current.gps')

        self.device = self.get('device')
        self.baudrate = self.get('baudrate',19200)
        self.gps = None

        self.force  = self.getboolean('force',False)

        self.forceData = {}
        self.forceData['latitude']  = self.getfloat('force.latitude',0)
        self.forceData['longitude'] = self.getfloat('force.longitude',0)
        self.forceData['speed']     = self.getfloat('force.speed',0)
        self.forceData['heading']   = self.getfloat('force.heading',0)
        self.forceData['pitch']     = self.getfloat('force.pitch',0)
        self.forceData['roll']      = self.getfloat('force.roll',0)

        now = self.currentTime()

        self.forceData['timestamp'] = [now.year,now.month,now.day,
                                       now.hour,now.minute,now.second]


    def update(self,data):
        self.cache.put('gps',data)
        if self.sharedfile:
            open(self.sharedfile,'w').write(gps.format(data))

    def startup(self):
        self.powerDown()

        if self.force:
            self.log.info('Forcing GPS position')
            self.update(self.forceData)

    def sample(self):
        data = None
        try:
            self.powerUp()
            data = self.collectData()
            self.update(data)
        finally:
            self.powerDown()
        return data

    def powerUp(self):
        self.setResources('ettus=on')
        self.wait(self.powerupDelay)
        self.gps = gps.GPS(self.device,self.baudrate)
        self.gps.setup()

    def collectData(self):

        timeout = self.currentTime() + self.powerupTimeout

        while self.running:

            if self.currentTime() > timeout:
                raise IOError('No valid GPS data')

            try:
                data = self.gps.getSuite()
                break
            except:
                pass

        self.log.info('Setting clock')
        self.log.info(self.gps.setClock())

        return data

    def powerDown(self):
        if self.gps:
            self.gps.close()
            self.gps = None
        self.clearResources()

    def write(self,output,timestamp,data):

        output.write(struct.pack('!i',timestamp))
        output.write(packFloat(data['latitude']))
        output.write(packFloat(data['longitude']))
        output.write(packFloat(data['speed']))
        output.write(packFloat(data['heading']))
        output.write(packFloat(data['pitch']))
        output.write(packFloat(data['roll']))

if __name__ == '__main__':
    GPSMonitor(sys.argv).run()
