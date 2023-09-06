#!/usr/bin/env python

###################################################################
#
#   Fan Control
#
#   2016-07-14  Todd Valentic
#               Initial implementation
#
###################################################################

from DataMonitor import DataMonitor
from pack import packFloat

import sys
import sunsaver
import md5

class FanMonitor(DataMonitor):

    def __init__(self,argv):
        DataMonitor.__init__(self,argv)

        self.cache  = self.connect('cache')

        self.curState = None

    def getParameters(self,schedule):

        # Defaults from transport config

        onTemperature  = self.getfloat('tmperature.on',35)
        offTemperature = self.getfloat('temperature.off',30)

        # Override from schedule file

        self.onTemperature = schedule.getfloat('temperature.on',onTemperature)
        self.offTemperature = schedule.getfloat('temperature.off',offTemperature)

    def sample(self):

        self.getParameters(self.curSchedule)

        try:
            data = sunsaver.Parse(self.cache.get('sunsaver'))
        except:
            self.log.info('No valid SunSaver data')
            return None

        Tamb = float(data['T_amb'])

        if Tamb<=self.offTemperature:
            self.setResources('fan=off')
            nextState = 'off'
        elif Tamb>=self.onTemperature:
            self.setResources('fan=on')
            nextState = 'on'
        else:   
            nextState = self.curState

        if nextState != self.curState:
            self.log.info('Turning fan %s to %s' % (self.curState,nextState))
            self.curState = nextState

        return None

if __name__ == '__main__':
    FanMonitor(sys.argv).run()

