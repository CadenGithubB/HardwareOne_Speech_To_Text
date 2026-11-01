#!/usr/bin/env python3
"""Synthetic retained-tail, center-crop and cross-speaker geometry cases."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/device_tests/speaker'))
from spkcuts import geometry,envelope_coverage


def clip(i,spk,a,b):
    return {'i':i,'speaker':spk,'start_s':a,'end_s':b,'speech_start_s':a,'speech_end_s':b}


def main():
    clips=[clip(0,'A',.25,2.5),clip(1,'B',3.2,3.9)]
    g=geometry({'span_play_s':[0,4],'samples':48000,'ref':'A'},clips)
    assert g['retained_span_s']==[0,3] and g['model_samples']==47840
    assert g['center_crop_offset_samples']==80 and g['discarded_capture_tail_ms']==1000
    assert not g['window_mixed_by_manifest'] and g['other_speaker_ids']==[]
    assert g['speech_envelope_ms_by_speaker']=={'A':2250}
    g=geometry({'span_play_s':[.4,2.9],'samples':40000,'ref':'A'},[clip(0,'A',.2,2.2)])
    assert g['capture_onset_lost_ms']==200 and g['model_onset_lost_ms']==200
    assert g['capture_onset_lost_ms_shift_100']==[100,300]
    assert g['outside_speech_envelopes_ms']==700
    g=geometry({'span_play_s':[0,2],'samples':32000,'ref':'A'},[clip(0,'A',0,1),clip(1,'B',1.2,2)])
    assert g['window_mixed_by_manifest'] and g['other_speaker_ids']==['B']
    g=geometry({'span_play_s':[0,8],'samples':128000,'ref':'A'},[clip(0,'A',.2,7.8)])
    assert g['capture_onset_lost_ms']==0 and g['model_onset_lost_ms']>2000
    c=envelope_coverage((0,3),[(0,1),(1,2),(2,3)])
    assert c['gap_ms']==0 and c['leading_gap_ms']==0
    c=envelope_coverage((0,3),[(.1,1),(1.2,2.9)])
    assert c=={'gap_ms':400,'leading_gap_ms':100,'trailing_gap_ms':100}
    print('spkcuts: retained and model window geometry ok')


if __name__=='__main__':main()
