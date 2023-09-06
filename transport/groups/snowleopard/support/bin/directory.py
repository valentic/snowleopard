#!/usr/bin/env

###################################################################
#
#   Encapsulate access to the AMISR directory service.
#
#   2005-11-11  Todd Valentic
#               Initial implementation.
#
#   2007-03-23  Todd Valenti
#               Added default timeout.
#
###################################################################

import xmlrpclib
import socket

socket.setdefaulttimeout(3)

class Directory:

    def __init__(self,host='localhost',port=8411):

        url = 'http://%s:%d' % (host,port)
        self.directory = xmlrpclib.ServerProxy(url)

    def connect(self,service):
        url = self.directory.get(service,'url')
        return xmlrpclib.ServerProxy(url)

if __name__ == '__main__':

    # Example usage - connect to beamcode service:

    dir = Directory()
    beamcodes = dir.connect('beamcodes')

    print beamcodes.list()

