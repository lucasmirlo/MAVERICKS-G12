import unittest
import json
from jev_requests import stage_a,stage_b,sentences

class JevContractTests(unittest.TestCase):
    def setUp(self):
        self.article={'news_id':'EX001','headline':'A plant stopped.','summary':'Aster Labs reports a two-day shutdown. Deliveries may be delayed.','Is_Risk':'SECRET_LABEL','Explanation':'ANSWER_KEY_MARKER'}
        self.suppliers=[{'supplier_id':'DEMO_A','name':'Aster Labs','country':'Spain','city':'Madrid'},{'supplier_id':'DEMO_B','name':'Boreal Packaging','country':'France','city':'Lyon'}]
    def test_only_allowed_input_reaches_model(self):
        for body in [stage_a(self.article,self.suppliers),stage_b(self.article,self.suppliers)]:
            encoded=json.dumps(body)
            self.assertNotIn('SECRET_LABEL',encoded)
            self.assertNotIn('ANSWER_KEY_MARKER',encoded)
    def test_multisupplier_is_not_single_choice(self):
        q=stage_a(self.article,self.suppliers)['questions']
        self.assertEqual(q['linked_DEMO_A']['type'],'noul')
        self.assertEqual(q['linked_DEMO_B']['type'],'noul')
        self.assertIn('DEMO_A',q['linked_DEMO_A']['instructions'])
    def test_batch_has_all_supplier_questions(self):
        q=stage_b(self.article,self.suppliers)['questions']
        self.assertEqual(len(q),12)
        self.assertEqual(len(q['severity_DEMO_A']['criteria']),10)
        self.assertIn('unknown',q['duration_DEMO_B']['criteria'])
    def test_quotes_are_exact_spans(self):
        for s in sentences(self.article):
            self.assertEqual(self.article[s['field']][s['start']:s['end']],s['text'])

if __name__=='__main__':unittest.main()
