#!/usr/bin/env python

###################################################################
#
#   File exchange service
#
#   2007-12-17  Todd Valentic
#               Initial implementation
#
#   2008-04-09  Todd Valentic
#               Add file compression flag to map file
#
#   2008-05-18  Todd Valentic
#               Add option to not split source files.
#               Incorporate map file into main config file.
#               Use component objects for mapping.
#               Allow options on each component (size, compression)
#
#   2008-05-31  Todd Valentic
#               Write flag file when successful
#
#   2008-08-02  Todd Valentic
#               Catch errors when writing inbound files.
#
#   2008-08-06  Todd Valentic
#               Added stop() method
#               Reset retry count on successful connect
#
#   2008-08-03  Todd Valentic
#               Added retry() method for doing retries
#               Retry getting modem stats if it fails
#
#   2008-11-10  Todd Valentic
#               Use rudicsHost as well we rudicsPort
#               Option to skip querying modem stats for direct
#                   connect network situations
#
#   2008-12-14  Todd Valentic
#               Make sure to add .bz2 if compressing files.
#
#   2009-02-27  Todd Valentic
#               Don't add empty sets to partition results (this
#                   case happened when a single file is larger
#                   then the maximum size).
#               Fix problems with splitting large files.
#
#   2009-09-29  Todd Valentic
#               Problems with logging and WorkerThread. This
#                   looks like it comes about because the worker
#                   thread was exiting after every transfer (and
#                   maybe closing the file handle?). I'm now
#                   using a long running thread instead and that
#                   seems to work fine.
#
#   2009-11-19  Todd Valentic
#               Fix bug in setting time (wrong code for seconds)
#
#   2010-03-13  Todd Valentic
#               Update exchange flag file as soon as server is
#               opened. That way we won't trigger the failsafe
#               watchdog if we have a very long transfer.
#
#   2010-03-16  Todd Valentic
#               Add try..except around reading file when moving
#                   to spool.
#
#   2010-05-14  Martin Grill
#               More verbose messages
#
#   2010-05-21  Martin Grill / Todd Valentic
#               Sync time to news server if no modem present
#
#   2011-05-16  Todd Valentic
#               Add group.limit parameter to allow only a subset
#                   of the pending files to be transmitted.
#
#		        Add ack of inbound messages.
#
#   2011-08-17  Todd Valentic
#               Cache iridium results
#
#   2012-05-18  Todd Valentic
#               Harden moveToSpool:
#                   Create spool directory if missing (happens
#                       if we manually remove to clear an error
#                       while exchange is running)
#                   Ensure files are closed - attemp to figure
#                       out why we see occasional file corruption
#
#   2013-05-23  Todd Valentic
#               Add alternate spool location.
#               Remove original files only when sent from spool
#               Rename moveToSpool -> copyToSpool
#
#   2014-06-09  Todd Valentic
#               Only allow setSystemTime to make change if we
#                   are close to the current time (within 30 days).
#
###################################################################

from Transport                  import ProcessClient
from Transport                  import XMLRPCServerMixin
from Transport                  import AccessMixin
from Transport                  import NewsTool
from Transport                  import ConfigComponent
from Transport.Util             import datefunc, sizeDesc
from Transport.Util.dateutil    import parser
from threading                  import Thread,Lock,Event
from newskit                    import NewsServer, NewsControl
from newskit                    import NewsPoller, NewsPoster
from datetime                   import datetime, timedelta
from ConfigParser               import ConfigParser

import os
import sys
import glob
import email
import nntplib
import commands
import socket
import md5
import math
import bz2

socket.setdefaulttimeout(10*60)

def synchronized(lock):

    def wrap(f):
        def newFunction(*args, **kw):
            lock.acquire()
            try:
                return f(*args, **kw)
            finally:
                lock.release()
        return newFunction
    return wrap

class StatusData:

    lock = Lock()

    def __init__(self):
        self.status = None

    @synchronized(lock)
    def set(self, status):
        self.status = status

    @synchronized(lock)
    def get(self):
        return self.status

class FileGroup(ConfigComponent):

    def __init__(self,name,parent):
        ConfigComponent.__init__(self,'group',name,parent)

        self.newsgroup      = self.get('newsgroup')
        self.filespecs      = self.get('files','').split()
        self.maxSize        = self.getBytes('maxSize')
        self.maxFiles       = self.getboolean('maxFiles')
        self.compressFiles  = self.getboolean('compress',False)
        self.removeFiles    = self.getboolean('remove',True)
        self.limit	        = self.getint('limit')

        self.log.info('%s:' % name)
        self.log.info('  files: %s' % self.filespecs)
        self.log.info('  group: %s' % self.newsgroup)

    def limitFiles(self,files):

        files,dropfiles = files[:self.limit],files[self.limit:]

        if self.limit<0:
            files,dropfiles = dropfiles,files

        if self.removeFiles:
            for filename in dropfiles:
                try:
                    os.remove(filename)
                except:
                    self.log.exception('Failed to remove %s' % filename)
                    continue

        return files

    def partitionFiles(self,files):

        result   = []
        curSize  = 0
        curFiles = []

        if self.limit is not None:
            files = self.limitFiles(files)

        for filename in files:
            filesize = os.path.getsize(filename)

            if self.maxSize and curSize+filesize>self.maxSize:
                if curFiles:
                    result.append(curFiles)
                curSize  = 0
                curFiles = []

            curSize+=filesize
            curFiles.append(filename)

            if self.maxFiles and len(curFiles)==self.maxFiles:
                result.append(curFiles)
                curSize  = 0
                curFiles = []

        if curFiles:
            result.append(curFiles)

        return result

class WorkerThread(Thread, AccessMixin):

    def __init__(self, parent):
        Thread.__init__(self)
        AccessMixin.__init__(self, parent)

        self.setDaemon(True)

        self.status     = parent.statusData
        self.directory  = parent.directory
        self.connect    = parent.connect

        self.groups     = self.getComponents('groups',FileGroup)

        self.log.info('File groups:')
        for map in self.groups:
            self.log.info('  - %s' % map.name)

        self.retryWait      = self.getDeltaTime('retry.wait',60)
        self.maxRetries     = self.getint('retry.max',10)
        self.flagFile       = self.get('filename.flag')
        self.queryModem     = self.getboolean('querymodem',True)
        self.spoolRoot      = self.get('spool','.')
        self.spoolDir       = os.path.join(self.spoolRoot,'spool')
        self.spoolConf      = os.path.join(self.spoolRoot,'spool.conf')

        self.server     = NewsServer(parent.rudicsHost, parent.rudicsPort)
        self.poller     = NewsPoller(self.server, log=self.log)
        self.poster     = NewsPoster(self.server, log=self.log)
        self.control    = NewsControl(self.server, log=self.log)

        self.poller.setGroup(self.get('inbound.newsgroup'))
        self.poller.setStopFunc(self.isStopped)
        self.poller.setCallback(self.processInbound)
        self.poller.setDebug(True)

        if not os.path.exists(self.spoolDir):
            os.makedirs(self.spoolDir)

        self.cache = self.connect('cache')

    def isRunning(self):
        return self.running and self.parent.runRequest.isSet()

    def isStopped(self):
        return not self.isRunning()

    def run(self):

        self.log.info('Worker thread starting')

        while self.running:

            while not self.parent.runRequest.isSet():
                self.parent.runRequest.wait(1)

            self.log.info('Run request received')

            try:
                self.process()
            except:
                self.log.exception('Problem processing:')

            self.log.info('Transfer finished')

            self.parent.runRequest.clear()

        self.log.info('Worker thread exiting')

    def retry(self,func):

        numRetries = 0

        while self.isRunning() and numRetries<self.maxRetries:

            if numRetries>0:
                self.log.info('  -- Retry %d' % numRetries)

            try:
                func()
                return True
            except:
                self.log.exception('Problem')
                numRetries+=1
                self.log.info('Waiting %s' % self.retryWait)
                self.wait(self.retryWait)

        return False

    def transfer(self):

        self.log.info('  * Connecting to news server')
        self.server.open()

        open(self.flagFile,'w').write(str(datetime.now()))

        if self.isRunning():    self.getInbound()
        if self.isRunning():    self.resumeTransfer()
        if self.isRunning():    self.sendOutbound()

    def process(self):

        self.log.info('Processing start')

        self.totalBytesIn = 0
        self.totalBytesOut = 0
        self.totalDataBytesOut = 0
        self.totalDataBytesIn = 0
        starttime = datetime.now()

        if self.retry(self.getStats):

            # getStats resets the clock...
            starttime = datetime.now()

            self.retry(self.transfer)

            self.log.info('  * Closing news server')
            self.server.close()

        elapsed = datetime.now()-starttime

        self.log.info('Processing finished:')
        self.log.info('  total time: %s' % elapsed)
        self.log.info('  bytes in  : %s' % sizeDesc(self.totalBytesIn))
        self.log.info('  bytes out : %s' % sizeDesc(self.totalBytesOut))
        self.log.info('  data  in  : %s' % sizeDesc(self.totalDataBytesIn))
        self.log.info('  data  out : %s' % sizeDesc(self.totalDataBytesOut))

    def getStats(self):

        if self.queryModem:

            self.log.info('  * Iridium stats')

            self.log.info('    - read from modem')
            stats = self.connect('modem').stats()
            curtime = parser.parse(stats['time'])

            self.setSystemTime(curtime)
            self.saveStats(stats, curtime)
            self.cache.put('iridium',stats)

        else:
            self.log.info('  * syncing time to news server')
            try:
                self.server.open()
                curtime = self.server.datetime()
                self.setSystemTime(curtime)
                self.log.info('  * set time to %s' % curtime)
            finally:
                self.server.close()

        return

    def saveStats(self, stats, curtime):
        filename = curtime.strftime(self.get('filename.iridium'))
        dirname  = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        self.log.info('    - writing output file: %s' % filename)

        out = open(filename, 'w')
        print >> out, '[iridium]'
        for key, value in stats.items():
            print >> out, key, ':', value
        out.close()

    def setSystemTime(self, curtime):

        self.log.info('    - setting system time')

        # Format - MMDDhhmmCCYY.ss

        before = datetime.now()
        window = timedelta(days=30)

        # Only change time if it is near the current time

        if abs(curtime-before) > window:
            self.log.error('      time delta too large: %s' % (curtime-before))
            return False

        cmd = curtime.strftime('setclock %m%d%H%M%Y.%S')
        status, output = commands.getstatusoutput(cmd)

        if status!=0:
            self.log.error('Problem setting system time')
            self.log.error('  cmd: %s' % cmd)
            self.log.error('  status: %s' % status)
            self.log.error('  output: %s' % output)
            return False

        after = datetime.now()
        self.log.info('        before: %s' % before)
        self.log.info('        after:  %s' % after)
        self.log.info('        delta:  %s' % (after-before))

    def getInbound(self):
        self.log.info('  * Processing inbound messages')
        self.poller.processUnreadMessages()

    def ackInbound(self, message):
        filename = self.currentTime().strftime(self.get('filename.ack'))
        dirname  = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        self.log.info('    - writing output file: %s' % filename)

        out = open(filename, 'a')
        print >> out,message['XRef']
        out.close()

    def processInbound(self, message):
        self.log.info('Inbound: %s' % message['XRef'])

        dest = message['X-Transport-DestPath'] or '/home/ftp/inbound'

        self.log.info('Saving to path %s' % dest)

        try:
            filenames = NewsTool.saveFiles(message, path=dest)
        except:
            # should make a note in an outbound trouble group...
            self.log.exception('Problem saving files')
            filenames = []

        # Need a way of getting the message size for totalBytesIn

        for filename in filenames:
            self.totalDataBytesIn += os.path.getsize(os.path.join(dest,filename))
            self.log.info('  - %s' % filename)

        self.ackInbound(message)

    def resumeTransfer(self):

        if os.path.exists(self.spoolConf):
            self.log.info('  * Resuming outbound transfer')
            self.sendSpool()

    def createGroup(self,group):
        self.log.info('    Group "%s" does not exist, creating it' % group)

        self.control.newgroup(group)

        for attempt in range(10):
            self.log.info('        waiting...')
            self.wait(30)

            if self.server.groupExists(group):
                return

            if not self.running:
                return

        raise IOError('Timeout waiting for group creation')

    def sendSpool(self):

        files = glob.glob(os.path.join(self.spoolDir, '*'))
        files.sort()

        if not files:
            return

        config = ConfigParser()
        config.read(self.spoolConf)

        if len(config.sections())>1:    # implies we have a chunked file
            for filename in files:
                self.postFiles([filename],config)
        else:
            self.postFiles(files,config)

        # Remove original files if successfully sent

        for filename in config.get('DEFAULT','filenames').split('\n'):
            try:
                os.remove(filename)
            except:
                self.log.exception('Failed to remove: %s' % filename)

        os.remove(self.spoolConf)

    def postFiles(self,filenames,config):

        self.log.info('    posting files: %d' % len(filenames))

        numBytes = 0

        for filename in filenames:
            filesize = os.path.getsize(filename)
            numBytes = numBytes+filesize
            self.log.info('      %s (%d/%d)' % (filename,filesize,numBytes))

        if len(filenames)==1 and config.has_section(filenames[0]):
            headers = dict(config.items(filenames[0]))
        else:
            headers = dict(config.items('DEFAULT'))

        starttime = datetime.now()

        while self.running:
            try:
                msgBytes = self.poster.post(filenames,headers=headers)
                self.totalBytesOut += msgBytes
                self.totalDataBytesOut += numBytes
                break
            except nntplib.NNTPTemporaryError,desc:
                if '441 No valid newsgroups' in str(desc):
                    self.createGroup(headers['newsgroups'])
                else:
                    raise

        for filename in filenames:
            os.remove(filename)

        elapsed = datetime.now()-starttime
        secs = datefunc.timedelta_as_seconds(elapsed)
        rate = int(numBytes/secs*8)
        self.log.info('      %.1f secs, %d bytes, %d bps' % (secs,numBytes,rate))

    def clearSpool(self):

        stalefiles = glob.glob(os.path.join(self.spoolDir,'*'))

        for stalefile in stalefiles:
            os.remove(stalefile)

    def splitFile(self,basename,data,config,maxSize):

        checksum = md5.new()

        config.set('DEFAULT','X-Transport-Filename',basename)

        numChunks = int(math.ceil(len(data)/float(maxSize)))

        for chunk in range(numChunks):
            start = chunk*maxSize
            bytes = data[start:start+maxSize]
            chunkname = os.path.join(self.spoolDir,'chunk.%04d' % chunk)
            open(chunkname,'wb').write(bytes)
            checksum.update(bytes)
            config.add_section(chunkname)
            part = '%d/%d' % (chunk,numChunks)
            config.set(chunkname,'X-Transport-Part',part)

        config.set('DEFAULT','X-Transport-MD5',checksum.hexdigest())

        self.log.info('      split into %d parts' % numChunks)

    def copyToSpool(self,filenames,group):

        config = ConfigParser()
        config.set('DEFAULT','Newsgroups',group.newsgroup)

        if not os.path.exists(self.spoolDir):
            os.makedirs(self.spoolDir)

        for filename in filenames:

            basename = os.path.basename(filename)

            try:
                data = open(filename).read()
            except:
                self.log.exception('Failed to read %s' % filename)
                continue

            if group.compressFiles:
                config.set('DEFAULT','X-Transport-Compress','True')
                data = bz2.compress(data)
                basename+='.bz2'

            if group.maxFiles==1 and group.maxSize:
                self.splitFile(basename,data,config,group.maxSize)
            else:
                destname = os.path.join(self.spoolDir,basename)
                output = open(destname,'w')
                output.write(data)
                output.close()

        if group.removeFiles:
            config.set('DEFAULT','filenames','\n'.join(filenames))
        else:
            config.get('DEFAULT','filenames','')

        output = open(self.spoolConf,'w')
        config.write(output)
        output.close()

    def sendOutbound(self):
        self.log.info('  * Processing outbound messages')

        for group in self.groups:

            self.log.info('     group: %s' % group.name)

            files = []

            for filespec in group.filespecs:
                filelist = glob.glob(filespec)
                files.extend(filelist)
                self.log.info('    %s: %d files' % (filespec, len(filelist)))

            filesets = group.partitionFiles(sorted(files))

            self.log.info('    partitioned into %d sets' % len(filesets))

            for k,fileset in enumerate(filesets):
                self.log.info('    File set %s' % k)
                for name in fileset:
                    self.log.info('    %s' % name)
                try:
                    self.clearSpool()
                    self.copyToSpool(fileset, group)
                except:
                    self.log.exception('Problem moving files to spool')
                    continue

                self.sendSpool()

class Server(ProcessClient, XMLRPCServerMixin):

    def __init__(self, args):
        ProcessClient.__init__(self, args)
        XMLRPCServerMixin.__init__(self)

        self.statusData = StatusData()

        self.rudicsHost = self.directory.get('rudicsnews', 'host')
        self.rudicsPort = int(self.directory.get('rudicsnews', 'port'))

        self.register_function(self.start)
        self.register_function(self.stop)
        self.register_function(self.busy)

        self.log.info('Connecting to RUDICS on port %s' % self.rudicsPort)

        self.runRequest = Event()

        self.worker = WorkerThread(self)
        self.worker.start()

    def start(self):
        if self.busy():
            self.log.warn('Transfer already running')

        self.runRequest.set()

        return 1

    def busy(self):
        return self.runRequest.isSet()

    def stop(self):
        self.runRequest.clear()
        return 1


if __name__ == '__main__':
    Server(sys.argv).run()

