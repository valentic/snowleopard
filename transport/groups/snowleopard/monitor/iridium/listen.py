#!/usr/bin/env python

##################################################################
#
#   Periodically power up the Iridium mode to give us a chance
#   to remotely login in the case of trouble.
#
#   2016-08-12  Todd Valentic
#               Initial implementation.
#
##################################################################

from DataMonitor import DataMonitor

import sys

class Monitor(DataMonitor):

    def sample(self):

        holdtime = self.curSchedule.getRate('holdtime',60)

        self.log.info('Turning on Iridium modem')

        self.setResources('iridium=on')
        self.wait(holdtime)
        self.clearResources()

        self.log.info('Turning off Iridium modem')

        return None

if __name__ == '__main__':
    Monitor(sys.argv).run()

