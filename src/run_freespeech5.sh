#!/bin/bash -x

PPID=$$
function handler {
  trap INT
  kill $PPID
}
trap handler INT
#shopt -s execfail


DS_DIR=/tf/DS6

MNAME=ds-other-2048
MODEL="${DS_DIR}/models/export-${MNAME}/output_graph.pbmm"
#MODEL="${DS_DIR}/DeepSpeech/native_client/deepspeech-0.5.1-models/output_graph.pbmm"


LMMOD_DIR="${DS_DIR}/DeepSpeech/data"
export LD_LIBRARY_PATH="${DS_DIR}/tensorflow/bazel-bin/native_client"

#    --alphabet "${LMMOD_DIR}/alphabet.txt"
${DS_DIR}/DeepSpeech/native_client/deepspeech \
    --model "$MODEL" \
    --lm "${LMMOD_DIR}/lm/lm.binary" \
    --trie "${LMMOD_DIR}/lm/trie" \
    $@
