"""Standalone product-event capture, called by an exclusive board/rollback owner.

No upload, flash, credentials, or lock takeover occurs here. All output is private.
"""
import hashlib,json,re,subprocess,time,wave
from pathlib import Path
from telemetry import parse_lines
HARNESS_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

def device_panic(remote,text):
    text='\n'.join(line for line in text.splitlines() if not re.search(r'\bSTT_EVENT\s+\{',line))
    return bool(remote.PANIC.search(text) or re.search(r'assert failed:|abort\(\) was called|Stack protection fault|stack overflow',text,re.I))

def watchdog_counts(text):
    # Warning and reset observations can describe the same incident. Their sum
    # is a repeat trigger, not a deduplicated count of independent failures.
    text='\n'.join(line for line in text.splitlines() if not re.search(r'\bSTT_EVENT\s+\{',line))
    return {'task_warnings':text.count('Task watchdog got triggered'),
            'interrupt_panics':len(re.findall(r'Interrupt wdt timeout',text,re.I)),
            'reset_observations':len(re.findall(r'(?m)^.*(?:rst:.*WDT|reset reason.*ESP_RST_(?:TASK|INT|RTC)_WDT).*$',text,re.I))}

def product_events(lines):
    rows=[]
    for line in lines:
        match=re.search(r'STT_EVENT (\{.*\})',line)
        if match:
            obj=json.loads(match[1]);assert obj.get('schema')==1 and isinstance(obj.get('type'),str)
            rows.append(obj)
    return rows

def audio_setup():
    data=json.loads(subprocess.check_output(['system_profiler','SPAudioDataType','-json'],text=True))
    devices=data['SPAudioDataType'][0]['_items']
    assert any(x.get('_name')=='Mac mini Speakers' and x.get('coreaudio_default_audio_output_device')=='spaudio_yes' for x in devices)
    subprocess.run(['osascript','-e','set volume output volume 50 without output muted'],check=True)

def audio_metadata(wav):
    wav=Path(wav)
    with wave.open(str(wav),'rb') as stream:
        if stream.getnchannels()!=1 or stream.getsampwidth()!=2 or stream.getframerate()<=0 or not stream.getnframes():
            raise ValueError('Expected nonempty mono int16 playback WAV; its rate need not match the 16 kHz microphone')
        rate=stream.getframerate();duration=stream.getnframes()/rate
    return {'duration_s':duration,'wav_sample_rate':rate,'wav_sha256':hashlib.sha256(wav.read_bytes()).hexdigest()}

def capture(remote,wav,directory,fixture,metrics=True,speakers=True):
    wav=Path(wav);directory=Path(directory)
    assert 'private' in directory.resolve().parts and not directory.exists()
    metadata=audio_metadata(wav);duration=metadata['duration_s']
    directory.mkdir(parents=True,mode=0o700)
    audio_setup();con=remote.Console(directory/'serial.log');play=None
    status={'fixture':fixture,'wav':str(wav.resolve()),**metadata,'mode':'standalone-live-pdm','phase':'boot',
            'harness_sha256':HARNESS_SHA256,'metrics':metrics,'speakers':speakers}
    def save():
        temp=directory/'capture.tmp';temp.write_text(json.dumps(status,indent=2));temp.replace(directory/'capture.json')
    save()
    try:
        ready=con.wait(r'STT_EVENT [^\r\n]*"state":"(?:listening|error)"[^\r\n]*',0,180)
        if not ready:raise RuntimeError('Standalone did not become ready')
        event=json.loads(ready.group(0).split('STT_EVENT ',1)[1]);assert event['state']=='listening',event
        con.command('note stop',r'STT_EVENT [^\r\n]*Recording closed[^\r\n]*',60)
        con.command('status',r'STT_EVENT [^\r\n]*"type":"status"[^\r\n]*',60)
        con.command('vocab list',r'STT_EVENT [^\r\n]*"type":"vocabulary"[^\r\n]*',60)
        settings=product_events(con.since(0))
        product_state=[e for e in settings if e['type']=='status'][-1]
        vocabulary=[e['words'] for e in settings if e['type']=='vocabulary'][-1]
        status.update(lm_strength=product_state['lmStrength'],custom_words=product_state['customWords'],
            vocabulary_sha256=hashlib.sha256(json.dumps(vocabulary,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        before=None
        if metrics:
            con.command('perf dump',r'STT_PERF [^\r\n]*"type":"end"[^\r\n]*',60)
            initial=parse_lines(con.since(0));assert len(initial['reports'])==1
            before=initial['reports'][0];assert before['state']['feature_capacity']==1000,'Feature pool unavailable'
            assert any(e.get('name')=='speaker' for e in initial['events'] if e['type']=='model')==speakers,'Speaker model identity disagrees with control'
        else:
            assert any('Capture feature pool:' in line for line in con.since(0)),'Feature pool unavailable'
            assert not parse_lines(con.since(0))['events'],'Metrics-off control unexpectedly emits probes'
        assert any('Optional background speaker labels ready' in line for line in con.since(0))==speakers,'Speaker readiness disagrees with control'
        session=[e for e in product_events(con.since(0)) if e['type']=='start'][-1]['sessionId']
        status.update(phase='playing',session_id=session,initial_report=before,
            estimated_playback_sample_offset_s=before['state']['accepted_samples']/16000 if before else None,
            initial_report_host_time=time.time());save()
        status['playback_host_time']=time.time()
        spawned=time.monotonic();play=subprocess.Popen(['afplay',str(wav)])
        status.update(playback_spawn_return_host_time=time.time(),playback_spawn_elapsed_s=time.monotonic()-spawned)
        save();deadline=time.monotonic()+duration+150
        while play.poll() is None:
            if time.monotonic()>deadline:raise RuntimeError('Audio playback deadline exceeded')
            if any(device_panic(remote,x) for x in con.since(0)):raise RuntimeError('Device panic during playback')
            time.sleep(1)
        assert play.returncode==0
        status['phase']='draining';save();drain=time.monotonic()
        while time.monotonic()-drain<90:
            rows=product_events(con.since(0));finals=[e for e in rows if e['type']=='final' and e['sessionId']==session]
            labels={(e['sessionId'],e['sequence']) for e in rows if e['type']=='speaker' and e.get('ready')}
            if time.monotonic()-drain>=20 and (not speakers or all((e['sessionId'],e['sequence']) in labels for e in finals)):break
            time.sleep(1)
        if metrics:con.command('perf dump',r'STT_PERF [^\r\n]*"type":"end"[^\r\n]*',90)
        else:con.command('status',r'STT_EVENT [^\r\n]*"type":"status"[^\r\n]*',90)
        lines=con.since(0);perf=parse_lines(lines)
        if metrics:assert len(perf['reports'])==2 and not perf['incomplete_report']
        else:assert not perf['events'],'Metrics-off control unexpectedly emits probes'
        rows=product_events(lines);text='\n'.join(lines);final=perf['reports'][-1] if metrics else None
        watchdogs=watchdog_counts(text)
        status.update(phase='complete',events=rows,telemetry=perf,watchdog_counts=watchdogs,watchdogs=sum(watchdogs.values()),panic=device_panic(remote,text),final_report=final,captions=sum(e['type']=='final' for e in rows),alignment='Estimated report-sample offset only; require sample-index RMS fit before timed/identity scoring.')
        save();return status
    except BaseException as error:status.update(phase='failed',error=type(error).__name__+': '+str(error));save();raise
    finally:
        if play and play.poll() is None:play.terminate();play.wait(timeout=10)
        con.close()
