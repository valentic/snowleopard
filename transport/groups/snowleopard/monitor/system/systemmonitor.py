#!/usr/bin/env python

##################################################################
#
#   Post system health status messages.
#
#   2009-07-28  Todd Valentic
#               Initial implementation.
#
#   2009-09-04  Todd Valentic
#               Updated to use DataMonitor
#
#   2010-09-22  Todd Valentic
#               Include version information
#
#   2013-03-04  Todd Valentic
#               Migrated to use DataMonitorComponent
#
##################################################################

from DataMonitor import DataMonitorComponent

import commands
import tarfile

class SystemMonitor (DataMonitorComponent):

    def __init__(self,*pos,**kw):
        DataMonitorComponent.__init__(self,*pos,**kw)

        self.versions  = '[Versions]\n'
        self.versions += 'release.version: %s\n' % self.get('release.version')
        self.versions += 'release.date: %s\n' % self.get('release.date')

    def sample(self):
        status,output = commands.getstatusoutput('systemstatus.py')

        output += self.versions

        if status!=0:
            raise IOError(output)

        return output

