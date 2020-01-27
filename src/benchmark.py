#!/usr/bin/env python3

'''
Use settings.ini to configure the benchmark.
'''

import codecs
import collections
import configparser
import glob
import os
import shutil
import time
import json
import argparse

import pandas as pd

import metrics
import transcribe


def get_speech_file_type(settings, data_folder):
    # Automatically detect the speech file type.
    # Heuristic: the detected speech file type is the one that has the more speech files in data_folder
    #            e.g., if in data_folder there are 10 mp3s and 25 flacs, then choose flac
    supported_speech_file_types = sorted(['flac', 'mp3', 'ogg', 'wav'])
    speech_file_type = settings.get('general','speech_file_type')
    if speech_file_type == 'auto':
        maximum_number_of_speech_files = 0
        detected_speech_file_type = None
        for supported_speech_file_type in supported_speech_file_types:
            potential_speech_filepaths = sorted(glob.glob(os.path.join(data_folder, '*.{0}'.format(supported_speech_file_type))))
            if maximum_number_of_speech_files < len(potential_speech_filepaths):
                maximum_number_of_speech_files = len(potential_speech_filepaths)
                detected_speech_file_type = supported_speech_file_type
        speech_file_type = detected_speech_file_type
        print('Detected speech file type: {0}'.format(speech_file_type))
        if detected_speech_file_type is None:
            raise ValueError('You have set speech_file_type to be "auto" ({0}). We could not detect any speech file. Speech file extensions should be {1}.'
                                .format(speech_file_type, supported_speech_file_types))

    if speech_file_type not in supported_speech_file_types:
        raise ValueError('You have set speech_file_type to be "{0}". This is invalid. speech_file_type should be {1}'.
                            format(speech_file_type, supported_speech_file_types))

    return speech_file_type


def get_speech_filepaths(settings, data_folder):
    speech_file_type = get_speech_file_type(settings, data_folder)
    speech_filepaths = sorted(glob.glob(os.path.join(data_folder, '*.{0}'.format(speech_file_type))))

    if settings.getint('general','max_data_files') > 0:
        speech_filepaths = speech_filepaths[0:settings.getint('general','max_data_files')]

    if len(speech_filepaths) <= 0:
        raise ValueError('There is no file with the extension "{0}"  in the folder "{1}"'.
                            format(speech_file_type,data_folder))
    return speech_filepaths, speech_file_type


def transcribe_audio_files(settings, speech_filepaths, speech_file_type, asr_systems):
    # Transcribe
    print('\n### Call the ASR engines to compute predicted transcriptions')
    for speech_file_number, speech_filepath in enumerate(speech_filepaths):
        # Convert the speech file from FLAC/MP3/Ogg to WAV
        if speech_file_type in ['flac', 'mp3', 'ogg']:
            from pydub import AudioSegment
            print('speech_filepath: (#{0}) {1}'.format(speech_file_number, speech_filepath))
            sound = AudioSegment.from_file(speech_filepath, format=speech_file_type)
            new_speech_filepath = speech_filepath[:-len(speech_file_type)-1]+'.wav'
            sound.export(new_speech_filepath, format="wav")
            speech_filepath = new_speech_filepath

        # Transcribe the speech file
        all_transcription_skipped = True
        for asr_system in asr_systems:
            _, transcription_skipped = transcribe.transcribe(speech_filepath, asr_system, settings, save_transcription=True)
            all_transcription_skipped = all_transcription_skipped and transcription_skipped

        # If the speech file was converted from FLAC/MP3/Ogg to WAV, remove the WAV file
        if speech_file_type in ['flac', 'mp3', 'ogg']:
            os.remove(new_speech_filepath)

        if not all_transcription_skipped:
            time.sleep(settings.getint('general','delay_in_seconds_between_transcriptions'))



def evaluate_transcriptions_files(settings, speech_filepaths, asr_systems):
    # Evaluate transcriptions
    df = pd.DataFrame(columns =['file', 'gold', 'len', 'service', 'transcript', 'wer', 'changes', 'corrects', 'subs', 'ins', 'dels'])
    df = df.astype(dtype= {'len': 'int', 'wer': 'float', 'changes': 'int', 'corrects': 'int', 'subs': 'int', 'ins': 'int', 'dels': 'int'})
    all_texts = {}
    print('\n### Final evaluation of all the ASR engines based on their predicted jurisdictions')

    for asr_system in asr_systems:
        all_texts[asr_system] = {}

        all_predicted_transcription_filepath = 'all_predicted_transcriptions_' + asr_system + '.txt'
        all_gold_transcription_filepath = 'all_gold_transcriptions.txt'
        all_predicted_transcription_file = codecs.open(all_predicted_transcription_filepath, 'w', settings.get('general','predicted_transcription_encoding'))
        all_gold_transcription_filepath = codecs.open(all_gold_transcription_filepath, 'w', settings.get('general','gold_transcription_encoding'))

        number_of_tokens_in_gold = 0
        number_of_empty_predicted_transcription_txt_files = 0
        number_of_missing_predicted_transcription_txt_files = 0
        edit_types = ['corrects', 'deletions', 'insertions', 'substitutions', 'changes']
        number_of_edits = {}
        
        for edit_type in edit_types:
            number_of_edits[edit_type] = 0

        for speech_filepath in speech_filepaths:
            _, gold_transcription_filepath_text, _ = transcribe.transcription_artifacts( speech_filepath, 'gold' )
            _, predicted_transcription_txt_filepath, _ = transcribe.transcription_artifacts( speech_filepath, asr_system )

            if not os.path.isfile(predicted_transcription_txt_filepath):
                number_of_missing_predicted_transcription_txt_files += 1
                predicted_transcription = ''
            else:
                predicted_transcription = codecs.open(predicted_transcription_txt_filepath, 'r', settings.get('general','predicted_transcription_encoding')).read().strip()
                if len(predicted_transcription) == 0:
                    #print('predicted_transcription_txt_filepath {0} is empty'.format(predicted_transcription_txt_filepath))
                    number_of_empty_predicted_transcription_txt_files += 1

            gold_transcription = codecs.open(gold_transcription_filepath_text, 'r', settings.get('general','gold_transcription_encoding')).read()
            gold_transcription = metrics.normalize_text(gold_transcription, lower_case=True, remove_punctuation=True, write_numbers_in_letters=False, write_numbers_in_letters_inflect=True)
            predicted_transcription = metrics.normalize_text(predicted_transcription, lower_case=True, remove_punctuation=True, write_numbers_in_letters=False, write_numbers_in_letters_inflect=True)

            all_predicted_transcription_file.write('{0}\n'.format(predicted_transcription))
            all_gold_transcription_filepath.write('{0}\n'.format(gold_transcription))
            #print('\npredicted_transcription\t: {0}'.format(predicted_transcription))
            #print('gold_transcription\t: {0}'.format(gold_transcription))
            wer = metrics.wer(gold_transcription.split(' '), predicted_transcription.split(' '))
            #print('wer: {0}'.format(wer))

            #if len(predicted_transcription) == 0: continue

            number_of_tokens_in_gold_this_sentence = len(gold_transcription.split(' '))
            number_of_tokens_in_gold += number_of_tokens_in_gold_this_sentence
            for edit_type in edit_types:
                number_of_edits[edit_type] += wer[edit_type]
            stats = {
                'file': speech_filepath, 'gold': gold_transcription, 'len': number_of_tokens_in_gold_this_sentence, 'service': asr_system, 'transcript': predicted_transcription, 
                'wer': wer['changes']/number_of_tokens_in_gold_this_sentence, 'changes': wer['changes'], 'corrects': wer['corrects'], 'subs': wer['substitutions'], 'ins': wer['insertions'], 'dels': wer['deletions']
            }
            df = df.append(stats, ignore_index=True)

        all_predicted_transcription_file.close()
        all_gold_transcription_filepath.close()

        wer = number_of_edits['changes'] / number_of_tokens_in_gold
        #print('\nGlobal WER based on the all predicted transcriptions:')
        #print('{3}\twer: {0:.5f}% ({1}; number_of_tokens_in_gold = {2})'.format(wer*100, number_of_edits, number_of_tokens_in_gold,asr_system))
        print('{5}\twer: {0:.5f}% \t(deletions: {1}\t; insertions: {2}\t; substitutions: {3}\t; number_of_tokens_in_gold = {4})'.
                format(wer*100, number_of_edits['deletions'], number_of_edits['insertions'], number_of_edits['substitutions'], number_of_tokens_in_gold,asr_system))
        print('Number of speech files: {0}'.format(len(speech_filepaths)))
        print('Number of missing predicted prescription files: {0}'.format(number_of_missing_predicted_transcription_txt_files))
        print('Number of empty predicted prescription files: {0}'.format(number_of_empty_predicted_transcription_txt_files))
    df.to_csv(settings.get('general','exp_name') + '_summary.csv')


preceeding_silence_cache = {}
def preseeding_silence(base_filepath):
    if not base_filepath in preceeding_silence_cache:
        silence_duration_in_ms = 0
        timid_info_filepath =  base_filepath + '.wrd'
        with open(timid_info_filepath) as fp:
            word_start_in_samples = int(fp.readline().split()[0])
            silence_duration_in_ms = word_start_in_samples * 1.0/16000
        preceeding_silence_cache[base_filepath] = silence_duration_in_ms

    return preceeding_silence_cache[base_filepath]

def transcript_compare(reference, candidate):
    cs = candidate.split()
    if len(cs) <= 0: return False
    return reference.split()[0].casefold() == cs[0].casefold()

def evaluate_latency_find_first_correct(tinfo):
    correct_latency = -1
    transcription = tinfo['transcription'].casefold()
    responses = tinfo['transcription_json']['responses']
    for response in responses:
        results = response['Transcript']['Results'] if 'Transcript' in response else response['results']
        for result in results:
            alts = result['Alternatives'] if 'Alternatives' in result else result['alternatives']
            for a in alts:
                
                t = a['Transcript'] if 'Transcript' in a else a['transcript'] if 'transcript' in a else ''
                if transcript_compare(transcription, t) and correct_latency<0:
                    correct_latency = response['latency']
                if correct_latency>=0 : break
            if correct_latency>=0 : break
        if correct_latency>=0 : break

    return correct_latency

def evaluate_latency(settings, speech_filepaths, asr_systems):
    print('\n### Summaring Latencies...')

    df = pd.DataFrame(columns =['file', 'service', 'first_latency', 'correct_latency'])
    df = df.astype(dtype= {'first_latency': 'float', 'correct_latency': 'float'})

    for asr_system in asr_systems:

        for speech_filepath in speech_filepaths:
            base_filepath, _, _ = transcribe.transcription_artifacts( speech_filepath )
            silence_offset = preseeding_silence(base_filepath)
            
            _, _, json_filepath = transcribe.transcription_artifacts( speech_filepath, asr_system )
            with open(json_filepath) as f: 
                tinfo = json.load(f)

            first_latency = tinfo['transcription_json']['first_latency']

            correct_latency = evaluate_latency_find_first_correct(tinfo)
            
            df = df.append({
                'file': speech_filepath, 
                'service': asr_system, 
                'silence_offset': silence_offset,
                'first_latency': first_latency,
                'correct_latency': correct_latency
                }, ignore_index=True)

    print(df.head(100))
    df.to_csv(settings.get('general','exp_name') + '_latency.csv')


def main(settings_filepath=None):
    # Load setting file
    settings = configparser.ConfigParser()
    settings.read(settings_filepath)

    asr_systems = settings.get('general','asr_systems').split(',')
    data_folders = settings.get('general','data_folders').split(',')
    asr_systems = [s.strip() for s in asr_systems]

    print('Configuration file: {0}'.format(settings_filepath))
    print('asr_systems: {0}'.format(asr_systems))
    print('data_folders: {0}'.format(data_folders))

    for data_folder in data_folders:
        print('\nWorking on data folder "{0}"'.format(data_folder))
        speech_filepaths, speech_file_type = get_speech_filepaths(settings, data_folder)

        if settings.getboolean('general','transcribe'):
            transcribe_audio_files(settings, speech_filepaths, speech_file_type, asr_systems)
 
        if settings.getboolean('general','evaluate_transcriptions'):
            evaluate_transcriptions_files(settings, speech_filepaths, asr_systems)

        if settings.getboolean('general','evaluate_latency'):
            evaluate_latency(settings, speech_filepaths, asr_systems)




if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', nargs='?', default='settings.ini', help='config file')
    args = parser.parse_args()

    main(settings_filepath=args.config)
    #cProfile.run('main()') # if you want to do some profiling
