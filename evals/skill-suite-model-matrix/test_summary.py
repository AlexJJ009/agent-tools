"""Denominator and paired-outcome regression tests using report-shaped records."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import summarize


def row(arm, rep, primary, guardrails=True, writing=True, case='H03'):
    return {'case':case,'arm':arm,'rep':rep,'primary':primary,
            'guardrails':guardrails,'writing':writing,
            'target_read_observed':False,'failures':{},'writing_failures':{},
            'raw':'/retained/raw.json','grade_path':'/retained/grade.json'}


def summary(rows,accepted=(),invalid=()):
    return {'rows':rows,'paired_outcomes':[{'case':'H03','rep':rep} for rep in accepted],
            'invalid_pairs':[{'case':'H03','rep':rep,'reasons':reasons} for rep,reasons in invalid],
            'pending':[]}


class PairDenominatorTests(unittest.TestCase):
    def test_unread_skill_still_contributes_actual_outcome(self):
        source=summary([row('control',1,True),row('skills',1,False)],
                       invalid=[(1,[summarize.READ_REASON])])
        original=copy.deepcopy(source)
        pairs,excluded=summarize.paired_rows(source)
        self.assertEqual(len(pairs),1)
        self.assertEqual(excluded,[])
        self.assertFalse(pairs[0]['body_confirmed'])
        self.assertEqual(summarize.metric(pairs,'primary')['skill_loss'],1)
        self.assertEqual(source,original)

    def test_only_read_reason_is_waived_not_structural_failures(self):
        source=summary([row('control',1,False),row('skills',1,True)],
                       invalid=[(1,[summarize.READ_REASON,'fixture differs or is missing'])])
        pairs,excluded=summarize.paired_rows(source)
        self.assertEqual(pairs,[])
        self.assertEqual(excluded,[{'case':'H03','rep':1,'reasons':['fixture differs or is missing']}])

    def test_missing_scored_arm_cannot_enter_denominator(self):
        for invalid,accepted in [([(1,[summarize.READ_REASON])],[]),([],[1])]:
            with self.subTest(invalid=invalid):
                pairs,excluded=summarize.paired_rows(summary([row('skills',1,True)],accepted,invalid))
                self.assertFalse(pairs)
                self.assertIn('missing scored arm',excluded[0]['reasons'])

    def test_four_cells_and_metrics_remain_independent(self):
        values=[(True,True),(False,True),(True,False),(False,False)]
        rows=[]
        for rep,(a,b) in enumerate(values,1):
            rows += [row('control',rep,a,False,True),row('skills',rep,b,True,False)]
        pairs,excluded=summarize.paired_rows(summary(rows,accepted=range(1,5)))
        self.assertFalse(excluded)
        self.assertEqual(summarize.metric(pairs,'primary'),{
            'n':4,'control':2,'skills':2,'both_pass':1,'skill_win':1,
            'skill_loss':1,'both_fail':1,'net_change':0.0})
        self.assertEqual(summarize.metric(pairs,'guardrails')['net_change'],1.0)
        self.assertEqual(summarize.metric(pairs,'writing')['net_change'],-1.0)

    def test_zero_eligible_pairs_is_unknown_not_zero_effect(self):
        self.assertEqual(summarize.metric([],'primary')['n'],0)
        self.assertIsNone(summarize.metric([],'primary')['net_change'])

    def test_export_keeps_assigned_and_read_subset_separate_per_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';output=Path(tmp)/'report'
            for model in ['model-a','model-b']:
                records=[row('control',1,True),row('skills',1,False),
                         row('control',2,False),row('skills',2,True)]
                data=summary(records,accepted=[2],invalid=[(1,[summarize.READ_REASON])])
                if model=='model-b':
                    data['invalid_pairs'][0]['reasons'].append('model/budget mismatch: effort')
                path=source/model/'suite'/'report'/'summary.json'
                path.parent.mkdir(parents=True);path.write_text(json.dumps(data))
            case={'id':'H03','target_skill':'teaching-reconstruction','capability':'explain causal order'}
            with patch.object(summarize.evaluate,'MODELS',('model-a','model-b')), \
                 patch.object(summarize.evaluate,'SUITES',{'suite':{}}), \
                 patch.object(summarize.evaluate,'dataset',return_value=[case]), \
                 patch.object(summarize.evaluate,'ensure_manifest',return_value={}):
                summarize.export(source,output)
            result=json.loads((output/'summary.json').read_text())
            a=result['models']['model-a']['cases']['H03']
            b=result['models']['model-b']['cases']['H03']
            self.assertEqual(a['all_assigned']['primary']['n'],2)
            self.assertEqual(a['all_assigned']['primary']['net_change'],0)
            self.assertEqual(a['confirmed_body']['primary']['n'],1)
            self.assertEqual(a['confirmed_body']['primary']['net_change'],1)
            self.assertEqual(b['all_assigned']['primary']['n'],1)
            self.assertEqual(len(result['models']['model-b']['exclusions']),1)
            self.assertTrue(result['no_pooled_effectiveness_score'])
            self.assertNotIn('overall_pass',result)


if __name__=='__main__':unittest.main()
