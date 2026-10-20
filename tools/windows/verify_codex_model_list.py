"""Offline Codex model/list integration. No turns, user auth or real API requests."""
import argparse,json,os,queue,subprocess,sys,tempfile,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from provider_core import Settings,prepare,apply_plan,read_snapshot
from switch_profiles import choices,prepare_switch

def model_list(executable,home):
    env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','PATH')}
    env['CODEX_HOME']=str(home)
    with (home/'probe.log').open('wb') as log:
        p=subprocess.Popen([str(executable),'app-server'],cwd=home,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log)
        q=queue.Queue()
        def receive():
            for line in p.stdout:q.put(line)
        reader=threading.Thread(target=receive,daemon=True);reader.start()
        def request(obj):
            p.stdin.write((json.dumps(obj)+'\n').encode());p.stdin.flush()
            for _ in range(100):
                result=json.loads(q.get(timeout=15))
                if result.get('id')==obj['id']:
                    assert 'error' not in result,result
                    return result['result']
            raise AssertionError('No matching model/list response')
        try:
            init=request({'id':1,'method':'initialize','params':{'clientInfo':{'name':'codex-connect-test','version':'1'},'capabilities':{'experimentalApi':True}}})
            result=request({'id':2,'method':'model/list','params':{'includeHidden':True}})
        finally:
            p.terminate();p.wait(timeout=10);reader.join(timeout=2)
            p.stdin.close();p.stdout.close()
    errors=(home/'probe.log').read_text(errors='replace')
    assert 'Invalid configuration' not in errors and 'failed to parse model_catalog_json' not in errors,errors
    return init['userAgent'],result['data']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--codex-exe',type=Path,required=True);args=parser.parse_args()
    report=[]
    with tempfile.TemporaryDirectory(prefix='catalog-integration-',dir=ROOT/'work') as temp:
        home=Path(temp);config=home/'config.toml'
        config.write_text('model_provider="openai"\nmodel="gpt-6-astra"\n',encoding='utf-8')
        settings=Settings('fixture','Fixture','DeepSeek-v4-flash','http://127.0.0.1:1',auth_mode='token',token='FAKE-LOCAL-ONLY')
        plan=prepare(read_snapshot(config),settings);apply_plan(plan)
        version,models=model_list(args.codex_exe,home)
        match=next(m for m in models if m['model']==settings.model)
        assert match['displayName']==settings.model and not match['hidden']
        report.append({'scenario':'generated-custom-name','model':match['model'],'displayName':match['displayName'],'passed':True})
        apply_plan(prepare_switch(read_snapshot(config),'account'))
        _,models=model_list(args.codex_exe,home)
        assert any(m['model']=='gpt-6-astra' for m in models)
        assert not any(m['model']==settings.model for m in models)
        report.append({'scenario':'account-restores-bundled-models','passed':True})
        selected=next(c for c in choices(read_snapshot(config)) if c['id']!='account')
        apply_plan(prepare_switch(read_snapshot(config),selected['id']))
        _,models=model_list(args.codex_exe,home)
        assert any(m['model']==settings.model and m['displayName']==settings.model for m in models)
        report.append({'scenario':'switch-back-restores-name','passed':True})
        from dataclasses import replace
        supplied={'models':[{'slug':'provider-custom','display_name':'old','context_window':999999,'model_messages':{'instructions_template':'Provider supplied instructions'},'input_modalities':['text']} ]}
        apply_plan(prepare(read_snapshot(config),replace(settings,model='provider-custom',catalog_bytes=json.dumps(supplied).encode())))
        _,models=model_list(args.codex_exe,home)
        assert any(m['model']=='provider-custom' and m['displayName']=='provider-custom' and m['inputModalities']==['text'] for m in models)
        report.append({'scenario':'imported-provider-catalog','passed':True})
    output={'codex':version,'scope':'isolated model/list only; no inference or real credentials','checks':report}
    (ROOT/'work/model-name-integration.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=True,indent=2))
if __name__=='__main__':main()
