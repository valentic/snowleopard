#!/usr/bin/env python

###################################################################
#
#   Iridium modem
#
#   A set of classes encapsulating the Iridium modem interface.
#   For testing RUDICS, thisis a simulated version that directly
#   connects to the remote port.
#
#   2007-12-16  Todd Valentic
#               Initial implementation
#
#   2008-04-08  Todd Valentic
#               Release lockfile on failed dialup.
#
#   2008-05-31  Todd Valentic
#               Add try..except in isConnected.
#
#   2008-08-10  Todd Valentic
#               Make sure lockfile is released on getStats.
#
#   2009-09-15  Todd Valentic
#               Rewrite modem file locking to avoid race conditions.
#               See this mailing list post:
#               http://groups.google.com/group/comp.lang.python/msg/5d678c60b5db54d0
#
#   2009-10-27  Todd Valentic
#               Remove autoflow
#               Add stopbits option
#               Fix typos in log messages
#
#   2014-06-09  Todd Valentic
#               Handle transition to new epoch 14:23:55.00 UTC 11 May 2014
#
#   2014-06-30  Todd Valentic
#               Fix lat/lon swap introduced in last update.
#               Handle new change in Iridium epoch rollover.
#
###################################################################

from Transport      import AccessMixin
from Transport.Util import datefunc
from datetime       import datetime,timedelta

import serial
import socket
import math
import os
import select
import commands
import time
import errno

class LockFile:

    def __init__(self,path,log):
        self.path   = path
        self.pid    = os.getpid()
        self.log    = log

        self.log.info('LockFile')

    def acquire(self):

        self.log.info('Trying to acquire lock')

        retry=0
        maxRetries=10

        while True:

            try:
                fd = os.open(self.path,os.O_EXCL | os.O_RDWR | os.O_CREAT)
                # we created the file, so we own it
                self.log.info('  - lock file created')
                break
            except OSError,e:
                if e.errno != errno.EEXIST:
                    self.log.exception('Error creating lock!')
                    # should not occur
                    raise

                self.log.info('  - lock file alreay exists')

                try:
                    # the lock file exists, try to read the pid to see if it is ours
                    f = open(self.path,'r')
                    self.log.info('  - opened lock file')
                except OSERROR, e:
                    self.log.exception('Failed to open lock file!')
                    if e.errno != errno.ENOENT:
                        self.log.error('not ENOENT, aborting')
                        raise
                    # The file went away, try again
                    if retry<maxRetries:
                        retry+=1
                        self.log.info('  - trying again, retry: %d' % retry)
                        time.sleep(1)
                        continue
                    else:
                        self.log.info('  - max retries, return false')
                        return False

                # Check if the pid is ours

                self.log.info('  - checking pid')

                pid = int(f.readline())
                f.close()

                self.log.info('  - pid=%d, ours=%d' % (pid,self.pid))

                if pid==self.pid:
                    # it's ours, we are done
                    self.log.info('  - we own this file, return true')
                    return True

                self.log.info('  - not ours')

                # It's not ours, see if the PID exists
                try:
                    os.kill(pid,0)
                    self.log.info('  - owner pid still exists, return false')
                    # PID is still active, this is somebody's lock file
                    return False
                except OSError,e:
                    if e.errno!=errno.ESRCH:
                        self.log.info('  - owner still exists, return false')
                        # PID is still active, this is somebody's lock file
                        return False

                self.log.info('  - owner is not running anymore')

                # The original process is gone. Try to remove.
                try:
                    os.remove(self.path)
                    time.sleep(5)
                    # It worked, must have been ours. Try again.
                    self.log.info('  - removed lock file. try again')
                    continue
                except:
                    self.log.info('  - failed to remove. return false')
                    return False

        # If we get here, we have the lock file. Record our PID.

        self.log.info('  - record pid in file')

        fh = os.fdopen(fd,'w')
        fh.write('%10d\n' % self.pid)
        fh.close()

        self.log.info('  - lock acquired!')

        return True

    def release(self):
        if self.ownlock():
            os.unlink(self.path)

    def _readlock(self):
        try:
            return int(open(self.path).readline())
        except:
            return 8**10

    def isLocked(self):
        try:
            pid = self._readlock()
            os.kill(pid,0)
            return True
        except:
            return False

    def ownlock(self):
        pid = self._readlock()
        return pid==self.pid

    def __del__(self):
        self.release()


class IridiumBase(AccessMixin):

    def __init__(self,parent):
        AccessMixin.__init__(self,parent)

        self.online=False

    def fileno(self):
        pass

    def write(self,data):
        pass

    def read(self,num=None):
        pass

    def dialup(self):
        pass

    def hangup(self):
        pass

    def isConnected(self):
        return self.online

    def flush(self):
        pass

    def getStats(self):
        pass

    def sendSBD(self,message):
        pass

class Iridium(IridiumBase):

    def __init__(self,*pos,**kw):
        IridiumBase.__init__(self,*pos,**kw)

        self.phoneNumber = self.get('phoneNumber','0088160000500')
        self.connectTimeout = self.getDeltaTime('modem.timeout.connect',30)

        device          = self.get('device','/dev/ttyS0')
        lockpath        = self.get('lockfile','/var/lock/LCK..S0')
        baudrate        = self.getint('baudrate',9600)
        stopbits        = self.getint('stopbits',2)
        writeTimeout    = self.getDeltaTime('timeout.write',15)
        readTimeout     = self.getDeltaTime('timeout.read',15)

        writeTimeout    = datefunc.timedelta_as_seconds(writeTimeout)
        readTimeout     = datefunc.timedelta_as_seconds(readTimeout)

        self.log.info('Lock file: %s' % lockpath)
        self.log.info('Baud rate: %s' % baudrate)
        self.log.info('Timeout (write): %s secs' % writeTimeout)
        self.log.info('Timeout (read) : %s secs' % readTimeout)

        self.lockfile   = LockFile(lockpath,self.log)

        # Use mgetty compatible locks. Need to assign device
        # separately to keep port from opening here.

        self.port = serial.Serial(baudrate=baudrate,
                                  rtscts=True,
                                  stopbits=stopbits,
                                  timeout=readTimeout,
                                  writeTimeout=writeTimeout)

        self.port.port = device

    def fileno(self):
        return self.port.fileno()

    def close(self):
        self.log.info('Serial port closed')
        self.port.close()

    def open(self):
        self.port.open()
        self.log.info('Serial port opened')
        self.port.flushInput()
        self.port.flushOutput()
        self.reset()

    def write(self,data):
        return self.port.write(data)

    def read(self,num=None):
        if num is None:
            num = self.port.inWaiting()
        return self.port.read(num)

    def send(self,cmd,expect='OK',reject='NO CARRIER',timeout=5):
        self.log.info('Sending: %s',cmd.strip())
        self.write(cmd+'\r')

        response=''
        if isinstance(timeout,int):
            timeout=timedelta(seconds=timeout)
        endtime = datetime.now()+timeout

        poller = select.poll()
        poller.register(self.port.fd,select.POLLIN)

        while True:

            events = poller.poll(1000)

            if events:
                response+=self.read(1)
                output = response.replace('\r','<CR>').replace('\n','<NL>')
                self.log.debug(' response: "%s"' % output)

            if response.strip().endswith(expect):
                self.log.debug('  found')
                return response
            if reject and response.strip().endswith(reject):
                raise IOError('reject found')
            if datetime.now()>endtime:
                self.log.error('Timeout on "%s"' % cmd.replace('\r','<CR>'))
                raise IOError('timeout')

    def dialup(self):

        if not self.lockfile.acquire():
            raise IOError('Serial port is locked')

        retry=0
        startTime = datetime.now()

        while retry<2:
            self.open()
            self.log.info('Attempt %s' % (retry+1))
            try:
                self.connect()
                elapsedTime = datetime.now()-startTime
                self.log.info('Connected in %s' % elapsedTime)
                return True
            except IOError:
                self.close()
                retry+=1

        self.online = False

        self.lockfile.release()
        self.log.info('Released lockfile')
        raise IOError('Failed to connect')

    def reset(self):
        self.log.info('  resetting modem')
        self.toggleDTR()

        self.port.write('\r')
        self.wait(1)
        self.send('AT')
        self.send('ATZ0')
        self.send('AT+CBST=71,0,1')

    def toggleDTR(self,delay=10):
        self.port.setDTR(0)
        self.log.info('DTR low')
        time.sleep(delay)   # don't use wait() - called on exit
        self.port.setDTR(1)
        self.log.info('DTR high')
        self.online=False

    def hangup(self):

        self.log.info('Hangup')

        if not self.lockfile.acquire():
            raise IOError('Serial port is locked')

        self.close()
        self.log.info('opening port')
        self.port.open()
        self.log.info('toggling DTR')
        self.toggleDTR(1)
        self.close()

        self.log.info('  releasing lock file')
        self.lockfile.release()

        self.log.info('  hangup finished')

        return True

    def flush(self):
        self.port.flushInput()
        self.port.flushOutput()

    def connect(self):

        self.log.info('Dialing')
        self.flush()

        self.send('ATDT %s' % self.phoneNumber,'Open',
            timeout=self.connectTimeout)

        self.online = True

    def isConnected(self):
        try:
            return self.online and self.port.getCD()
        except:
            return False

    def getTime(self):

        # Note: Iridium time is determined by a base epoch + the number of seconds.
        # Only the seconds are returned by the time commands. The epoch is assumed
        # and it is occasionally reset about every 7-years. The original epoch was
        # 03:50:21.00 UTC 08 Mar 2007 and in June, 2014, it shifted to be
        # 14:23:55.00 UTC 11 May 2014. We need to detect these changes and adjust
        # the epoch. For now, this is done simply by looking at the seconds count
        # during the transition time. After the transition, we need to lock down
        # the code to the current epoch.
        #
        # On June 30, 2014, Iridium decided to revert the epoch change and delay
        # it until Q1 2015. Modify the code here to test the seconds count and
        # use epoch 1 if the count more then 10 years.

        tenYears = 60*60*24*365*10

        results = self.send('AT-MSSTM')
        for line in results.split('\r\n'):
            if line.startswith('-MSSTM:'):
                timestamp = int(line.split(':')[1].strip(),16)
                secs = timestamp*90e-3

                if secs>tenYears:
                    era = datetime(2007,3,8,3,50,21)   # 03:50:21.00 UTC 08 Mar 2007
                else:
                    era = datetime(2014,5,11,14,23,55) # 14:23:55.00 UTC 11 May 2014

                return era+timedelta(seconds=secs)

        raise IOError('Failed to get time')

    def getPosition(self):
        results = self.send('AT-MSGEO')
        for line in results.split('\r\n'):
            if line.startswith('-MSGEO'):
                x,y,z = [int(n) for n in line.split(':')[1].split(',')[0:3]]
                r = math.sqrt(x*x+y*y)
                longitude = math.atan2(y,x)*180/math.pi
                latitude  = math.atan2(z,r)*180/math.pi
                return latitude,longitude

        raise IOError('Failed to find position')

    def getSignal(self):
        results = self.send('AT+CSQ',timeout=10)
        for line in results.split('\r\n'):
            if line.startswith('+CSQ'):
                signal=int(line.split(':')[1].strip())
                return signal

        raise IOError('Failed to read signal')

    def getStats(self):
        try:
            return self._getStats()
        except:
            self.lockfile.release()
            self.log.exception('Problem in getStats')
            raise

    def _getStats(self):

        # Need to make sure lock file is released on failure...

        if self.isConnected():
            self.hangup()

        if not self.lockfile.acquire():
            raise IOError('Serial port is locked')
        self.open()

        lat,lon = self.getPosition()

        results = { 'version':  2,
                    'time':     str(self.getTime()),
                    'latitude': lat,
                    'longitude':lon,
                    'signal':   self.getSignal()
                    }

        self.close()
        self.lockfile.release()

        return results

    def sendSBD(self,message):
        try:
            return self._sendSBD(message)
        except:
            self.lockfile.release()
            self.log.exception('Problem in sendSBD')
            raise

    def _sendSBD(self,message):

        # Need to make sure lock file is released on failure...

        if self.isConnected():
            self.hangup()

        if not self.lockfile.acquire():
            raise IOError('Serial port is locked')
        self.open()

        self.send('AT')
        self.send('AT+SBDWT=%s'%message)
        results = self.send('AT+SBDI',timeout=60)

        self.close()
        self.lockfile.release()

        return results


class SimulatedIridium(IridiumBase):

    def __init__(self,*pos,**kw):
        IridiumBase.__init__(self,*pos,**kw)

        self.port       = self.getint('simulate.port',9080)
        self.host       = self.get('simulate.host','transport.sri.com')
        self.bytesPerSec= self.getint('simulate.bytesPerSec',180)
        self.timeout    = self.getDeltaTime('modem.timeout.read',3)
        self.timeout    = datefunc.timedelta_as_seconds(self.timeout)
        self.socket     = None

        self.log.info('Simulating Iridium')

    def fileno(self):
        return self.socket.fileno()

    def delay(self,numBytes):
        # We are getting about 180 bytes/s on the link
        secs = numBytes/self.bytesPerSec
        self.wait(secs)

    def write(self,data):
        self.delay(len(data))
        return self.socket.sendall(data)

    def read(self):
        data = self.socket.recv(1024)
        self.delay(len(data))
        return data

    def dialup(self):
        self.log.info('Dialup (connection to %s:%s)' % (self.host,self.port))
        self.socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        self.socket.connect((self.host,self.port))
        self.online=True

    def hangup(self):
        self.log.info('Hangup')
        if self.socket:
            self.socket.close()
            self.socket=None
        self.online=False

    def getPosition(self):
        return -123,38

    def getTime(self):
        return datetime.now()

    def getSignal(self):
        return 5

    def getStats(self):

        if self.isConnected():
            self.hangup()

        lat,lon = self.getPosition()

        return {'version':  2,
                'time':     str(self.getTime()),
                'latitude': lat,
                'longitude':lon,
                'signal':   self.getSignal()
                }


