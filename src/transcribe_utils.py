#!/usr/bin/env python

import time

def delay_generator(content, delay_ms=0):
    for chunk in content:
        yield chunk
        time.sleep(delay_ms/1000.0)


