#!/usr/bin/env python

###################################################################
#
#   Iridium dialup modem service
#
#   This service provides an interface to the Iridium modem.
#
#   2008-01-17  Todd Valentic
#               Initial implementation
#
#   2008-04-21  Todd Valentic
#               Implement work around for TS-7260 lockups
#               (send on character at a time).
#
#               Move lots of log info to DEBUG.
#
#   2008-05-31  Todd Valentic
#               Catch any errors in the worker thread and keep
#                   on running. Don't let it die.
#
#   2009-11-18  Todd Valentic
#               Added sendSBD()
#
###################################################################

from Transport      import ProcessClient
from Transport      import XMLRPCServerMixin
from Transport      import AccessMixin
from threading      import Thread
from datetime       import datetime,timedelta

import sys
import SocketServer
import select
import struct
import time

import modem

class RequestHandler(SocketServer.BaseRequestHandler):

    def printBuffer(self,label,data):
        if self.dumpbuffer:
            self.log.debug('%s: %s' % (label,repr(data)))

    def setup(self):
        self.log = self.server.log
        self.modem = self.server.modem
        self.wait = self.server.wait
        self.blocksize = self.server.blocksize
        self.dumpbuffer = self.server.dumpbuffer

    def handle(self):
        try:
            self._handle()
        except:
            self.log.exception('Problem handling request')

        self.log.info('request finished')

    def _handle(self):

        self.log.info('-'*20)
        self.log.info('From %s' % str(self.client_address))

        if not self.modem.isConnected():
            self.log.info('Need to go online')
            try:
                self.modem.dialup()
            except:
                self.log.exception('Failed to connect')
                return
        else:
            self.log.info('Already online')

        poller = select.poll()

        poller.register(self.request,select.POLLIN)
        poller.register(self.modem,select.POLLIN)

        ready=True
        output=''
        input=''

        while ready:

            events = poller.poll(5000)

            for fd,event in events:

                if fd==self.request.fileno() and event&select.POLLIN:

                    data = self.request.recv(4096)

                    if not data:
                        self.log.info('Socket disconnect')
                        ready=False
                    else:
                        self.printBuffer('socket -> output buffer',data)
                        self.log.debug('socket -> output buffer')
                        output+=data
                        poller.register(self.modem,select.POLLIN|select.POLLOUT)

                elif fd==self.request.fileno() and event&select.POLLOUT:
                    n = self.request.send(input[:256])
                    self.printBuffer('input buffer -> socket',input[:n])
                    self.log.debug('input buffer -> socket')
                    input = input[n:]
                    if not input:
                        poller.register(self.request,select.POLLIN)

                elif fd==self.modem.fileno() and event&select.POLLIN:
                    data=self.modem.read()
                    self.printBuffer('modem -> input buffer',data)
                    self.log.debug('modem -> input buffer')
                    input+=data
                    poller.register(self.request,select.POLLIN|select.POLLOUT)

                elif fd==self.modem.fileno() and event&select.POLLOUT:
                    try:
                        self.printBuffer('output buffer -> modem',output)
                        self.log.debug('output buffer -> modem')
                        self.modem.write(output[:self.blocksize])
                        output=output[self.blocksize:]
                        if not output:
                            poller.register(self.modem,select.POLLIN)
                    except:
                        self.log.exception('Problem writing to modem')
                        self.modem.toggleDTR(1)
                        self.modem.close()
                        ready=False
                        break

            if not self.modem.isConnected():
                ready=False
                self.modem.hangup()
                self.log.info('No carrier')

        self.log.info('Finished')

class SocketThread(Thread,AccessMixin,SocketServer.TCPServer):

    allow_reuse_address = True
    daemon_threads      = True

    def __init__(self,parent,port):
        Thread.__init__(self)
        AccessMixin.__init__(self,parent)
        SocketServer.TCPServer.__init__(self,('',port),RequestHandler)

        self.setDaemon(True)

        self.blocksize = self.getint('blocksize',1)
        self.dumpbuffer = self.getboolean('dumpbuffer',False)

    def run(self):

        while self.running:
            try:
                self._run()
            except:
                self.log.exception('Problem in worker thread:')

    def _run(self):

        if self.getboolean('simulate',False):
            self.modem = modem.SimulatedIridium(self)
        else:
            self.modem = modem.Iridium(self)

        poller = select.poll()
        poller.register(self.socket,select.POLLIN)

        while self.running:
            if poller.poll(1000):
                self.handle_request()
                timeout = datetime.now()+timedelta(minutes=1)

            elif self.modem.isConnected() and datetime.now()>timeout:
                self.log.info('Idle timeout')
                self.modem.hangup()

        self.log.info('Worker thread exiting')

        self.modem.hangup()

class Server(ProcessClient,XMLRPCServerMixin):

    def __init__(self,args):
        ProcessClient.__init__(self,args)
        XMLRPCServerMixin.__init__(self)

        self.register_function(self.hangup)
        self.register_function(self.stats)
        self.register_function(self.sendSBD)

        port = int(self.directory.get('modemdata','port'))

        self.thread = SocketThread(self,port)
        self.thread.start()

    def hangup(self):
        self.thread.modem.hangup()
        return 1

    def stats(self):
        return self.thread.modem.getStats()

    def sendSBD(self,msg):
        return self.thread.modem.sendSBD()

    def run(self):
        XMLRPCServerMixin.run(self)

if __name__ == '__main__':
    Server(sys.argv).run()

