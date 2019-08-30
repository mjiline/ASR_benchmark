#!/usr/bin/env python3

import speech_recognition as sr
from os import path
import time
import json
import os
import sys
import asr_speechmatics
import codecs

def transcribe(speech_filepath, asr_system, settings, save_transcription=True):
    '''
    Returns:
     - transcription: string corresponding the transcription obtained from the ASR API or existing transcription file.
     - transcription_skipped: Boolean indicating if the speech file was sent to the ASR API.
    '''
    transcription_json = ''
    transcription_filepath_base = '.'.join(speech_filepath.split('.')[:-1]) + '_'  + asr_system
    transcription_filepath_text = transcription_filepath_base  + '.txt'
    transcription_filepath_json = transcription_filepath_base  + '.json'

    # If there already exists a transcription file,  we may skip it depending on the user settings.
    if os.path.isfile(transcription_filepath_text):
        existing_transcription = codecs.open(transcription_filepath_text, 'r', settings.get('general','predicted_transcription_encoding')).read()
        is_transcription_file_empty = len(existing_transcription.strip()) == 0
        if not is_transcription_file_empty and not settings.getboolean('general','overwrite_non_empty_transcriptions'):
            print('Skipped speech file {0} because the file {1} already exists and is not empty.'.format(speech_filepath,transcription_filepath_text))
            print('Change the setting `overwrite_non_empty_transcriptions` to True if you want to overwrite existing transcriptions')
            transcription_skipped = True
            return existing_transcription, transcription_skipped
        if is_transcription_file_empty and not settings.getboolean('general','overwrite_empty_transcriptions'):
            print('Skipped speech file {0} because the file {1} already exists and is empty.'.format(speech_filepath,transcription_filepath_text))
            print('Change the setting `overwrite_empty_transcriptions` to True if you want to overwrite existing transcriptions')
            transcription_skipped = True
            return existing_transcription, transcription_skipped

    # use the audio file as the audio source
    r = sr.Recognizer()
    with sr.AudioFile(speech_filepath) as source:
        audio = r.record(source)  # read the entire audio file

    transcription = ''
    asr_could_not_be_reached = False
    asr_timestamp_started = time.time()
    speech_language = settings.get('general','speech_language')
    if asr_system == 'google':
        # recognize speech using Google Speech Recognition
        try:
            # for testing purposes, we're just using the default API key
            # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY")`
            # instead of `r.recognize_google(audio)`
            response = r.recognize_google(audio, show_all=True, language=speech_language)
            transcription_json = response

            actual_result = response
            if not isinstance(actual_result, dict) or len(actual_result.get("alternative", [])) == 0: raise sr.UnknownValueError()

            if "confidence" in actual_result["alternative"]:
                # return alternative with highest confidence score
                best_hypothesis = max(actual_result["alternative"], key=lambda alternative: alternative["confidence"])
            else:
                # when there is no confidence available, we arbitrarily choose the first hypothesis.
                best_hypothesis = actual_result["alternative"][0]
            if "transcript" not in best_hypothesis: raise sr.UnknownValueError()
            transcription = best_hypothesis["transcript"]

            print("Google Speech Recognition transcription is: " + transcription)
        except sr.UnknownValueError:
            print("Google Speech Recognition could not understand audio")
        except sr.RequestError as e:
            print("Could not request results from Google Speech Recognition service; {0}".format(e))
            asr_could_not_be_reached = True

    elif asr_system == 'googlecloud':
        # recognize speech using Google Cloud Speech
        GOOGLE_CLOUD_SPEECH_CREDENTIALS_filepath = settings.get('credentials','google_cloud_speech_credentials_filepath')
        GOOGLE_CLOUD_SPEECH_CREDENTIALS = codecs.open(GOOGLE_CLOUD_SPEECH_CREDENTIALS_filepath, 'r', 'UTF-8').read()
        try:
            response = r.recognize_google_cloud(audio, credentials_json=GOOGLE_CLOUD_SPEECH_CREDENTIALS, show_all=True, language=speech_language)
            transcription_json = response
            if "results" not in response or len(response["results"]) == 0: raise sr.UnknownValueError()
            transcript = ""
            for result in response["results"]:
                transcript += result["alternatives"][0]["transcript"].strip() + " "

            transcription = transcript

        except sr.UnknownValueError:
            print("Google Cloud Speech could not understand audio")
        except sr.RequestError as e:
            print("Could not request results from Google Cloud Speech service; {0}".format(e))
            asr_could_not_be_reached = True

    # recognize speech using Wit.ai
    elif asr_system == 'wit':
        WIT_AI_KEY = settings.get('credentials','wit_ai_key')
        print("Calling the Wit.ai API")
        try:
            response = r.recognize_wit(audio, key=WIT_AI_KEY, show_all=True)
            transcription_json = response

            if "_text" not in response or response["_text"] is None: raise sr.UnknownValueError()
            transcription = response["_text"]

        except sr.UnknownValueError:
            print("Wit.ai could not understand audio")
        except sr.RequestError as e:
            print("Could not request results from Wit.ai service; {0}".format(e))
            asr_could_not_be_reached = True

    # recognize speech using Microsoft Bing Voice Recognition
    elif asr_system == 'microsoft':
        BING_KEY = settings.get('credentials','bing_key')
        print('Calling the Microsoft Bing Voice Recognition API')
        try:
            response =  r.recognize_bing(audio, key=BING_KEY, show_all=True, language=speech_language)
            transcription_json = response
            if "RecognitionStatus" not in response or response["RecognitionStatus"] != "Success" or "DisplayText" not in response:
                raise sr.UnknownValueError()
            transcription = response["DisplayText"]

        except sr.UnknownValueError:
            print("Microsoft Bing Voice Recognition could not understand audio")
        except sr.RequestError as e:
            print("Could not request results from Microsoft Bing Voice Recognition service; {0}".format(e))
            asr_could_not_be_reached = True


    elif asr_system == 'houndify':
        # recognize speech using Houndify
        HOUNDIFY_CLIENT_ID = settings.get('credentials','houndify_client_id')
        HOUNDIFY_CLIENT_KEY = settings.get('credentials','houndify_client_key')

        print("Calling the Houndify API")
        try:
            response = r.recognize_houndify(audio, client_id=HOUNDIFY_CLIENT_ID, client_key=HOUNDIFY_CLIENT_KEY, show_all=True)
            transcription_json = response

            if "Disambiguation" not in response or response["Disambiguation"] is None:
                raise sr.UnknownValueError()

            transcription = response['Disambiguation']['ChoiceData'][0]['Transcription']


        except sr.UnknownValueError:
            print("Houndify could not understand audio")
        except sr.RequestError as e:
            print("Could not request results from Houndify service; {0}".format(e))
            asr_could_not_be_reached = True

    # recognize speech using IBM Speech to Text
    elif asr_system == 'ibm':
        IBM_USERNAME = settings.get('credentials','ibm_username')
        IBM_PASSWORD = settings.get('credentials','ibm_password')
        try:
            response = r.recognize_ibm(audio, username=IBM_USERNAME, password=IBM_PASSWORD, show_all=True, language=speech_language)
            transcription_json = response

            if "results" not in response or len(response["results"]) < 1 or "alternatives" not in response["results"][0]:
                raise sr.UnknownValueError()

            transcription = []
            for utterance in response["results"]:
                if "alternatives" not in utterance: raise sr.UnknownValueError()
                for hypothesis in utterance["alternatives"]:
                    if "transcript" in hypothesis:
                        transcription.append(hypothesis["transcript"])
            transcription = "\n".join(transcription)
            transcription = transcription.strip()

        except sr.UnknownValueError:
            print("IBM Speech to Text could not understand audio")
        except sr.RequestError as e:
            print("Could not request results from IBM Speech to Text service; {0}".format(e))
            asr_could_not_be_reached = True

    elif asr_system == 'speechmatics':
        # recognize speech using Speechmatics Speech Recognition
        speechmatics_id = settings.get('credentials','speechmatics_id')
        speechmatics_token = settings.get('credentials','speechmatics_token')
        print('speech_filepath: {0}'.format(speech_filepath))
        transcription, transcription_json = asr_speechmatics.transcribe_speechmatics(speechmatics_id,speechmatics_token,speech_filepath,speech_language)
        try:
            print('Speechmatics  transcription is: {0}'.format(transcription))
        except:
            print('Speechmatics encountered some issue')
            asr_could_not_be_reached = True

    elif asr_system == 'amazon':
        try:
            bot_name = settings.get('credentials','amazon_bot_name')
            bot_alias = settings.get('credentials','amazon_bot_alias')
            user_id = settings.get('credentials','amazon_user_id')
            transcription,transcription_json = recognize_amazon(audio, bot_name, bot_alias, user_id,
                     content_type="audio/l16; rate=16000; channels=1", access_key_id=settings.get('credentials','amazon_access_key_id'),
                     secret_access_key=settings.get('credentials','amazon_secret_access_key'), region=settings.get('credentials','amazon_region'))
            transcription_json['audioStream'] = ''
        except sr.UnknownValueError:
            print("Amazon not process the speech transcription request")

    elif asr_system == 'deepspeech':
        try:
            deepspeech_cmdline = settings.get('deepspeech','cmdline')
            transcription,transcription_json = recognize_deepspeech(audio, deepspeech_cmdline)
        except:
            print('Deepspeech encountered some issue')
            asr_could_not_be_reached = True
            
    else: raise ValueError("Invalid asr_system. asr_system = {0}".format(asr_system))

    asr_timestamp_ended = time.time()
    asr_time_elapsed = asr_timestamp_ended - asr_timestamp_started
    print('asr_time_elapsed: {0:.3f} seconds'.format(asr_time_elapsed))
    #time.sleep(2)   # Delay in seconds
    #if len(transcription) == 0 and asr_could_not_be_reached: return transcription

    if save_transcription:
        #print('Transcription saved in {0} and {1}'.format(transcription_filepath_text,transcription_filepath_json))
        codecs.open(transcription_filepath_text,'w', settings.get('general','predicted_transcription_encoding')).write(transcription)

    print('transcription: {0}'.format(transcription))
    results = {}
    results['transcription'] = transcription
    results['transcription_json'] = transcription_json
    results['asr_time_elapsed'] = asr_time_elapsed
    results['asr_timestamp_ended'] = asr_timestamp_ended
    results['asr_timestamp_started'] = asr_timestamp_started


    json.dump(results, codecs.open(transcription_filepath_json, 'w', settings.get('general','predicted_transcription_encoding')), indent = 4, sort_keys=True)

    transcription_skipped = False
    return transcription, transcription_skipped



def recognize_amazon(audio_data, bot_name, bot_alias, user_id,
                     content_type="audio/l16; rate=16000; channels=1", access_key_id=None, secret_access_key=None, region=None):
    """
    Performs speech recognition on ``audio_data`` (an ``AudioData`` instance).

    If access_key_id or secret_access_key is not set it will go through the list in the link below
    http://boto3.readthedocs.io/en/latest/guide/configuration.html#configuring-credentials

    Author: Patrick Artounian (https://github.com/partounian)
    Source: https://github.com/Uberi/speech_recognition/pull/331
    """
    assert isinstance(audio_data, sr.AudioData), "Data must be audio data"
    assert isinstance(bot_name, str), "``bot_name`` must be a string"
    assert isinstance(bot_alias, str), "``bot_alias`` must be a string"
    assert isinstance(user_id, str), "``user_id`` must be a string"
    assert isinstance(content_type, str), "``content_type`` must be a string"
    assert access_key_id is None or isinstance(access_key_id, str), "``access_key_id`` must be a string"
    assert secret_access_key is None or isinstance(secret_access_key, str), "``secret_access_key`` must be a string"
    assert region is None or isinstance(region, str), "``region`` must be a string"

    try:
        import boto3
    except ImportError:
        raise sr.RequestError("missing boto3 module: ensure that boto3 is set up correctly.")

    client = boto3.client('lex-runtime', aws_access_key_id=access_key_id,
                          aws_secret_access_key=secret_access_key,
                          region_name=region)

    raw_data = audio_data.get_raw_data(
        convert_rate=16000, convert_width=2
    )

    accept = "text/plain; charset=utf-8"
    response = client.post_content(botName=bot_name, botAlias=bot_alias, userId=user_id,
                                   contentType=content_type, accept=accept, inputStream=raw_data)

    if not response["inputTranscript"]:
        raise sr.UnknownValueError()

    return response["inputTranscript"], response



def recognize_deepspeech(audio_data, cmdline):
    """
    Author: Misha Jiline (https://github.com/mjiline)
    """
    assert isinstance(audio_data, sr.AudioData), "Data must be audio data"
    assert isinstance(cmdline, str), "``cmdline`` must be a string"

    try:
        import tempfile
        import subprocess
    except ImportError:
        raise sr.RequestError("missing tempfile module")

    raw_data = audio_data.get_wav_data(
        convert_rate=16000, convert_width=2
    )

    with tempfile.NamedTemporaryFile(suffix='.wav') as fp:
        fp.write(raw_data)
        fp.seek(0)
        transcript = subprocess.run(
            "%s --audio %s" % (cmdline, fp.name), 
            shell=True, capture_output=True).stdout
        transcript = transcript.decode('utf-8')

    return transcript, {}