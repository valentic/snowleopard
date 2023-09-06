#!/usr/bin/env python

import serial
import sys
import time
import commands
import os
import datetime
import md5
import select

def send(port,cmd,expect='OK'):

    port.write(cmd+'\r')
    response=''

    while True:
        line = port.readline()
        print line.strip()
        if expect in line:
            break
        if 'NO CARRIER' in line:
            raise IOError

def CreateLock(filename):
    lock = open(filename,'w')
    lock.write(str(os.getpid()))
    lock.close()

def RemoveLock(filename):
    os.remove(filename)

def SendFile(filename):

    device = '/dev/ttyS0'
    lockfile = '/tmp/LCK..ttyS0'

    CreateLock(lockfile)

    baudrate=19200
    timeout=120

    port = serial.Serial(device,baudrate,rtscts=1,
                        stopbits=2,
                        timeout=timeout,writeTimeout=timeout)

    port.flushInput()

    print 'Toggling DTR'
    port.setDTR(0)
    time.sleep(10)
    port.setDTR(1)

    print 'Sending init strings'
    send(port,'AT')
    send(port,'ATZ0')
    send(port,'AT+CBST=71,0,1')

    print 'Dialing'
    send(port,'ATDT 0088160000500',expect='RUDICS Bridge')

    print 'Writing file to modem'
    start = time.time()
    data = open(filename).read()
    frame = data+'END'

    ready = True

    poller = select.poll()
    poller.register(port,select.POLLOUT)

    blocksize=128
    bytessent=0
    waittime=1

    while frame and port.getCD():
        for fd,flags in poller.poll():
            if flags & select.POLLOUT:
                port.write(frame[:blocksize])
                bytessent+=len(frame[:blocksize])
                frame=frame[blocksize:]
                print bytessent,'/',len(frame)
                if waittime:
                    time.sleep(waittime)

    print 'Flushing output buffer'
    port.drainOutput()

    stop = time.time()

    time.sleep(15)

    print 'Hanging up'
    port.setDTR(0)

    elapsed = stop-start
    filesize = len(data)
    rate = filesize/elapsed
    checksum = md5.new(data)

    print 'Elapsed time: %s secs' % datetime.timedelta(seconds=elapsed)
    print 'Total bytes : %d' % filesize
    print 'Rate        : %d Bps (%d bps)' % (rate,rate*8)
    print 'Checksum    : %s' % checksum.hexdigest()

    RemoveLock(lockfile)

    print 'Finished'

if __name__ == '__main__':
    filename = sys.argv[1]
    SendFile(filename)
