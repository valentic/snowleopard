#!/usr/bin/env python

##################################################################
#
#   Iridium data transfer
#
#   2009-11-06  Todd Valentic
#               Initial implementation.
#
#   2009-11-08  Todd Valentic
#               Added update handling.
#
#   2009-11-10  Todd Valentic
#               Remove keepalive flag at start
#               Hangup modem after transfer
#
#   2009-11-11  Todd Valentic
#               Use setResources/clearResources
#
#   2009-11-14  Todd Valentic
#               Run with higher clock speed during transfers
#
#   2009-11-17  Todd Valentic
#               Throttle clock speed back down (not needed)
#               Package transport log files.
#
#   2010-03-04  Todd Valentic
#               Revert clock speed change. Running at 42MHz
#                   limits transfers to 500bps. At 200MHz, we
#                   get 1500bps.
#
#   2010-03-19  Todd Valentic
#               checkrate and startwait were swapped
#
#   2011-08-17  Todd Valentic
#               Use DayNightDataMonitor
#
##################################################################

from DayNightDataMonitor import DayNightDataMonitor

import os
import sys
import shutil
import datetime
import commands

class Transfer(DayNightDataMonitor):

    def __init__(self,argv):
        DayNightDataMonitor.__init__(self,argv)

        self.exchange       = self.connect('exchange')
        self.modem          = self.connect('modem')

        self.keepaliveFlag  = self.get('keepalive.flag')
        self.updateFlag     = self.get('update.flag')

        self.checkrate      = self.getDeltaTime('checkrate',60)
        self.startwait      = self.getDeltaTime('startwait',60)

        self.logsdest       = self.get('logs.outbound')
        self.logssrc        = self.get('logs.src','/opt/transport/log')

    def saveLogs(self):

        if not self.logsdest:
            return

        destfile = self.currentTime().strftime(self.logsdest)
        destpath = os.path.dirname(destfile)
        if not os.path.exists(destpath):
            os.makedirs(destpath)

        cmd = 'tar jcvf %s %s' % (destfile,self.logssrc)

        status,output = commands.getstatusoutput(cmd)

        if status!=0:
            self.log.error('Failed to save logs:')
            self.log.error('  cmd   : %s' % cmd)
            self.log.error('  status: %s' % status)
            self.log.error('  output: %s' % output)

    def sample(self):

        try:
            if os.path.isdir(self.keepaliveFlag):
                shutil.rmtree(self.keepaliveFlag)
            elif os.path.isfile(self.keepaliveFlag):
                os.remove(self.keepaliveFlag)
        except:
            self.log.exception('Problem remove keepalive flag')

        try:
            self.saveLogs()
        except:
            self.log.exception('Problem saving log files')

        self.setResources('pc104=on','iridium=on','cpu=max')
        self.wait(self.startwait)

        try:
            self.sendData()
            self.checkUpdates()
        finally:
            if not os.path.exists(self.keepaliveFlag):
                self.clearResources()

        return None

    def sendData(self):

        self.log.info('Starting file exchange')

        startTime = self.currentTime()

        self.exchange.start()

        while self.exchange.busy():
            self.wait(self.checkrate)

        self.log.info('  finished: %s' % (self.currentTime()-startTime))

        self.log.info('Hanging up modem')
        try:
            self.modem.hangup()
        except:
            self.log.exception('Failed to handup modem')

    def checkUpdates(self):

        if os.path.exists(self.updateFlag):
            self.log.info('Updates found')
            commands.getstatusoutput('chmod 777 %s' % self.updateFlag)
            status,output = commands.getstatusoutput(self.updateFlag)
            self.log.info('  command: %s' % self.updateFlag)
            self.log.info('  status:  %s' % status)
            self.log.info('  output:  %s' % output)
            os.remove(self.updateFlag)

if __name__ == '__main__':
    Transfer(sys.argv).run()

