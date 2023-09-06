#!/usr/bin/env python

#########################################################################
#
#   RUDICS Bridge Server Packet
#
#   2007-12-15  Todd Valentic
#               Initial implementation.
#
#   2010-03-08  Todd Valentic
#               Remove unused md5 and base64 imports.
#               Remove compress parameter - always try compression.
#
#########################################################################

import bz2
import struct
import crc16

# Packet types

class Type:
    SYN         = 0
    SYNACK      = 1
    SYNACKACK   = 2
    ACK         = 3
    DATA        = 4
    DATACMP     = 5
    FIN         = 6

TypeDesc = {
    Type.SYN:        'SYN',
    Type.SYNACK:     'SYNACK',
    Type.SYNACKACK:  'SYNACKACK',
    Type.ACK:        'ACK',
    Type.DATA:       'DATA',
    Type.DATACMP:    'DATACMP',
    Type.FIN:        'FIN'
    }

def hexdump(data,filename):
    output = open(filename,'w')
    ascii = ''
    for pos,byte in enumerate(data):
        if pos%16==0:
            print >> output,'  ',ascii
            print >> output,'%05d:' % pos,
            ascii=''
        print >> output,'%02X' % ord(byte),
        if ord(byte)<32 or ord(byte)>127:
            ascii+='.'
        else:
            ascii+=byte
    output.close()

def fromstring(input,log):

    log.debug('parsing string')

    start = input.find(chr(0xAA))
    if start<0:
        log.debug('  - no sync found')
        return None,''

    input = input[start:]

    headerfmt = '!BBBHHB'
    headerlen = struct.calcsize(headerfmt)

    if len(input)<headerlen:
        log.debug('  - header too short')
        return None,input

    sync,ptype,seq,id,numbytes,xor = struct.unpack(headerfmt,input[:headerlen])

    try:
        pdesc = TypeDesc[ptype]
    except:
        pdesc = 'Unknown'

    log.debug('  sync: %0X' % sync)
    log.debug('  type: %s (%0X)' % (pdesc,ptype))
    log.debug('  seq : %0X' % seq)
    log.debug('  id:   %0X' % id)
    log.debug('  len : %d'  % numbytes)
    log.debug('  xor : %0X' % xor)

    test=0
    for c in input[:headerlen]:
        test^=ord(c)

    if test!=0:
        log.debug('header checksum failed')
        return None,input[1:]

    bodyfmt ='!%dsH' % numbytes
    bodylen = struct.calcsize(bodyfmt)
    end=headerlen+numbytes+2

    log.debug('  body len: %d' % bodylen)
    log.debug('  end: %d' % end)
    log.debug('  len(input): %d' % len(input))

    if len(input)<end:
        log.debug('  - body too short. expecting %d bytes, got %d' % \
            (end,len(input)))
        return None,input

    data,checksum = struct.unpack(bodyfmt,input[headerlen:end])

    if checksum==crc16.crc16(data):
        log.debug('  - message is good')
        return Packet(ptype,seq,id,data),input[end:]
    else:
        log.debug('  - checksum error')
        return None,input[1:]

class Packet:

    def __init__(self,ptype,seq,id,data=''):

        # Try to compress data - for small lists, the compressed
        # version might actually be larger. In these cases, keep
        # the data umcompressed.

        if ptype==Type.DATA:
            zdata = bz2.compress(data)
            if len(zdata)<len(data):
                ptype = Type.DATACMP
                data = zdata

        self.type   = ptype
        self.seq    = seq
        self.data   = data
        self.id     = id
        self.key    = (id,seq)

        self.makeFrame()

    def makeFrame(self):

        self.checksum = crc16.crc16(self.data)

        headerfmt = '!BBBHH'
        header = struct.pack(headerfmt,0xAA,self.type,
                                self.seq,self.id,len(self.data))

        xor=0
        for c in header:
            xor^=ord(c)

        fmt='!%dsB%dsH' % (struct.calcsize(headerfmt),len(self.data))
        self.frame  = struct.pack(fmt,header,xor,self.data,self.checksum)

    def getPayload(self):
        if self.type==Type.DATACMP:
            return bz2.decompress(self.data)
        else:
            return self.data

    def print_key(self):
        return '(%04X, %02X)' % (self.id,self.seq)

    def __str__(self):
        result = []
        try:
            result.append(TypeDesc[self.type])
        except:
            result.append('????')
        result.append('%02X' % self.seq)
        result.append('%04X' % self.id)
        result.append('%04X' % len(self.data))

        output=''
        for c in self.data[:16]:
            if ord(c)>31 and ord(c)<127:
                output+=c
            else:
                output += '<%02X>' % ord(c)

        if len(self.data)>16:
            output+='...'

        result.append('"%s"' % output)
        result.append('%04X' % self.checksum)

        return ' '.join(result)

    def __cmp__(self,other):
        windowSize=256
        n = other.seq-self.seq
        if n<0:
            n+=windowSize

        if n==0:
            return 0
        elif n<=windowSize/2:
            return -1
        else:
            return 1

def ACK(*arg,**kw):       return Packet(Type.ACK,*arg,**kw)
def SYN(*arg,**kw):       return Packet(Type.SYN,*arg,**kw)
def SYNACK(*arg,**kw):    return Packet(Type.SYNACK,*arg,**kw)
def SYNACKACK(*arg,**kw): return Packet(Type.SYNACKACK,*arg,**kw)
def DATA(*arg,**kw):      return Packet(Type.DATA,*arg,**kw)
def DATACMP(*arg,**kw):   return Packet(Type.DATACMP,*arg,**kw)
def FIN(*arg,**kw):       return Packet(Type.FIN,*arg,**kw)

if __name__ == '__main__':

    print DATA(100,9080,"Hello world")

