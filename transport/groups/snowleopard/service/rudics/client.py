#!/usr/bin/env python

################################################################
#
#   RUDICS Proxy - remote client side
#
#   2008-02-23  Todd Valentic
#               Initial implementation
#
################################################################

from Transport      import ProcessClient

import sys
import asyncore

import rdtp

class Client(ProcessClient):

    def __init__(self,argv):
        ProcessClient.__init__(self,argv)

        host = self.get('connect.host','')
        port = self.getint('connect.port',9080)
        portmap = {}

        self.log.info('Connecting to port %d' % port)

        self.log.info('Port mappings:')

        for line in self.get('portmap','').split('\n'):
            try:
                localport,remoteaddr = line.split()
                portmap[int(localport)] = remoteaddr
                self.log.info('  %5s: %s' % (localport,remoteaddr))
            except:
                continue

        rdtp.Client(port,host=host,portmap=portmap,log=self.log)

    def run(self):

        self.log.info('Ready to start')

        while self.running:
            try:
                asyncore.loop(timeout=0.1,use_poll=True,count=1)
            except:
                pass

        self.log.info('Finished')

if __name__ == '__main__':
    Client(sys.argv).run()

