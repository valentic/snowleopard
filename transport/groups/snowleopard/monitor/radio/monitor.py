#!/usr/bin/env python

###########################################################
#
#   USRP Monitor Service
#
#   Collect data samples from radio
#
#   2016-07-15  Todd Valentic
#               Initial implementation.
#
#   2016-08-12  Todd Valentic
#               Switch to DayNight monitor class. Turn
#                   off radio after sampling in night.
#
#   2016-08-18  Todd Valentic
#               Add sequence of param files
#
###########################################################

from DayNightDataMonitor import DayNightDataMonitor
from Transport.Util import datefunc

import sys
import os

class RadioMonitor(DayNightDataMonitor):

    def __init__(self,args):
        DayNightDataMonitor.__init__(self,args)

        self.fileTemplate   = self.get('output.file','test.dat')
        self.paramPath      = self.get('scripts.param.path','.')
        self.paramFile      = self.get('scripts.param','radio.conf')

        self.seqNum=0

    def isRadioOn(self):
        status = self.getStatus()
        return status.getint('Device','ettus')==1

    def turnRadioOn(self):
        self.setResources('ettus=on','lna=on')
        self.wait(20)

    def turnRadioOff(self):
        self.clearResources()

    def getParameters(self):

        schedule = self.curSchedule

        # Defaults from transport config file

        paramFiles = self.get('sequence',self.paramFile)

        # Override from schedule

        paramFiles = schedule.getList('sequence',paramFiles)

        self.log.info('raw sequence: %s' % paramFiles)

        self.paramFiles = []

        for filename in self.paramFiles:
            filename = os.path.join(self.paramPath,filename)
            self.paramFiles.append(filename)

    def sample(self):

        self.getParameters()

        if not self.paramFiles:
            self.log.info('No sequence listed')
            return None

        if self.seqNum>=len(self.paramFiles):
            self.seqNum=0

        paramFile = self.paramFiles[self.seqNum]

        self.log.info('Param file: [%d] %s' % (self.seqNum,paramFile))

        self.seqNum+=1

        if not self.isRadioOn():
            self.turnRadioOn()

        filename = self.currentTime().strftime(self.fileTemplate)

        # store samples into a temporary name to avoid getting
        # picked up by the monitor/backup program.

        tmpname = filename+'.new'
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        cmd = 'collect %s %s' % (self.paramFile,tmpname)

        self.runScript(cmd)

        if os.path.exists(tmpname):
            os.rename(tmpname,filename)

        if self.reportState=='night':
            self.turnRadioOff()

        self.log.info('Done collecting sample')

        return None

if __name__ == '__main__':
    RadioMonitor(sys.argv).run()
