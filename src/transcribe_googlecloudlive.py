#!/usr/bin/env python

import argparse
import io
from google.cloud import speech
from google.cloud.speech import enums
from google.cloud.speech import types
import time

def delay_generator(content, delay_ms=0):
    for chunk in content:
        yield chunk
        time.sleep(delay_ms/1000)

def transcribe_streaming_from_file(stream_file, verbose=True):
    """Streams transcription of the given audio file."""
    with io.open(stream_file, 'rb') as audio_file:
        content = audio_file.read()

    return transcribe_streaming_from_data(content, verbose)


def transcribe_streaming_from_data(content, chunk_size=4*1024, sample_rate_hertz=16000, audio_sample_size=2, realtime=False, verbose=True):

    assert audio_sample_size==2

    client = speech.SpeechClient()

    # In practice, stream should be a generator yielding chunks of audio data.
    #stream = [content]
    
    if realtime: 
        stream = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    else:
        stream = [content]

    requests = (types.StreamingRecognizeRequest(audio_content=chunk)
                for chunk in stream)

    config = types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sample_rate_hertz,
        language_code='en-US',
        max_alternatives=1,
        enable_automatic_punctuation=True)
    streaming_config = types.StreamingRecognitionConfig(
        config=config,
        interim_results=True,
        single_utterance=False)

    # streaming_recognize returns a generator.
    delay_ms = 0
    if realtime: delay_ms = 1000 / (sample_rate_hertz * audio_sample_size / chunk_size)
    responses = client.streaming_recognize(streaming_config, delay_generator(requests, delay_ms=delay_ms) )

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
    transcribe_streaming_from_file(args.stream, verbose=True)