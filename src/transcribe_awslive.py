#!/usr/bin/env python

import io, os, argparse
import boto3
import websockets, asyncio
import datetime, time
import hashlib, hmac, base64, urllib.parse, binascii
from struct import pack, unpack_from 
import json


def HashSHA256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def sign(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def getSignatureKey(key, dateStamp, regionName, serviceName):
    kDate = sign(('AWS4' + key).encode('utf-8'), dateStamp)
    kRegion = sign(kDate, regionName)
    kService = sign(kRegion, serviceName)
    kSigning = sign(kService, 'aws4_request')
    return kSigning

def create_request_url(region="us-east-1", access_key=None, secret_key=None, debug=False):
    assert access_key != None and secret_key != None

    method = "GET"
    service = "transcribe"
    host = "transcribestreaming.%s.amazonaws.com:8443" % region
    endpoint = "https://%s" % host
    t = datetime.datetime.utcnow()
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    datestamp = t.strftime('%Y%m%d')
    canonical_uri = "/stream-transcription-websocket"
    canonical_headers = "host:" + host + "\n"
    signed_headers = "host"                        
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = datestamp + "/" + region + "/" + service + "/" + "aws4_request"

    canonical_querystring  = "X-Amz-Algorithm=" + algorithm
    canonical_querystring += "&X-Amz-Credential=" + urllib.parse.quote_plus(access_key + "/" + credential_scope)
    canonical_querystring += "&X-Amz-Date=" + amz_date 
    canonical_querystring += "&X-Amz-Expires=300"
    canonical_querystring += "&X-Amz-SignedHeaders=" + signed_headers
    canonical_querystring += "&language-code=en-US&media-encoding=pcm&sample-rate=16000"

    payload_hash = HashSHA256("")

    canonical_request = method + '\n'
    canonical_request += canonical_uri + '\n' 
    canonical_request += canonical_querystring + '\n' 
    canonical_request += canonical_headers + '\n' 
    canonical_request += signed_headers + '\n' 
    canonical_request += payload_hash

    if debug: print("\ncanonical_request:\n%s\n" % canonical_request)

    string_to_sign = algorithm + "\n"
    string_to_sign += amz_date + "\n"
    string_to_sign += credential_scope + "\n"
    string_to_sign += HashSHA256(canonical_request)

    if debug: print("\nstring_to_sign:\n%s\n" % string_to_sign)

    signing_key = getSignatureKey(secret_key, datestamp, region, service)
    signature = hmac.new(signing_key, (string_to_sign).encode('utf-8'), hashlib.sha256).hexdigest()

    canonical_querystring += "&X-Amz-Signature=" + signature
    request_url = endpoint + canonical_uri + "?" + canonical_querystring

    return request_url

def wrap_audio_chunk(chunk):
    headers = b''
    headers += pack('!B13sBH24s', 13,  bytes(':content-type', 'utf-8'), 7, 24, bytes('application/octet-stream', 'utf-8'))
    headers += pack('!B11sBH10s', 11,  bytes(':event-type', 'utf-8'), 7, 10, bytes('AudioEvent', 'utf-8'))
    headers += pack('!B13sBH5s',  13,  bytes(':message-type', 'utf-8'), 7, 5, bytes('event', 'utf-8'))

    headers_len = len(headers)
    audio_len = len(chunk)
    others_len = 3*4 + 4 
    total_len = others_len + headers_len + audio_len

    prelude = pack('!II', total_len, headers_len)
    prelude_crc = pack('!I', binascii.crc32(prelude))

    message = prelude + prelude_crc + headers + chunk
    message_crc = pack('!I', binascii.crc32(message))
    message_complete = message + message_crc

    return message_complete

def unwrap_response(response_bin):
    header_len = unpack_from("!I", response_bin, 4)[0]
    json_bin = response_bin[3*4+header_len:-4]
    return json.loads(json_bin)



def delay_generator(content, delay_ms=0):
    for chunk in content:
        yield chunk
        time.sleep(delay_ms/1000)


async def handle_stream_reader(websocket, debug=True):
    rx_complete_messages = {'messages': []}
    try:
        while True:
            rx_message = await websocket.recv()
            rx_message = unwrap_response(rx_message) 
            results = rx_message['Transcript']['Results']
            for r in results: 
                if not r['IsPartial'] :
                    rx_complete_messages['messages'].append(r)
            if debug: print("Received: %s" % rx_message)
    except websockets.exceptions.ConnectionClosedOK:
        return rx_complete_messages


async def handle_stream(url, data, ws_debug=False, debug=True):
    if ws_debug:
        import logging
        logger = logging.getLogger('websockets')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler())

    ws_url = url.replace('https://', 'wss://')
    if debug: print('ws_url: %s' % ws_url)
    async with websockets.connect(ws_url) as websocket:
        loop = asyncio.get_event_loop()
        read_task = loop.create_task(handle_stream_reader(websocket))

        for chunk in data:
            if debug: print("Chunk len: %d" % len(chunk))
            await websocket.send(wrap_audio_chunk(chunk))
        if debug: print("Sending empty chunk")
        await websocket.send(wrap_audio_chunk(b''))

        transcription_json = await read_task
        print("transcription_json: %s" % transcription_json)

 


def streaming_recognize(url, data):
    results = []
    asyncio.get_event_loop().run_until_complete(handle_stream(url, data))
    return results


def transcribe_streaming_from_file(stream_file, verbose=True, **kwargs):
    """Streams transcription of the given audio file."""
    with io.open(stream_file, 'rb') as audio_file:
        content = audio_file.read()

    return transcribe_streaming_from_data(content, verbose=verbose, **kwargs)


def transcribe_streaming_from_data(content, 
        chunk_size=8*1024, sample_rate_hertz=16000, audio_sample_size=2, realtime=False, verbose=True,
        access_key=None, secret_key=None):

    assert audio_sample_size==2

    # In practice, stream should be a generator yielding chunks of audio data.
    #stream = [content]
    
    if realtime: 
        stream = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    else:
        stream = [content]

    requests = (chunk for chunk in stream)

    # streaming_recognize returns a generator.
    delay_ms = 0
    if realtime: 
        delay_ms = 1000 / (sample_rate_hertz * audio_sample_size / chunk_size)
        requests = delay_generator(requests, delay_ms=delay_ms)

    
    ### responses = client.streaming_recognize(streaming_config, delay_generator(requests, delay_ms=delay_ms) )
    url = create_request_url(access_key=access_key, secret_key=secret_key)
    responses = streaming_recognize(url, requests)

    transcript = ""
    for response in responses:
        # Once the transcription has settled, the first result will contain the
        # is_final result. The other results will be for subsequent portions of
        # the audio.
        for result in response.results:
            if verbose:
                print('Finished: {}'.format(result.is_final))
                print('Stability: {}'.format(result.stability))
            
            # The alternatives are ordered from most likely to least.
            alternatives = result.alternatives
            if result.is_final: 
                transcript += alternatives[0].transcript.strip() + " "

            for alternative in alternatives:
                if verbose:
                    print('Confidence: {}'.format(alternative.confidence))
                    print(u'Transcript: {}'.format(alternative.transcript))
    return transcript, {}



if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('stream', help='File to stream to the API')
    args = parser.parse_args()
    access_key = os.environ['AWS_ACCESS_KEY_ID']
    secret_key = os.environ['AWS_SECRET_ACCESS_KEY']
    transcribe_streaming_from_file(args.stream, access_key=access_key, secret_key=secret_key, verbose=True, realtime=True)