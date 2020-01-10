#!/usr/bin/env python

import io, os, argparse
import datetime, time
import json
from transcribe_utils import delay_generator

from ibm_watson import SpeechToTextV1
from ibm_watson.websocket import RecognizeCallback, AudioSource
from threading import Thread
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

try:
    from Queue import Queue, Full
except ImportError:
    from queue import Queue, Full

class IbmLiveRecognizeCallback(RecognizeCallback):
    messages = []
    start_time = 0
    debug = False
    def __init__(self, debug=False):
        RecognizeCallback.__init__(self)
        self.debug = debug
    
    def on_data(self, data):
        if self.debug : print("data: %s" % data)
        data = data.copy()
        data['latency'] = time.time() - self.start_time
        self.messages.append(data)

    def on_transcription(self, transcript):
        if self.debug : print('transcript: %s' % transcript)

    def on_connected(self):
        if self.debug: print('Connection was successful')
        assert self.start_time <= 0
        self.start_time = time.time()

    def on_error(self, error):
        if self.debug: print('Error received: {}'.format(error))
        assert True

    def on_inactivity_timeout(self, error):
        if self.debug: print('Inactivity timeout: {}'.format(error))
        assert True

    def on_listening(self):
        if self.debug: print('Service is listening')

    def on_hypothesis(self, hypothesis):
        if self.debug: print("hypothesis: %s" % hypothesis)

    def on_close(self):
        if self.debug: print("Connection closed")

def recognize_thread_proc(speech_to_text_engine=None, **kwargs):
    speech_to_text_engine.recognize_using_websocket(
        content_type='audio/l16; rate=16000',
        interim_results=True,
        max_alternatives=1,
        **kwargs)

def streaming_recognize(data, password=None, audio_maxsize=1024*1024):
    authenticator = IAMAuthenticator(password)
    speech_to_text_engine = SpeechToTextV1(authenticator=authenticator)

    audio_queue = Queue(maxsize=audio_maxsize)
    audio_source = AudioSource(audio_queue, True, True)
    mycallback = IbmLiveRecognizeCallback(debug=True)

    try:
        recognize_thread = Thread(
            target=recognize_thread_proc, 
            kwargs={
                'speech_to_text_engine': speech_to_text_engine,
                'audio': audio_source,
                'recognize_callback': mycallback
            })
        recognize_thread.start()

        for chunk in data:
            audio_queue.put(chunk)
        audio_source.completed_recording()
        recognize_thread.join(30.0)
        assert not recognize_thread.is_alive()
    except Exception as e:
        raise
    finally:
        audio_source.completed_recording()


    #ws_url = 'wss://api.%s.speech-to-text.watson.cloud.ibm.com/instances/%s/v1/recognize' % ('us-south', instance_id) 
    #end_of_phrase_silence_time
    #interim_results=true
    results = []
    #results = asyncio.get_event_loop().run_until_complete(handle_stream(data))
    return results


def transcribe_streaming_from_file(stream_file, verbose=False, **kwargs):
    """Streams transcription of the given audio file."""
    with io.open(stream_file, 'rb') as audio_file:
        content = audio_file.read()

    content = content
    return transcribe_streaming_from_data(content, verbose=verbose, **kwargs)


def transcribe_streaming_from_data(content, 
        chunk_size=8*1024, sample_rate_hertz=16000, audio_sample_size=2, 
        realtime=False, verbose=False,
        password=None):

    assert audio_sample_size==2

    # In practice, stream should be a generator yielding chunks of audio data.
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

    responses = streaming_recognize(requests, password=password)

    transcript = ""
    first_latency = -1
    for response in responses:
        #if len(response['Transcript']['Results']) > 0 :
        #    if verbose: print('result latency: %f' % response['latency']) 
        #    if first_latency < 0 :
        #        first_latency = response['latency']

        for utterance in result["results"]:
            if "alternatives" not in utterance: raise UnknownValueError()
            for hypothesis in utterance["alternatives"]:
                if verbose: print(hypothesis)
                if "transcript" in hypothesis:
                    transcript += hypothesis["transcript"]

    if verbose:  print('first_latency: %f' % first_latency) 
    transcript_json = {'first_latency': first_latency, 'responses':responses}
    return transcript, transcript_json


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('stream', help='File to stream to the API')
    args = parser.parse_args()
    password = os.environ['IBM_PASSWORD']
    transcript, transcript_json = transcribe_streaming_from_file(
        args.stream, password=password,
        verbose=True, realtime=True)
    print(transcript_json)
    print(transcript)
