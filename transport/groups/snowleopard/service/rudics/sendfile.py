#!/usr/bin/env python

import sys
import time
import datetime
import socket
import md5
import select

FlagDesc = {
    1:  'POLLIN',
    2:  'POLLPRI',
    4:  'POLLOUT',
    8:  'POLLERR',
    16: 'POLLHUP',
    32: 'POLLNVAL',
    64: 'POLLRDNORM',
    128:'POLLRDBAND',
    256:'POLLWRNORM',
    1024:'POLLMSG'
    }

def PrintFlags(flags):
    print 'Flags:'
    for bit in range(0,11):
        n=2**bit
        if flags&n:
            print '  %s' % FlagDesc[n]

def SendFile(filename):

    print "Connecting to proxy service"

    proxy = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    proxy.connect(('',9001))

    print 'Writing file to proxy'
    start = time.time()
    output = open(filename).read()
    checksum = md5.new(output)
    filesize = len(output)
    output+='END'
    #proxy.sendall(data)
    #proxy.sendall('END')

    poller = select.poll()
    flags = select.POLLIN|select.POLLOUT
    flags |= select.POLLERR|select.POLLHUP|select.POLLNVAL
    poller.register(proxy,flags)

    input = ''
    ready = True

    while ready:
        for fd,flags in poller.poll():
            #PrintFlags(flags)
            if flags & select.POLLIN:
                data = proxy.recv(1024)
                print 'Input:',repr(data)

                if not data:
                    print 'No data on read, client connection gone'
                    ready=False
                    continue

                input+=data

                if input.endswith('END\r\n'):
                    print 'Finished'
                    break

            elif flags & select.POLLOUT:
                try:
                    n = proxy.send(output[:1024])
                except:
                    print 'Error writing'
                    break
                output = output[n:]
                print 'Output: %d bytes sent, %d remaining' % (n,len(output))

                if not output:
                    poller.unregister(proxy)
                    poller.register(proxy,select.POLLIN)

            elif flags & (select.POLLERR|select.POLLHUP|select.POLLNAVL):
                print 'ERROR'
                break

    stop = time.time()

    print 'Hanging up'
    proxy.close()

    elapsed = stop-start
    rate = filesize/elapsed

    print 'Elapsed time: %s secs' % datetime.timedelta(seconds=elapsed)
    print 'Total bytes : %d' % filesize
    print 'Rate        : %d Bps (%d bps)' % (rate,rate*8)
    print 'Checksum    : %s' % checksum.hexdigest()

    print 'Finished'

if __name__ == '__main__':
    filename = sys.argv[1]
    SendFile(filename)
