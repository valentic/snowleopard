#!/usr/bin/python

#####################################################################
#   HF Receiver
#
#   2016-07-14  Todd Valentic
#               Initial implementation
#
#   2016-07-28  Todd Valentic
#               Specify frequency in MHz (still stored as Hz)
#
#####################################################################

from gnuradio import blocks
from gnuradio import eng_notation
from gnuradio import gr
from gnuradio import uhd
from gnuradio.eng_option import eng_option
from gnuradio.filter import firdes
from optparse import OptionParser
import time
import sys
import signal
import struct

VERSION = 1
running = True

def SignalHandler(signum,frame):
    global running
    print 'Signal received'
    running = False

#signal.signal(signal.SIGINT,    SignalHandler)
#signal.signal(signal.SIGTERM,   SignalHandler)
#signal.signal(signal.SIGHUP,    SignalHandler)

class top_block(gr.top_block):

    def __init__(self,options):
        gr.top_block.__init__(self, "HF-RX")

        self.writeHeader(options)

        self.usrp_source = uhd.usrp_source(
        	",".join(("addr=192.168.11.2", "")),
        	uhd.stream_args(
        		cpu_format="sc16",
        		channels=range(1),
        	),
        )

        self.usrp_source.set_clock_source("gpsdo", 0)
        self.usrp_source.set_time_source("gpsdo", 0)

        self.usrp_source.set_samp_rate(options.sample_rate)
        self.usrp_source.set_center_freq(options.frequency, 0)
        self.usrp_source.set_gain(options.gain, 0)

        if options.antenna:
            self.usrp_source.set_antenna(options.antenna, 0)

        self.file_sink = blocks.file_sink(gr.sizeof_int*1, options.filename, True)
        self.file_sink.set_unbuffered(False)

        if options.nsamples:
            self.head = blocks.head(gr.sizeof_int, int(options.nsamples)*2)
            self.connect(self.usrp_source, self.head, self.file_sink)
        else:
            self.connect(self.usrp_source, self.file_sink)

    def writeHeader(self,options):
        output = open(options.filename,'wb')
        output.write(struct.pack('!B',VERSION))
        output.write(struct.pack('!i',time.time()))
        output.write(struct.pack('!f',options.frequency))
        output.write(struct.pack('!f',options.sample_rate))
        output.write(struct.pack('!f',options.gain))
        output.close()

def get_options():

    parser = OptionParser(option_class=eng_option)
    parser.add_option("-x", "--gain", type="eng_float", default=20,
                      help="set gain [default=20]")
    parser.add_option("-f", "--frequency", type="eng_float", default=10.0,
                      help="set transmit frequency (MHz) [default=10.0]")
    # On USRP2, the sample rate should lead to an even decimator
    # based on the 100 MHz clock.  At 2.5 MHz, we end up with 40
    parser.add_option("-s", "--sample-rate", type="eng_float", default=250000,
                      help="set sample rate [default=250000]")
    parser.add_option("-t", "--filename", type="string", default="dat.bin",
                      help="set output file name [default=dat.bin]")
    parser.add_option("-a", "--antenna", type="string", default=None,
                      help="set antenna [default=None]")
    parser.add_option("-N", "--nsamples", type="eng_float", default=None,
                      help="number of samples to collect [default=+inf]")

    (options, args) = parser.parse_args()

    if len(args) != 0:
        parser.print_help()
        raise SystemExit, 1

    options.frequency *= 1e6

    return (options)

if __name__ == '__main__':

    (options) = get_options()
    tb = top_block(options)

    try:
        tb.run()
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(1)
        pass

#    tb.start()
#
#    while running:
#        time.sleep(1)
#
#    tb.stop()
