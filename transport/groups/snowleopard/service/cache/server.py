#!/usr/bin/env python

###################################################################
#
#   Caching service
#
#   This service is used to cache values between clients.
#
#   2009-11-03  Todd Valentic
#               Initial implementation
#
#   2009-11-11  Todd Valentic
#               Incorporate config lookup (replaced the separate
#                   config service).
#
###################################################################

from Transport  import ProcessClient
from Transport  import XMLRPCServerMixin

import sys

class Server(ProcessClient,XMLRPCServerMixin):

    def __init__(self,args):
        ProcessClient.__init__(self,args)
        XMLRPCServerMixin.__init__(self)

        self.register_function(self.getValue,'get')
        self.register_function(self.put)
        self.register_function(self.list)
        self.register_function(self.lookup)

        self.cache = {}

    def put(self,key,value):
        self.cache[key]=value
        return True

    def getValue(self,key):
        return self.cache[key]

    def list(self):
        return self.cache.keys()

    def lookup(self,keyword):
        return self.get(keyword)

if __name__ == '__main__':
    Server(sys.argv).run()

