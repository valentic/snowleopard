#!/usr/bin/env python

##################################################################
#
#   Take webcam pictures
#
#   2009-09-18  Todd Valentic
#               Initial implementation.
#
#   2009-11-08  Todd Valentic
#               Correctly allocate resources.
#
#   2009-11-11  Todd Valentic
#               Use new setResources/clearResources
#               Put intermediate image in /tmp/share
#               Remove uvc modules before turning off USB bus
#
#   2011-09-02  Todd Valentic
#               Add ability to set UVC controls via yavta.
#                   The control values are unique to cameras,
#                   so we just pass through the config entry.
#               Remove tmpname before taking picture.
#
#   2011-09-11  Todd Valentic
#               Convert to DayNightDataMonitor
#
#   2012-02-15  Todd Valentic
#               Add skip parameter
#               Add fps parameter
#               Allow override of camera parameters from schedule
#
#   2013-03-04  Todd Valentic
#               Use component class
#
#   2016-07-18  Todd Valentic
#               SnowLeopard verion - remove setResources() from
#                   TS7260 version.
#
##################################################################

from DayNightDataMonitor import DayNightDataMonitorComponent

import os
import commands

class CameraMonitor(DayNightDataMonitorComponent):

    def __init__(self,*pos,**kw):
        DayNightDataMonitorComponent.__init__(self,*pos,**kw)

        self.tmpname = '/tmp/%s.jpg' % self.name

    def getParameters(self):

        schedule = self.curSchedule

        # Defaults from transport config file

        device      = self.get('camera.device','/dev/video0')
        resolution  = self.get('camera.resolution','800x600')
        frames      = self.getint('camera.frames',1)
        skip        = self.getint('camera.skip',60)
        jpegLevel   = self.getint('camera.jpeg.level',80)
        delay       = self.getint('camera.delay',5)
        fps         = self.getint('camera.fps',5)
        controls    = self.get('camera.controls','')

        # Override from schedule

        self.device     = schedule.get('camera.device',device)
        self.resolution = schedule.get('camera.resolution',resolution)
        self.frames     = schedule.getint('camera.frames',frames)
        self.skip       = schedule.getint('camera.skip',skip)
        self.jpegLevel  = schedule.getint('camera.jpeg.level',jpegLevel)
        self.delay      = schedule.getint('camera.delay',delay)
        self.fps        = schedule.getint('camera.fps',fps)
        self.controls   = schedule.getList('camera.controls',controls)

    def sample(self):

        self.setResources()

        self.wait(10)

        try:
            return self.takePicture()
        finally:
            self.wait(5)
            self.clearResources()

    def setControls(self):

        for control in self.controls:
            control = control.replace('=',' ')
            cmd = ['yavta']
            cmd.append(self.device)
            cmd.append('-w "%s"' % control.replace('=',' '))

            cmd = ' '.join(cmd)

            status,output = commands.getstatusoutput(cmd)

            if status!=0:
                self.log.error('Failed to set control:')
                self.log.error('  cmd=%s'    % cmd)
                self.log.error('  status=%s' % status)
                self.log.error('  output=%s' % output)
                raise IOError

    def takePicture(self):

        self.getParameters()
        self.setControls()

        if os.path.exists(self.tmpname):
            os.remove(self.tmpname)

        cmd = ['fswebcam']
        cmd.append('-d %s' % self.device)
        cmd.append('-D %s' % self.delay)
        cmd.append('-S %s' % self.skip)
        cmd.append('-F %s' % self.frames)
        cmd.append('-r %s' % self.resolution)
        cmd.append('--fps %s' % self.fps)
        cmd.append('--no-banner')
        cmd.append('--jpeg %s' % self.jpegLevel)
        cmd.append('--save %s' % self.tmpname)

        cmd = ' '.join(cmd)

        self.log.debug(cmd)

        status,output = commands.getstatusoutput(cmd)

        if status!=0:
            self.log.error('Failed to take picture:')
            self.log.error('  cmd=%s'    % cmd)
            self.log.error('  status=%s' % status)
            self.log.error('  output=%s' % output)
            raise IOError

        self.log.info('Took a picture')

        return open(self.tmpname).read()


