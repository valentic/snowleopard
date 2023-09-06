#!/usr/bin/python

####################################################################
#
#   NewsKit
#
#   Based on the NewsTool inferface. Experimental redesign for
#   small, embedded systems running Iridium rudics.
#
#   2008-01-03  Todd Valentic
#               Initial implementation

#   2008-05-21  Todd Valentic
#               Use basename for filename in attachments
#               Have post return num bytes in message
#
#	2008-08-08	Todd Valentic
#				Don't send quit in close(). When the remote
#					connection had dropped, this was taking
#				 	the full timeout to respond.
#				Reduce timeout to be 2 minutes.
#
#   2008-08-12  Todd Valentic
#               Restore timeout to 10 minutes. Debugging a
#                   connection problem.
#
#   2008-09-03  Todd Valentic
#               Close before open.
#
#   2010-05-21  Martin Grill
#               Time from news server was parsed incorrectly in
#               self.datetime
#
####################################################################

from Transport.Util.dateutil    import parser

from email.MIMEText             import MIMEText
from email.MIMEMultipart        import MIMEMultipart
from email.MIMEImage            import MIMEImage
from email.MIMEAudio            import MIMEAudio
from email.MIMEBase             import MIMEBase
from email.Generator            import Generator
from email                      import Encoders

import os
import nntplib
import logging
import mimetypes
import email
import cStringIO
import fnmatch
import datetime

#########################################################################
#
#   News Server
#
#########################################################################

class NewsServer:

    def __init__(self,host,port=119,log=logging):
        self.host   = host
        self.port   = port
        self.log    = logging
        self.server = None

    def __del__(self):
        self.log.info('In __del__')
        self.close()

    def open(self):
        self.close()
        self.server = nntplib.NNTP(self.host,self.port,readermode=True)
        self.server.sock.settimeout(10*60)

    def close(self):
        if self.server:
            try:
                #self.server.quit()
                self.server.sock.close()
            except:
                pass
        self.server = None

    def sync(self,func,*args,**kw):

        if self.server:
            try:
                return getattr(self.server,func)(*args,**kw)
            except nntplib.NNTPError:
                raise

        self.open()
        return getattr(self.server,func)(*args,**kw)

    def group(self,*args,**kw):
        return self.sync('group',*args,**kw)

    def date(self,*args,**kw):
        return self.sync('date',*args,**kw)

    def newsgroups(self,*args,**kw):
        return self.sync('newsgroups',*args,**kw)

    def list(self,*args,**kw):
        return self.sync('list',*args,**kw)

    def newnews(self,*args,**kw):
        return self.sync('newnews',*args,**kw)

    def article(self,*args,**kw):
        return self.sync('article',*args,**kw)

    def xhdr(self,*args,**kw):
        return self.sync('xhdr',*args,**kw)

    def post(self,*args,**kw):
        return self.sync('post',*args,**kw)

    def head(self,*args,**kw):
        return self.sync('head',*args,**kw)

    def body(self,*args,**kw):
        return self.sync('body',*args,**kw)

    def quit(self,*args,**kw):
        return self.close()

    #-- Extended functions --------------------------------------------

    def groupExists(self,newsgroup):
        try:
            info = self.server.group(newsgroup)
            return True
        except:
            return False

    def datetime(self):
        # 111 YYYYMMDDhhmmss
        return parser.parse(self.server.date()[0].split()[1])

    def numArticles(self,offset,newsgroups):

        # List articles during offset (which is a datetime.timedelta)
        #
        # newsgroups can be a string or a list

        start   = self.datetime()-offset
        date    = start.strftime('%Y%m%d')
        time    = start.strftime('%H%M%S GMT')

        if isinstance(newsgroups,basestring):
            newsgroups = [newsgroups]

        articles = {}

        for group in newsgroups:
            nummsgs = len(self.newnews(group,date,time)[1])
            articles[group] = nummsgs

        return articles

    def queryGroup(self,group):
        response,count,first,last,name = self.group(group)
        first = int(first)
        last  = int(last)
        if first==0:
            count=0
        else:
            count = last-first+1
        return first,last,count

    def listGroups(self,pattern='transport.*'):

        response,newsgroups = self.list()
        newsgroups = [x for x in newsgroups if fnmatch.fnmatch(x[0],pattern)]

        results = {}

        for entry in newsgroups:
            minmsg = int(entry[2])
            maxmsg = int(entry[1])
            nummsg = maxmsg-minmsg+1

            if minmsg==0 or maxmsg<minmsg:
                results[entry[0]] = (minmsg,maxmsg,0)
            else:
                results[entry[0]] = (minmsg,maxmsg,nummsg)

        return results

#########################################################################
#
#   News Client Base
#
#########################################################################

class NewsBase:

    def __init__(self,server,group=None,log=logging,**kw):
        self.server = server
        self.setGroup(group)
        self.setLog(log)

    def setLog(self,func):
        self.log = func

    def setGroup(self,group):
        self.group = group

#########################################################################
#
#   News Poster
#
#########################################################################

class NewsPoster(NewsBase):

    def __init__(self,*args,**kw):
        self.clearHeaders()
        NewsBase.__init__(self,*args,**kw)

        self.setHeader('Subject','no subject')
        self.setHeader('From','transport@transport.sri.com')
        self.setEnable(True)

    def setEnable(self,flag):
        self.enabled = flag

    def clearHeaders(self):
        self.headers = {}

    def setHeader(self,key,value):
        self.headers[key] = value

    def setGroup(self,group):
        NewsBase.setGroup(self,group)
        if self.group:
            self.setHeader('Newsgroups',self.group)

    def addHeaders(self,msg,date=None,headers={}):

        if date:
            msg['X-Transport-Date'] = str(date)

        for key,value in self.headers.items():
            msg[key]=value

        for key,value in headers.items():
            msg[key]=value

    def addFile(self,msg,filename):

        ctype,encoding = mimetypes.guess_type(filename)
        if ctype is None or encoding is not None:
            ctype = 'application/octet-stream'
        maintype,subtype = ctype.split('/',1)
        if maintype=='text':
            fp = open(filename)
            part = MIMEText(fp.read(),_subtype=subtype)
            fp.close()
        elif maintype == 'image':
            fp = open(filename, 'rb')
            part = MIMEImage(fp.read(), _subtype=subtype)
            fp.close()
        elif maintype == 'audio':
            fp = open(filename, 'rb')
            part = MIMEAudio(fp.read(), _subtype=subtype)
            fp.close()
        else:
            fp = open(filename, 'rb')
            part = MIMEBase(maintype, subtype)
            part.set_payload(fp.read())
            fp.close()
            Encoders.encode_base64(part)

        basename = os.path.basename(filename)
        part.add_header('Content-Disposition','attachment',filename=basename)
        msg.attach(part)

    def post(self,filenames=[],text=None,date=None,headers={}):

        if not self.enabled:
            return

        if isinstance(filenames,basestring):
            filenames = [filenames]

        if not filenames:
            msg = MIMEText(text)

        else:
            msg = MIMEMultipart()
            msg.preamble=text
            msg.epilogue=''

            for filename in filenames:
                self.addFile(msg,filename)

        self.addHeaders(msg,date,headers)

        buffer = cStringIO.StringIO()
        Generator(buffer,mangle_from_=False).flatten(msg)

        buffer.seek(0,2)
        numBytes = buffer.tell()
        buffer.seek(0)

        self.server.post(buffer)

        return numBytes

#########################################################################
#
#   News Control
#
#########################################################################

class NewsControl(NewsPoster):

    def __init__(self,*args,**kw):
        NewsPoster.__init__(self,*args,**kw)

        self.setGroup('control')

    def postCommand(self,text):
        self.setHeader('Control',text)
        self.setHeader('Approved',self.headers['From'])

        # Set text to make sure that the body has something in it

        self.post(text=text)

    def newgroup(self,group):
        self.postCommand('newgroup %s' % group)

    def rmgroup(self,group):
        self.postCommand('rmgroup %s' % group)

    def cancelMessage(self,group,messageID):
        self.setGroup(group)
        self.postCommand('cancel %s' % message)
        self.setGroup('control')

    def cancelGroup(self,group):
        response,count,first,last,name = self.server.group(group)
        response,subject = self.server.xhdr('Message-ID',first+'-'+last)

        for articleNumber,messageID in subject:
            self.cancelMessage(group,messageID)

#########################################################################
#
#   News Poller
#
#########################################################################

class NewsPoller(NewsBase):

    def __init__(self,*args,**kw):
        NewsBase.__init__(self,*args,**kw)

        if 'callback' in kw:
            self.setCallback(kw['callback'])

        self.setDebug(False)
        self.setSingleShot(False)
        self.setStopFunc(self.defaultStop)

    def setDebug(self,flag):
        self.debug=flag

    def setCallback(self,func):
        self.callback=func

    def setSingleShot(self,flag):
        self.singleshot=flag

    def setStopFunc(self,func):
        self.stop = func

    def defaultStop(self):
        return False

    def saveLastRead(self,articleNum):
        open(self.group,'w').write(str(articleNum))

    def loadLastRead(self):
        return int(open(self.group).readline())

    def markMessageRead(self,message):
        num = message['XRef'].split(':')[1]
        self.saveLastRead(num)

    def markRead(self,msgcount=1):

        if msgcount==0:
            return

        first,last,count = self.server.queryGroup(self.group)

        try:
            lastid = self.loadLastRead()
        except:
            lastid = first

        if msgcount==1:
            newlast = last
        else:
            newlast = max(lastid,last+msgcount)

        self.log.debug('Marking %d msgs read: %d -> %d' % \
                        (msgcount,lastid,newlast))

        self.saveLastRead(newlast)

    def unreadArticleNums(self):

        try:
            first,last,count = self.server.queryGroup(self.group)
        except:
            self.log.debug('  failed to get article number range')
            return []

        text = 'available messages: %d (%d-%d)' % (count,first,last)

        try:
            nextnum = self.loadLastRead()+1
        except:
            nextnum = first

        if nextnum==0 or nextnum>last:
            self.log.debug('  %s, none are new' % text)
            return []

        if nextnum<first:
            nextnum=first

        if self.singleshot:
            last=nextnum

        nummsgs = last-nextnum+1

        self.log.debug('  %s, %d unread (%d-%d)' % (text,nummsgs,nextnum,last))

        return range(nextnum,last+1)

    def getMessage(self,num):

        self.log.debug('  retrieving article number %s' % num)

        starttime = datetime.datetime.now()

        try:
            article = self.server.article(str(num))[3]
        except nntplib.NNTPTemporaryError,desc:
            self.log.error('Problem retrieving article: %s' % desc)
            code = int(str(desc).split()[0])
            if code==400:
                self.log.error('  retry later')
                raise
            else:
                self.log.error('  skipping')
                return None
        except:
            self.log.exception('Problem retrieving article %s' % num)
            raise

        elapsed = datetime.datetime.now()-starttime

        self.log.info('    - elapsed: %s' % elapsed)

        try:
            return email.message_from_string('\n'.join(article))
        except:
            self.log.exception('Problem parsing message body')
            return None

    def unreadMessages(self):

        for articleNumber in self.unreadArticleNums():

            try:
                msg = self.getMessage(articleNumber)
            except:
                break

            if not msg:
                self.saveLastRead(articleNumber)
                continue

            yield msg


    # These next two methods might be better in client code....

    def processUnreadMessages(self):

        host = '%s:%s' % (self.server.host,self.server.port)

        self.log.debug('Polling %s %s' % (host,self.group))

        for msg in self.unreadMessages():
            self.processMessage(msg)
            self.markMessageRead(msg)

            if self.stop():
                break

        self.log.debug('End of polling cycle')

    def processMessage(self,msg):

        try:
            self.callback(msg)
        except:
            self.log.error('Problem in the callback function')

            if self.debug:
                raise


