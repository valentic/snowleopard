#!/usr/bin/python

import sys
sys.path.append('/opt/transport/lib/python2.4/site-packages')

from newskit    import  NewsServer, NewsPoller, NewsPoster, NewsControl

import time
import datetime
import logging
import nntplib
import os

from StringIO import StringIO
from email.Generator import Generator

logging.basicConfig(level=logging.DEBUG)

def printMessage(message):
    print '-'*50
    print 'Num bytes: %s' % len(message.get_payload())
    print message.get_payload()
    print '-'*50

testgroup = 'transport.testing'

server = NewsServer('localhost',8110)
#server = NewsServer('localhost',10001)

print 'Opening server connection'
server.open()

print 'Getting server timestamp'
print server.date()

print 'Checking if test group exists'
if server.groupExists(testgroup):
    print '  - yes'
else:
    print '  - no, need to create'

    control = NewsControl(server)

    control.newgroup(testgroup)

    while not server.groupExists(testgroup):
        time.sleep(30)
        print '    waiting...'

    print '    group created successfully'

poster = NewsPoster(server,group=testgroup)
poller = NewsPoller(server,group=testgroup,callback=printMessage)

print 'Posting text message'
try:
    poster.post(text="Hello world: %s" % datetime.datetime.now())
except nntplib.NNTPTemporaryError,desc:
    print 'Error:',str(desc)
    sys.exit(1)

datafile = '0100k.dat'
print 'Posting file:',datafile
headers = {'X-Transport-DestPath':'/home/ftp/inbound/code'}
#poster.post('demo.py',headers=headers)
start = datetime.datetime.now()
poster.post(datafile,headers=headers)
stop = datetime.datetime.now()
elapsed = stop-start
numbytes = os.path.getsize(datafile)
print 'Elapsed time: %s' % elapsed
print 'Bytes/sec: %s' % (numbytes/elapsed.seconds)

print 'Polling'
poller.setDebug(True)
poller.processUnreadMessages()

print 'Finished'
