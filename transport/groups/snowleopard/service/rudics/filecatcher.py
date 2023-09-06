#!/usr/bin/env python

#########################################################
#
#   Example server for use with testing RDTP.
#
#   2008-01-19  Todd Valentic
#               Initial implementation.
#
#########################################################

import SocketServer
import select
import logging
import md5

logging.basicConfig(level=logging.DEBUG)

class RequestHandler(SocketServer.BaseRequestHandler):

    def handle(self):

        input=''
        checksum=md5.md5()

        logging.info('Incoming connection from %s' % str(self.client_address))
        self.request.sendall('File collection service\n')

        poller = select.poll()
        poller.register(self.request,select.POLLIN)

        while True:
            events = poller.poll()

            for fd,event in events:
                if fd==self.request.fileno():
                    data = self.request.recv(1024)
                    if not data:
                        logging.info('Client gone')
                        return
                    else:
                        logging.info('Incoming: %s' % len(data))
                        input+=data
                        checksum.update(data)

                    #logging.info('Outgoing: %s' % repr(data))
                    #self.request.sendall(data)

        logging.info('Num bytes: %d' % len(input))
        logging.info('Checksum:  %s' % checksum.hexdigest())

        logging.info('Request finished')


class Server(SocketServer.TCPServer):

    allow_reuse_address = True

    def __init__(self,port):
        SocketServer.TCPServer.__init__(self,('',port),RequestHandler)

if __name__ == '__main__':

    port = 9000

    logging.info('Listening on port %d' % port)

    Server(port).serve_forever()


