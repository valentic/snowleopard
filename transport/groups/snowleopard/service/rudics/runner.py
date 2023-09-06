#!/usr/bin/env python

import os
import logging
import optparse
import signal
import asyncore

import rdtp

logging.basicConfig(level=logging.INFO)

running = True
dumpstats = False

def StopHandler(signum,frame):
    print 'handler hit'
    global running
    running=False

def StatsHandler(signum,frame):
    print 'dump stats handler'
    global dumpstats
    dumpstats=True

if __name__ == '__main__':

    signal.signal(signal.SIGINT, StopHandler)
    signal.signal(signal.SIGTERM, StopHandler)
    signal.signal(signal.SIGHUP, StatsHandler)

    usage = 'Usage: %prog [options] port'

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-s','--server',action='store_true',dest='server')
    parser.add_option('-m','--portmap',dest='portmap')
    parser.add_option('-r','--host',dest='host')

    parser.set_defaults(server=False,portmap=None,host='')

    (options,args) = parser.parse_args()

    if len(args)<1:
        parser.error('Not enough args')

    port = int(args[0])

    portmap = {}
    if options.portmap and os.path.exists(options.portmap):
        for line in open(options.portmap):
            try:
                localport,remoteaddr = line.split()
                localport = int(localport)
            except:
                continue
            portmap[localport] = remoteaddr

    if options.server:
        obj = rdtp.Server(port,portmap=portmap,log=logging)
    else:
        obj = rdtp.Client(port,host=options.host,portmap=portmap,log=logging)

    while running:
        asyncore.loop(timeout=0.1,use_poll=True,count=1)
        if dumpstats:
            obj.mux.print_stats()
            dumpstats=False

