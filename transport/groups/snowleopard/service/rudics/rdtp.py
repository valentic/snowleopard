#!/usr/bin/env python

############################################################################
#
#   RUDICS Data Transport Protocol (RDTP)
#
#   RDTP implements a means to allow remote clients to access TCP services
#   such as web (HTTP), news (NNTP) and email (SMTP) over a single connection.
#   The common use is to tunnel these services over an Iridium/RUDICS
#   satellite link.
#
#   Each service that is to be tunneled is proxied on the remote side.
#   When a user connects to the proxied port, a ProtocolHandler object
#   is created to manage the connection. Data bytes are read from the
#   socket and formed into packets, which are sent to the remote side
#   via the Mux objects. The Mux can handle multiple streams and
#   multiplexes/demultiplexes them onto the link. A corresponding
#   ProtocolHandler is created on the other side to handle the other
#   end of the connection. When either side (or the connection between
#   the Mux objects) is closed, the ProtocolHandlers are removed.
#   When no streams are present, the Mux drops the connection to the
#   other mux as well.
#
#   This code uses a modified version of the Python standard library's
#   asyncore module. It adds timers to the set of functions.
#
#   =============== Remote ===========        ======= Server ===============
#
#    ------     ---------------+-----          -----+----------------
#   | user |<->|ProtocolHandler|     |        |     |ProtocolHandler |<->NNTP
#    ------    |---------------|     |        |     |----------------|
#              |ProtocolHandler| Mux |<~~//~~>| Mux |ProtocolHandler |
#              |---------------|     |        |     |----------------|
#              |ProtocolHandler|     |        |     |ProtocolHandler |
#               ---------------+-----          -----+----------------
#
#
#   Initial connection sequence
#   ==================================================================
#
#   Client seq=100, next=unknown
#   Server seq=300, next=unknown
#
#                Client                          Server
#   ------------------------------     -----------------------------
#   State       Function    W  R         R  W   Function    State
#
#   CLOSED                                                  CLOSED
#               send_syn()
#                - Send SYN(seq)
#
#   SENT_SYN               SYN(100) ==>         packet_syn()
#                                                - set next=100
#                                                - send SYNACK(seq)
#                                                - connect to service
#
#               packet_synack()     <==  SYNACK(300)[100]   SENT_SYNACK
#                - set next=300
#                - send SYNACKACK
#
#   ESTABLISHED      SYNACKACK(101) ==>         packet_synack()
#                                                - send ACK
#
#                                   <== ACK(301)            ESTABLISHED
#
#   Client seq=102, next=302
#   Server seq=302, next=102
#
#   ==================================================================
#
#
#
#   2008-01-23  Todd Valentic
#               Initial implementation
#
#   2008-08-12  Todd Valentic
#               Increase resend timeout to 3 minutes.
#
#   2009-11-09  Todd Valentic
#               Have server print "Open" on connect to handle SIM
#               cards that do not send "Trying ... Open".
#
#   2010-01-21  Todd Valentic
#               Disable packet resending (not really needed on Iridium
#                   links and causing more harm than good when the link
#                   is very slow).
#
#   2010-03-08  Todd Valentic
#               The interface to asynchat.async_chat.__init__, changed
#               at python 2.6+. It used to have a parameter named conn
#               and now has one name sock. To make compatible with all
#               versions, just pass it in as a positional parameter
#               instead of named one.
#
#   2010-03-10  Todd Valentic
#               Code clean up and fix the lockup errors when the
#                   server-side service is either not available or
#                   if it closes the connection. Use the Python 2.6
#                   version of asycore (local copy) patched to support
#                   timer functions.
#
############################################################################

import asyncore
import asynchat
import socket
import logging
import heapq
import random
import traceback

import Packet

STATE_CLOSED            = 0
STATE_SENT_SYN          = 1
STATE_SENT_SYNACK       = 2
STATE_SENT_SYNACKACK    = 3
STATE_ESTABLISHED       = 4

class PacketProducer:

    def __init__(self,packet,buffer_size=512):
        self.data = packet.frame
        self.buffer_size = 512

    def more(self):
        if len(self.data) > self.buffer_size:
            result = self.data[:self.buffer_size]
            self.data = self.data[self.buffer_size:]
        else:
            result = self.data
            self.data = ''

        return result

class ProtocolHandler(asynchat.async_chat):

    # If conn is set, this handles a client connection
    # If addr is set, this connects to a service

    def __init__(self,mux,id,conn=None,addr=None,log=logging):
        asynchat.async_chat.__init__(self,conn)

        self.log = log

        if addr:
            self.addr = addr
            self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connect(addr)

        self.id                 = id
        self.mux                = mux
        self.seq                = random.randint(0,256)
        self.rxseq              = 0
        self.state              = STATE_CLOSED
        self.inflight           = []
        self.incoming           = []
        self.buffer             = ''
        self.timeout            = 0.1
        self.max_packet_size    = 15*1024
        self.input_timer        = None

        self.mux.register(self)
        heapq.heapify(self.incoming)

        self.handler_map = {
            Packet.Type.ACK:        self.handle_ack,
            Packet.Type.SYN:        self.handle_syn,
            Packet.Type.SYNACK:     self.handle_synack,
            Packet.Type.SYNACKACK:  self.handle_synackack,
            Packet.Type.DATA:       self.handle_data,
            Packet.Type.DATACMP:    self.handle_data,
            Packet.Type.FIN:        self.handle_fin
            }

        self.set_terminator(None)

    def info(self,msg):
        self.log.info('[%04X] %s' % (self.id,msg))

    def error(self,msg):
        self.log.error('[%04X] %s' % (self.id,msg))

    def increment(self,seq):
        return (seq+1)%256

    def next_seq(self):
        self.seq = self.increment(self.seq)
        return self.seq

    def readable(self):
        return self.state==STATE_ESTABLISHED

    def send_packet(self,packet):
        self.info('R<== %s' % packet)
        self.inflight.append(packet.key)
        self.mux.send_packet(packet)

    def collect_incoming_data(self,data):
        self.info('C==> [%d] %s...' % (len(data),repr(data[:16])))
        self.buffer+=data
        self.mux.update_bytes_in(len(data))

        if self.input_timer:
            self.input_timer.reset()
        else:
            self.input_timer = asyncore.call_later(self.timeout,self.flush_input)

    def found_terminator(self):

        if self.buffer and self.state==STATE_ESTABLISHED:
            packet = Packet.DATA(self.next_seq(),self.id,self.buffer)
            self.send_packet(packet)
            self.set_terminator(self.max_packet_size)
            self.buffer=''

    def flush_input(self):
        self.found_terminator()
        self.input_timer = None

    def handle_ack(self,packet):
        if packet.key in self.inflight:
            self.inflight.remove(packet.key)
            self.info('Packet %s landed, remaining: %s' % \
                        (packet.print_key(),len(self.inflight)))
        else:
            self.info('Packet %s not inflight' % packet.print_key())

    def handle_packet(self,packet):
        self.handler_map[packet.type](packet)

    def handle_connect(self):
        self.info('Connecting to %s' % str(self.addr))

    def send_syn(self,dest):
        syn = Packet.SYN(self.next_seq(),self.id,dest)
        self.send_packet(syn)
        self.state=STATE_SENT_SYN

    def handle_syn(self,packet):
        self.rxseq = self.increment(packet.seq)
        synack = Packet.SYNACK(self.seq,packet.id,chr(packet.seq))
        self.send_packet(synack)
        self.state=STATE_SENT_SYNACK

    def handle_synack(self,packet):

        if self.state == STATE_SENT_SYN:
            self.rxseq = self.increment(packet.seq)
            packet.seq = ord(packet.data[0])
            packet.key = (packet.id,packet.seq)
            self.handle_ack(packet)
            synackack = Packet.SYNACKACK(self.next_seq(),self.id)
            self.send_packet(synackack)
            self.state = STATE_SENT_SYNACKACK

    def handle_synackack(self,packet):

        if self.state==STATE_SENT_SYNACK:
            self.rxseq = self.increment(packet.seq)
            self.state=STATE_ESTABLISHED

    def handle_data(self,packet):

        if packet.seq>=self.rxseq and self.state==STATE_SENT_SYNACKACK:
            ack=Packet.Packet(Packet.Type.SYNACKACK,self.seq,self.id)
            self.handle_ack(ack)
            self.state=STATE_ESTABLISHED

        if self.state==STATE_ESTABLISHED:

            seq = packet.seq
            if seq<self.rxseq:
                seq+=256
            if seq>=self.rxseq and seq<self.rxseq+100:
                heapq.heappush(self.incoming,packet)
            else:
                self.error('Packet outside of window')
        else:
            self.info('Duplicate packet')

        ack = Packet.ACK(packet.seq,self.id)
        self.send_packet(ack)

        while self.incoming and self.incoming[0].seq==self.rxseq:
            packet = heapq.heappop(self.incoming)
            data = packet.getPayload()
            self.info('C<== [%d] %s' % (len(data),repr(data[:16])))
            self.push(data)
            self.mux.update_bytes_out(len(data))
            self.rxseq=self.increment(self.rxseq)

    def handle_error(self):
        #self.error('error: %s' % traceback.format_exc())
        self.handle_close()

    def handle_close(self,sendfin=True):
        if not self.state==STATE_CLOSED:
            self.info('Closing')
            self.found_terminator()
            if sendfin:
                fin = Packet.FIN(self.next_seq(),self.id)
                self.send_packet(fin)
            self.clear_timeouts()
            self.close_when_done()
            self.mux.unregister(self)
            self.state=STATE_CLOSED

    def handle_fin(self,packet):
        self.info('Remote side closed')
        self.clear_timeouts()
        self.close()
        self.mux.unregister(self)
        self.state=STATE_CLOSED

    def clear_timeouts(self):

        if self.input_timer and self.input_timer.active():
            self.input_timer.cancel()

class ClientListener(asyncore.dispatcher):

    def __init__(self,localport,remoteaddr,mux):
        asyncore.dispatcher.__init__(self)

        self.remoteaddr = remoteaddr
        self.mux = mux
        self.log = mux.log

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('',localport))
        self.listen(5)

        self.log.info('CL: Listening on %s' % localport)

    def handle_accept(self):
        conn,addr = self.accept()
        handler = ProtocolHandler(self.mux,addr[1],conn=conn,log=self.log)
        handler.send_syn(self.remoteaddr)

class Mux(asynchat.async_chat):

    def __init__(self,addr,conn=None,portmap=None,log=logging):
        asynchat.async_chat.__init__(self,conn)

        self.buffer = ''
        self.clients = {}
        self.addr = addr
        self.log = log

        self.bytes_in = 0
        self.bytes_out = 0
        self.packets_in = 0
        self.packets_out = 0
        self.packets_bytes_in = 0
        self.packets_bytes_out = 0

        if conn:
            self.manageConnection = False
        else:
            self.manageConnection = True

        self.set_terminator(None)

        if portmap:
            for localport,remoteaddr in portmap.items():
                ClientListener(localport,remoteaddr,self)

    def info(self,msg):
        self.log.info('Mux: %s' % msg)

    def error(self,msg):
        self.log.error('Mux: %s' % msg)

    def register(self,client):
        self.clients[client.id]=client

        if self.manageConnection and not self.connected:
            self.info('Bringing up external connection')
            self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
            self.set_reuse_addr()
            self.connect(self.addr)
            self.online=True

    def unregister(self,client):
        if client.id in self.clients:
            del self.clients[client.id]
        self.info('Unregistering %04X' % client.id)
        if self.clients:
            self.info('Remaining clients:')
            for id in self.clients:
                self.info('  %04X' % id)
        else:
            self.info('No remaining clients')
            if self.manageConnection and self.connected:
                self.info('Dropping external connection')
                self.close()

    def update_bytes_in(self,num):
        self.bytes_in+=num

    def update_bytes_out(self,num):
        self.bytes_out+=num

    def send_packet(self,packet):
        self.packets_out+=1
        self.packets_bytes_out+=len(packet.frame)
        self.push_with_producer(PacketProducer(packet))

    def handle_error(self):
        #self.error('error: %s' % traceback.format_exc())
        self.handle_close()

    def handle_connect(self):
        self.info('Connected to %s' % str(self.addr))

    def handle_close(self):
        self.info('Lost external connection')
        for client in self.clients.values():
            client.handle_close(sendfin=False)
        self.close()

    def collect_incoming_data(self,data):

        self.buffer = self.buffer+data

        #self.info('collect: %s' % repr(data))

        while self.buffer:
            packet,self.buffer = Packet.fromstring(self.buffer,self.log)
            if packet:
                self.info('R==> %s' % packet)
                self.packets_in+=1
                self.packets_bytes_in+=len(packet.frame)
                self.handle_packet(packet)
            else:
                break

    def handle_packet(self,packet):

        if packet.type==Packet.Type.SYN and packet.id not in self.clients:
            self.info('Received SYN for new tunnel')
            self.create_handler(packet)

        if packet.id in self.clients:
            self.clients[packet.id].handle_packet(packet)

    def create_handler(self,packet):

        try:
            host,port = packet.data.split(':')
            addr = (host,int(port))
        except:
            self.error('Problem parsing address: %s' % packet.data)
            return

        ProtocolHandler(self,packet.id,addr=addr,log=self.log)

    def print_stats(self):
        self.info('Statistics:')
        self.info('  bytes in:             %s' % self.bytes_in)
        self.info('  bytes out:            %s' % self.bytes_out)
        self.info('  packets in:           %s' % self.packets_in)
        self.info('  packets out:          %s' % self.packets_out)
        self.info('  packets bytes in:     %s' % self.packets_bytes_in)
        self.info('  packets bytes out:    %s' % self.packets_bytes_out)

class Client:

    def __init__(self,port,host='',portmap=None,log=logging):
        self.mux = Mux((host,port),portmap=portmap,log=log)

class Server(asyncore.dispatcher):

    def __init__(self,port,portmap=None,log=logging):
        asyncore.dispatcher.__init__(self)

        self.portmap = portmap
        self.log = log

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('',port))
        self.listen(5)

    def handle_accept(self):
        conn,addr = self.accept()
        self.log.info('Incoming connection from %s' % str(addr))
        self.mux = Mux(addr,conn=conn,portmap=self.portmap,log=self.log)
        self.mux.send('Open')

