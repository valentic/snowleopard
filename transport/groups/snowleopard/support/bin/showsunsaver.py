#!/usr/bin/env python

import sys
sys.path.append('/opt/transport/groups/snowleopard/support/lib')

from directory import Directory
import sunsaver
import time
import md5
import pprint

directory = Directory()
cache = directory.connect('cache')

prevResults = None

while True:

    try:
        data = cache.get('sunsaver')
    except:
        continue
    finally:
        time.sleep(1)

    curResults = md5.new(str(data)).hexdigest()

    if prevResults!=curResults:
        results = sunsaver.Parse(data)
        print '-'*70
        print time.ctime()
        print '-'*70
        pprint.pprint(results)
        print '-'*70
        print

        prevResults=curResults
