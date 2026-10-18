import unittest
from scoring import priority, decisions

def case(**kwargs):
    values=dict(is_risk=True,severity=9,criticality='High',single_source='Y',
                share_category_pct=40,inventory_days=30,lead_days=90)
    values.update(kwargs)
    return priority(**values)

class PriorityTests(unittest.TestCase):
    def test_hand_calculated_example(self):
        self.assertEqual(case()['priority'],83.6)
        self.assertAlmostEqual(case()['factors']['B'],2/3)
    def test_nonrisk_and_resolution(self):
        self.assertEqual(case(is_risk=False)['priority'],0)
        self.assertEqual(case(active=False)['priority'],0)
    def test_no_double_single_source(self):
        a=case()['priority']; b=case(single_source='N')['priority']
        self.assertEqual(b,70.1)
        self.assertLess(a,2*b)
    def test_bounds_and_monotonicity(self):
        for c in ['High','Medium','Low']:
            for u in ['Y','N']:
                for cover in [0,20,45,90]:
                    scores=[case(severity=s,criticality=c,single_source=u,inventory_days=cover)['priority'] for s in range(1,11)]
                    self.assertEqual(scores,sorted(scores))
                    self.assertTrue(all(0<=s<=100 for s in scores))
        cover_scores=[case(inventory_days=v)['priority'] for v in [0,20,30,60,90,180]]
        self.assertEqual(cover_scores,sorted(cover_scores,reverse=True))
    def test_spend_and_criticality_are_monotonic(self):
        self.assertEqual([case(share_category_pct=v)['priority'] for v in [0,10,50,100]],sorted(case(share_category_pct=v)['priority'] for v in [0,10,50,100]))
        self.assertLess(case(criticality='Low')['priority'],case(criticality='Medium')['priority'])
        self.assertLess(case(criticality='Medium')['priority'],case(criticality='High')['priority'])
    def test_unknown_is_not_zero_or_worst_buffer(self):
        unknown=case(inventory_days=None)
        zero=case(inventory_days=0)
        self.assertNotIn('B',unknown['factors'])
        self.assertIn('inventory_missing',unknown['warnings'])
        self.assertEqual(zero['factors']['B'],1)
    def test_services_omit_buffer_without_review(self):
        result=case(inventory_days=None,inventory_applicability='not_applicable')
        self.assertNotIn('B',result['factors'])
        self.assertFalse(result['needs_review'])
    def test_duration_can_exceed_existing_cover(self):
        a=case(inventory_days=90,lead_days=60)
        b=case(inventory_days=90,lead_days=60,disruption_days=180)
        self.assertEqual(a['factors']['B'],0)
        self.assertEqual(b['factors']['B'],0.5)
        self.assertGreater(b['priority'],a['priority'])
    def test_missing_all_exposure(self):
        result=case(criticality=None,single_source=None,share_category_pct=None,inventory_days=None,lead_days=None)
        self.assertIsNone(result['priority'])
        self.assertTrue(result['needs_review'])
    def test_invalid_data_rejected(self):
        for override in [dict(share_category_pct=101),dict(lead_days=0),dict(inventory_days=-1),dict(severity=float('nan')),dict(severity=11),dict(criticality='Unknown')]:
            with self.assertRaises(ValueError):case(**override)
    def test_sound_and_export_invariants(self):
        positive=decisions(p_link=.99,p_risk=.01,p_urgent=.95,impact_status='positive')
        self.assertTrue(positive['linked'])
        self.assertEqual(positive['is_risk'],'N')
        self.assertEqual(positive['urgent'],'N')
        self.assertFalse(positive['sound_eligible'])
        uncertain=decisions(p_link=.55,p_risk=.98,p_urgent=.99)
        self.assertTrue(uncertain['needs_review'])
        self.assertFalse(uncertain['sound_eligible'])
        urgent=decisions(p_link=.99,p_risk=.99,p_urgent=.98)
        self.assertTrue(urgent['sound_eligible'])
        review=decisions(p_link=.99,p_risk=.99,p_urgent=.98,needs_review=True)
        self.assertFalse(review['sound_eligible'])
    def test_confidence_does_not_change_priority(self):
        score=case()['priority']
        decisions(p_link=.55,p_risk=.99,p_urgent=.99)
        self.assertEqual(case()['priority'],score)

if __name__=='__main__': unittest.main()
