"""Offline validation of this handoff. Does not call JEV or solve input articles."""
from pathlib import Path
import copy
import hashlib
import json
import re
import sys
import unittest
from datetime import datetime, timezone

try:
    from jsonschema import Draft202012Validator
except ImportError:
    raise SystemExit('Install reference/requirements.txt before running this validator.')

ROOT=Path(__file__).resolve().parents[1]
def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))

def main():
    checks=[]
    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append({'name':name,'status':'passed'})
    required=['00_LEEME.md','01_PROMPT_MAESTRO_CODEX.md',
      'docs/02_ESPECIFICACION.md','docs/03_MOTOR_RIESGO.md','docs/04_JEV_Y_RSS.md',
      'docs/05_DISENO_E_INTERACCION.md','docs/06_RAILWAY.md','docs/07_ACEPTACION_Y_DEMO.md',
      'docs/08_FUENTES_Y_VERIFICACION.md','prompts/01_IMPLEMENTACION_POR_ETAPAS.md',
      'prompts/02_DISENO_UI.md','prompts/03_AUDITORIA_Y_ENTREGA.md',
      'prompts/04_TEXTOS_Y_BORRADORES.md','contracts/README.md',
      'Supplier_Risk_Radar_Especificacion.docx']
    check('required_deliverables',all((ROOT/x).is_file() for x in required))
    for p in ROOT.rglob('*.json'):
        json.loads(p.read_text())
    check('all_json_parse',True)
    manifest=read('evidence/input_manifest.json')
    check('answer_key_excluded',manifest['answer_key_included'] is False and
          not any('answer_key' in p.name.lower() for p in ROOT.rglob('*')))
    check('input_manifest_exact',len(manifest['files'])==6)
    for entry in manifest['files']:
        data=(ROOT/entry['path']).read_bytes()
        check('sha256:'+entry['path'],hashlib.sha256(data).hexdigest()==entry['sha256'])
    policy=read('config/risk_policy.json')
    check('weights_sum_one',abs(sum(policy['weights'].values())-1)<1e-9)
    check('severity_has_ten_levels',len(policy['severity_rubric'])==10)
    check('model_version_pinned',re.fullmatch(r'jev-\d+\.\d+\.\d+',policy['default_model']) is not None)
    feeds=read('config/rss_sources.json')['sources']
    evidence=read('evidence/rss_verification.json')
    check('six_unique_rss',len(feeds)==6 and len({f['url'] for f in feeds})==6)
    verified={x['url'] for x in evidence if x['http_status']==200 and x['item_count']>0}
    check('rss_matches_recorded_checks',all(x['url'] in verified for x in feeds))
    env=(ROOT/'config/env.example').read_text()
    check('empty_secrets',all(re.search('^'+k+'=$',env,re.M) for k in
          ['TYPESAFE_API_KEY','ADMIN_PASSWORD','SESSION_SECRET']))
    schema=read('contracts/article_analysis.schema.json')
    Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema)
    sample=read('fixtures/analysis_valid.json')
    validator.validate(sample)
    check('schema_and_valid_fixture',True)
    bad=copy.deepcopy(sample);bad['assessments'][0]['priority']=101
    check('schema_rejects_out_of_range',not validator.is_valid(bad))
    bad=copy.deepcopy(sample);bad['is_risk']='N';bad['urgent']='Y'
    check('schema_rejects_urgent_nonrisk',not validator.is_valid(bad))
    bad=copy.deepcopy(sample);bad['analysis_status']='error'
    check('schema_rejects_error_as_success',not validator.is_valid(bad))
    for name in ['jev_stage_a_request.json','jev_stage_b_request.json']:
        payload=read('fixtures/'+name)
        check('model:'+name,payload['model']==policy['default_model'])
        check('unlabelled:'+name,not any(k in json.dumps(payload['state']) for k in
              ['Affected_Supplier_IDs','Is_Risk','Urgent','Explanation','SECRET_LABEL']))
    for p in ROOT.rglob('*.md'):
        for rel in re.findall(r'`((?:docs|prompts|config|reference|contracts|inputs|evidence)/[^` ]+\.(?:md|json|py|xlsx|docx|png|txt))`',p.read_text()):
            if rel=='evidence/validation_report.json':continue
            check('reference:'+str(p.relative_to(ROOT))+':'+rel,(ROOT/rel).is_file())
    suite=unittest.defaultTestLoader.discover(str(ROOT/'reference'),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    check('reference_tests',result.wasSuccessful())
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'passed',
      'reference_tests_run':result.testsRun,'checks':checks,
      'not_tested':['authenticated_jev','railway_deployment','app_e2e','device_audio','challenge_predictions']}
    (ROOT/'evidence/validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f'PASS: {len(checks)} bundle checks and {result.testsRun} reference tests. No API calls.')

if __name__=='__main__':main()
