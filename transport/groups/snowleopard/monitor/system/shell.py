#!/usr/bin/env python

####################################################################
#
#   Data monitor shell
#
#   2013-03-04  Todd Valentic
#               Initial implementation
#
####################################################################

import sys

from Transport          import ProcessClient

from systemmonitor      import SystemMonitor
from schedulemonitor    import ScheduleMonitor
from watchdogmonitor    import WatchdogMonitor
from sbcmonitor         import SBCMonitor
from wxt520monitor      import WXT520Monitor

class DataMonitorShell(ProcessClient):

    def __init__(self,argv):
        ProcessClient.__init__(self,argv)

        self.monitors = self.getComponents('monitors',self.monitorFactory)

    def monitorFactory(self,name,parent,**kw):

        id = self.get('monitor.%s.type'%name,self.get('monitor.*.type'))

        self.log.info('creating monitor: %s (%s)' % (id,name))

        map = {
            'system':   SystemMonitor,
            'schedule': ScheduleMonitor,
            'watchdog': WatchdogMonitor,
            'sbc':      SBCMonitor,
            'wxt520':   WXT520Monitor
            }

        if id in map:
            return map[id](name,parent,**kw)
        else:
            raise ValueError('Unknown monitor: %s' % id)

    def run(self):

        steppers = [monitor.step() for monitor in self.monitors]

        while self.wait(60,sync=True):

            for stepper in steppers:
                try:
                    stepper.next()
                except StopIteration:
                    pass


if __name__ == '__main__':
    DataMonitorShell(sys.argv).run()

