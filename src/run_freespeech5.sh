#!/bin/bash


DS_DIR=/home/ubuntu/speech/DS-5
#MODEL="${DS_DIR}/DeepSpeech/native_client/deepspeech-0.5.1-models/output_graph.pbmm"
MODEL="${DS_DIR}/DeepSpeech/model-mzh256/output_graph.pbmm"
#MODEL="${DS_DIR}/DeepSpeech/model-mzh512/output_graph.pbmm"
#MODEL="${DS_DIR}/DeepSpeech/model-mzh2048/output_graph.pbmm"


LMMOD_DIR="${DS_DIR}/DeepSpeech/data"
export LD_LIBRARY_PATH="${DS_DIR}/tensorflow/bazel-bin/native_client"

exec "${DS_DIR}/DeepSpeech/native_client/deepspeech" \
    --model "$MODEL" \
    --alphabet "${LMMOD_DIR}/alphabet.txt" \
    --lm "${LMMOD_DIR}/lm/lm.binary" \
    --trie "${LMMOD_DIR}/lm/trie" \
    $@