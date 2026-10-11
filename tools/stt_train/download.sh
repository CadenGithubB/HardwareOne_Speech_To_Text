#!/bin/bash
# Resumable downloads for STT fine-tuning. Re-run safely; curl -C - resumes.
export STT_ROOT=${STT_ROOT:?set STT_ROOT to the STT data root (speech stores, work, logs)}
set -u
LOG=$STT_ROOT/logs/download.log
get() { # url dest
  local url="$1" dest="$2"
  if [ -f "$dest.done" ]; then return 0; fi
  for i in 1 2 3 4 5; do
    if curl -sSfL --retry 5 --retry-delay 5 -C - -o "$dest" "$url"; then touch "$dest.done"; echo "$(date +%T) OK $dest" >> $LOG; return 0; fi
    echo "$(date +%T) retry $i $dest" >> $LOG; sleep 10
  done
  echo "$(date +%T) FAIL $dest" >> $LOG; return 1
}
HF=https://huggingface.co/datasets/edinburghcstr/ami/resolve/main
ami() { # mic
  local mic=$1
  curl -s "https://huggingface.co/api/datasets/edinburghcstr/ami/tree/main/$mic" | python3 -c "import sys,json;[print(f['path']) for f in json.load(sys.stdin)]" | while read p; do get "$HF/$p" "$STT_ROOT/ami/$p"; done
}
OS=https://www.openslr.org/resources
case "${1:-all}" in
  ami) ami sdm; ami ihm ;;
  libri) # Hugging Face parquet mirror of OpenSLR LibriSpeech (OpenSLR stalled)
    for part in train.100 validation test; do
      curl -s "https://huggingface.co/api/datasets/openslr/librispeech_asr/tree/main/clean/$part" | python3 -c "import sys,json;[print(f['path']) for f in json.load(sys.stdin)]" | while read p; do
        get "https://huggingface.co/datasets/openslr/librispeech_asr/resolve/main/$p" "$STT_ROOT/librispeech/$(echo $p | tr '/' '_')"; done
    done ;;
  libri360) # extra clean read speech, ~900 more speakers
    curl -s "https://huggingface.co/api/datasets/openslr/librispeech_asr/tree/main/clean/train.360" | python3 -c "import sys,json;[print(f['path']) for f in json.load(sys.stdin)]" | while read p; do
      get "https://huggingface.co/datasets/openslr/librispeech_asr/resolve/main/$p" "$STT_ROOT/librispeech/$(echo $p | tr '/' '_')"; done ;;
  tedlium) mkdir -p $STT_ROOT/tedlium; get https://openslr.elda.org/resources/51/TEDLIUM_release-3.tgz $STT_ROOT/tedlium/TEDLIUM_release-3.tgz ;;
  voxpopuli) # parliament speeches, many accents (CC0); first 8 of 30 shards (~140 h)
    mkdir -p $STT_ROOT/voxpopuli
    for i in 0000 0001 0002 0003 0004 0005 0006 0007; do
      get "https://huggingface.co/datasets/facebook/voxpopuli/resolve/refs%2Fconvert%2Fparquet/en/train/$i.parquet" "$STT_ROOT/voxpopuli/train_$i.parquet"; done
    get "https://huggingface.co/datasets/facebook/voxpopuli/resolve/refs%2Fconvert%2Fparquet/en/validation/0000.parquet" "$STT_ROOT/voxpopuli/validation_0000.parquet" ;;
  voxpopuli2) # 2026-10-01: 4 more English train shards (0008-0011, ~40 h kept)
    for i in 0008 0009 0010 0011; do
      get "https://huggingface.co/datasets/facebook/voxpopuli/resolve/refs%2Fconvert%2Fparquet/en/train/$i.parquet" "$STT_ROOT/voxpopuli/train_$i.parquet"; done ;;
  peoples) # People's Speech "clean" (CC-BY / CC-BY-SA), 30 of 804 shards spread
    # across the set for source variety (~7.25 h each; council meetings, interviews, talks)
    mkdir -p $STT_ROOT/peoples_speech
    for k in $(seq 0 29); do
      i=$(printf %05d $(( k * 804 / 30 )))
      get "https://huggingface.co/datasets/MLCommons/peoples_speech/resolve/main/clean/train-$i-of-00804.parquet" "$STT_ROOT/peoples_speech/clean_train_$i.parquet"; done ;;
  musan) get https://openslr.elda.org/resources/17/musan.tar.gz $STT_ROOT/musan/musan.tar.gz ;;
  rirs) get https://openslr.elda.org/resources/28/rirs_noises.zip $STT_ROOT/rirs/rirs_noises.zip ;;
esac
echo "$(date +%T) DONE ${1:-all}" >> $LOG
