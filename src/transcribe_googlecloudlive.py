#!/usr/bin/env python

import argparse
import io
from google.cloud import speech
from google.cloud.speech import enums
from google.cloud.speech import types
import time
from transcribe_utils import delay_generator
from google.protobuf.json_format import MessageToDict


def transcribe_streaming_from_file(stream_file, verbose=True, **kwargs):
    """Streams transcription of the given audio file."""
    with io.open(stream_file, 'rb') as audio_file:
        content = audio_file.read()

    return transcribe_streaming_from_data(content, verbose, **kwargs)


def transcribe_streaming_from_data(content, 
        chunk_size=4*1024, sample_rate_hertz=16000, audio_sample_size=2, realtime=False, verbose=True, 
        recognition_params={}):

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

    language_code = recognition_params.get('language_code', 'en-US')
    model = recognition_params.get('model', 'default')
    use_enhanced = recognition_params.get('use_enhanced', False)
    config = types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sample_rate_hertz,
        language_code=language_code,
        model=model,
        use_enhanced=use_enhanced,
        max_alternatives=1,
        enable_automatic_punctuation=True)
    streaming_config = types.StreamingRecognitionConfig(
        config=config,
        interim_results=True,
        single_utterance=False)

    # streaming_recognize returns a generator.
    delay_ms = 0
    if realtime: delay_ms = 1000 / (sample_rate_hertz * audio_sample_size / chunk_size)
    start_time = time.time()
    responses_pb = client.streaming_recognize(streaming_config, delay_generator(requests, delay_ms=delay_ms) )

    transcript = ""
    responses = []
    first_latency = -1
    for response_pb in responses_pb:
        # Once the transcription has settled, the first result will contain the
        # is_final result. The other results will be for subsequent portions of
        # the audio.
        latency = time.time() - start_time
        response = MessageToDict(response_pb)
        response['latency'] = latency
        responses.append(response)
        for result in response['results']:
            if verbose:
                print('Finished: {}'.format(result.get('isFinal', False)))
                print('Stability: {}'.format(result['stability']))
            
            # The alternatives are ordered from most likely to least.
            alternatives = result['alternatives']
            if len(alternatives) > 0 and 'transcript' in alternatives[0]:
                if first_latency < 0 :
                    first_latency = latency
                if result.get('isFinal', False): 
                    transcript += alternatives[0]['transcript'].strip() + " "

            for alternative in alternatives:
                if verbose:
                    print('Confidence: {}'.format(alternative['confidence']))
                    print(u'Transcript: {}'.format(alternative['transcript']))
    
    transcription_result = {
        'responses': responses, 
        'first_latency': first_latency
    }
    return transcript, transcription_result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('stream', help='File to stream to the API')
    args = parser.parse_args()
    transcribe_streaming_from_file(args.stream, verbose=True, realtime=True)