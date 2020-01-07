#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
export GOOGLE_APPLICATION_CREDENTIALS="${DIR}/Transcriber-134d5988de26.json"

exec /usr/bin/env python3 -u benchmark.py