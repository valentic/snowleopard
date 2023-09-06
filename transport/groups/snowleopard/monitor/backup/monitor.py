#!/usr/bin/env python

##################################################################
#
#   Backup data files
#
#   Compressing large files can take a long time. To speed things
#   up, use the --fast flag and a parallel verison of the bzip2.
#
#   http://superuser.com/questions/591154/time-to-zip-very-large-100g-files
#
#   Example timings:
#
#   python bzip: real 1m16.619s, user 1m15.682s, sys 0m0.733s
#   pbzip2:      real 0m20.306s, user 1m17.727s, sys 0m0.917s
#
#   pbzip2 -1 -l -k sl01-radio-20160715-194901.dat
#
#   400000017 Jul 18 07:32 sl01-radio-20160715-194901.dat
#   114126955 Jul 18 07:33 sl01-radio-20160715-194901.dat.bz2 - python
#   114181318 Jul 18 07:32 sl01-radio-20160715-194901.dat.bz2 - pbzip2
#
#   2016-07-18  Todd Valentic
#               Initial implementation.
#
##################################################################

from DataMonitor import DataMonitor

import sys
import os
import datetime
import ConfigParser
import fnmatch

class Sampler (DataMonitor):

    def __init__(self,argv):
        DataMonitor.__init__(self,argv)

        self.sourcePath = self.get('source.path','.')
        self.backupPath = self.get('backup.path','/tmp')
        self.excludeFiles = self.getList('source.exclude','')

        self.keepSource = self.getboolean('source.keep',False)

    def validFilename(self,filename):

        for spec in self.excludeFiles:
            if fnmatch.fnmatch(filename,spec):
                return False

        return True

    def getFilename(self):

        results = []

        for root,dirnames,filenames in os.walk(self.sourcePath):

            for filename in filenames:
                if self.validFilename(filename):
                    results.append(os.path.join(root,filename))

        return results

    def powerUp(self):
        self.setResources('ssd=on')

        self.log.info('  - powering on SSD')
        self.log.info('  - waiting for filesystem mount')

        timeout = self.currentTime() + datetime.timedelta(seconds=60)

        while self.currentTime()<timeout:
            if os.path.isdir(self.backupPath):
                return

        raise IOError('Backup path is not ready: %s' % self.backupPath)

    def powerDown(self):
        self.clearResources()

    def backupFile(self,filename):

        outputname = filename.replace(self.sourcePath,self.backupPath)+'.bz2'

        dirname = os.path.dirname(outputname)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        cmd = 'compress %s %s' % (filename,outputname)

        if not self.runScript(cmd):
            raise IOError('Problem compressing file')

        if not self.keepSource:
            os.remove(filename)

        return outputname

    def backupFiles(self):

        results = ConfigParser.ConfigParser()
        results.set('DEFAULT','time.start',str(self.currentTime()))

        filenames = self.getFilename()
        numfiles  = len(filenames)

        results.set('DEFAULT','numfiles',str(numfiles))

        self.log.info(' - found %d files' % numfiles)

        for index,filename in enumerate(sorted(filenames)):
            section = 'file-%d' % index
            results.add_section(section)
            results.set(section,'source',filename)
            results.set(section,'source.size',str(os.path.getsize(filename)))

            try:
                backupname = self.backupFile(filename)
            except:
                break

            results.set(section,'backup',backupname)
            results.set(section,'backup.size',str(os.path.getsize(backupname)))

            if not self.running:
                break

        results.set('DEFAULT','time.stop',str(self.currentTime()))

        return results

    def sample(self):
        self.log.info('Backing up files')

        try:
            self.powerUp()
            results = self.backupFiles()
        finally:
            self.powerDown()

        return results

    def write(self,output,timestamp,data):
        data.write(output)

if __name__ == '__main__':
    Sampler(sys.argv).run()

