#!/usr/bin/env python

##################################################################
#
#   SunSaver monitor
#
#   2016-07-05  Todd Valentic
#               Initial implementation.
#
##################################################################

from DataMonitor import DataMonitor

from sunsaver import SunSaver

import sys

class Sampler (DataMonitor):

    def __init__(self,argv):
        DataMonitor.__init__(self,argv)
        self.cache = self.connect('cache')
        self.device = self.get('sunsaver.device','/dev/ttyS0')
        self.sunsaver = SunSaver(self.device)

    def sample(self):
        self.log.info('Reading SunSaver')
        results = self.sunsaver.sample()
        self.cache.put('sunsaver',results)
        return results 

    def write(self,output,timestamp,data):
        self.sunsaver.write(output,timestamp,data)

if __name__ == '__main__':
    Sampler(sys.argv).run()

