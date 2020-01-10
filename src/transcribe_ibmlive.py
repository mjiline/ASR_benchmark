#!/usr/bin/env python

import io, os, argparse
import boto3
import websockets, asyncio
import datetime, time
import hashlib, hmac, base64, urllib.parse, binascii
from struct import pack, unpack_from 
import json
from transcribe_utils import delay_generator


async def handle_stream(audio_data, username=None, password=None, language="en-US", show_all=False):

        assert isinstance(audio_data, AudioData), "Data must be audio data"
        assert isinstance(username, str), "``username`` must be a string"
        assert isinstance(password, str), "``password`` must be a string"

        flac_data = audio_data.get_flac_data(
            convert_rate=None if audio_data.sample_rate >= 16000 else 16000,  # audio samples should be at least 16 kHz
            convert_width=None if audio_data.sample_width >= 2 else 2  # audio samples should be at least 16-bit
        )
        url = "https://stream.watsonplatform.net/speech-to-text/api/v1/recognize?{}".format(urlencode({
            "profanity_filter": "false",
            "model": "{}_BroadbandModel".format(language),
            "inactivity_timeout": -1,  # don't stop recognizing when the audio stream activity stops
        }))
        request = Request(url, data=flac_data, headers={
            "Content-Type": "audio/x-flac",
            "X-Watson-Learning-Opt-Out": "true",  # prevent requests from being logged, for improved privacy
        })
        authorization_value = base64.standard_b64encode("{}:{}".format(username, password).encode("utf-8")).decode("utf-8")
        request.add_header("Authorization", "Basic {}".format(authorization_value))
        try:
            response = urlopen(request, timeout=self.operation_timeout)
        except HTTPError as e:
            raise RequestError("recognition request failed: {}".format(e.reason))
        except URLError as e:
            raise RequestError("recognition connection failed: {}".format(e.reason))
        response_text = response.read().decode("utf-8")
        result = json.loads(response_text)

        # return results
        if show_all: return result
        if "results" not in result or len(result["results"]) < 1 or "alternatives" not in result["results"][0]:
            raise UnknownValueError()

        transcription = []
        for utterance in result["results"]:
            if "alternatives" not in utterance: raise UnknownValueError()
            for hypothesis in utterance["alternatives"]:
                if "transcript" in hypothesis:
                    transcription.append(hypothesis["transcript"])
        return "\n".join(transcription)


def streaming_recognize(data, username=None, password=None, instance_id=None):
    ws_url = 'wss://api.%s.speech-to-text.watson.cloud.ibm.com/instances/%s/v1/recognize' \
        % ('us-south', instance_id)
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
        chunk_size=8*1024, sample_rate_hertz=16000, audio_sample_size=2, realtime=False, verbose=False,
        username=None, password=None, instance_id=None):

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

    responses = streaming_recognize(requests, username=username, password=password, instance_id=instance_id)

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
    username = os.environ['IBM_USERNAME']
    password = os.environ['IBM_PASSWORD']
    instance_id = os.environ['IBM_INSTANCE_ID']
    transcript, transcript_json = transcribe_streaming_from_file(
        args.stream, username=username, password=password, instance_id=instance_id,
        verbose=True, realtime=True)
    print(transcript_json)
    print(transcript)
