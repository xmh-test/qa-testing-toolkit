"""Behavior tests: status precedence, complete matrix, independent builds and resumption."""
import copy
import unittest
from execution_state import summarize


def fixture():
    return {'schema_version': 1, 'case_ids': ['C1'], 'platforms': ['macOS', 'Android'],
            'attempts': [], 'bugs': [], 'checks': [
                {'case_id': 'C1', 'platform': p, 'build': 'b1', 'applicable': True,
                 'assertions': [{'id': 'a', 'result': 'not_run'}, {'id': 'b', 'result': 'not_run'}],
                 'attempt_ids': [], 'bug_ids': [],
                 'cause': {'category': 'environment', 'details': 'not ready', 'resume_condition': 'connect'}}
                for p in ('macOS', 'Android')]}


def attempt(run, platform='macOS', aid='t1', results=('pass', 'not_run'), build='b1'):
    run['attempts'].append({'id': aid, 'case_id': 'C1', 'platform': platform, 'build': build,
                            'at': '2026-01-01T10:00:00+08:00', 'steps': ['observed UI'], 'evidence': ['shot.png']})
    c = next(c for c in run['checks'] if c['platform'] == platform)
    c['attempt_ids'].append(aid)
    c['build'] = build
    for a, result in zip(c['assertions'], results):
        a['result'] = result
        if result != 'not_run':
            a.update(attempt_id=aid, evidence=['shot.png'])
    return c


class RecordChecks(unittest.TestCase):
    def test_partial_resource_is_unexecuted_not_blocked(self):
        d = fixture(); attempt(d)
        s = summarize(d)
        self.assertEqual(s['statuses']['未执行'], 2)
        self.assertEqual(s['partial_progress'], 1)
        self.assertEqual(s['attempted_checks'], 1)

    def test_failure_wins_over_resource_gap(self):
        d = fixture(); c = attempt(d, results=('fail', 'not_run'))
        d['bugs'] = [{'id': 'B1'}]; c['bug_ids'] = ['B1']
        s = summarize(d)
        self.assertEqual(s['checks'][0]['status'], '失败')
        self.assertEqual(s['incomplete_checks'], 2)

    def test_missing_feature_reuses_bug_across_platforms(self):
        d = fixture(); d['bugs'] = [{'id': 'B1'}]
        c = attempt(d, results=('fail', 'not_run')); c['bug_ids'] = ['B1']
        d['checks'][1]['cause'] = {'category': 'product', 'details': 'dependent feature missing',
                                  'resume_condition': 'feature delivered', 'bug_ids': ['B1']}
        s = summarize(d)
        self.assertEqual(s['unique_bugs'], 1)
        self.assertEqual(s['statuses']['失败'], 1)
        self.assertEqual(s['statuses']['阻塞'], 1)

    def test_resume_preserves_attempts_and_does_not_complete_other_platform(self):
        d = fixture(); attempt(d)
        attempt(d, aid='t2', results=('pass', 'pass'))
        s = summarize(d)
        self.assertEqual(s['attempts'], 2)
        self.assertEqual(s['statuses']['通过'], 1)
        self.assertEqual(s['statuses']['未执行'], 1)
        self.assertEqual(s['complete_assertion_checks'], 1)

    def test_build_change_cannot_inherit_old_assertions(self):
        d = fixture(); c = attempt(d, results=('pass', 'pass')); c['build'] = 'b2'
        with self.assertRaisesRegex(ValueError, 'another build'):
            summarize(d)

    def test_unexecuted_rows_cannot_disappear(self):
        d = fixture(); d['checks'].pop()
        with self.assertRaisesRegex(ValueError, 'Matrix'):
            summarize(d)

    def test_not_applicable_requires_basis_and_is_not_in_denominator(self):
        d = fixture(); c = d['checks'][1]; c['applicable'] = False
        with self.assertRaisesRegex(ValueError, 'basis'):
            summarize(d)
        c['applicability_basis'] = 'platform has no such supported interface'
        s = summarize(d)
        self.assertEqual(s['applicable_checks'], 1)
        self.assertEqual(sum(s['statuses'].values()), 2)

    def test_cross_platform_attempt_and_duplicate_ids_rejected(self):
        d = fixture(); attempt(d)
        d['checks'][1]['attempt_ids'] = ['t1']
        with self.assertRaisesRegex(ValueError, 'Cross-platform'):
            summarize(d)
        d = fixture(); d['checks'].append(copy.deepcopy(d['checks'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            summarize(d)


    def test_excluded_special_cases_are_not_unexecuted_or_in_denominator(self):
        d = fixture()
        d['input_case_ids'] = ['C1', 'MOBILE-SPECIAL']
        d['excluded_cases'] = [{'case_id': 'MOBILE-SPECIAL', 'categories': ['mobile'],
                                'reason': 'special testing not enabled', 'enable_condition': 'explicit inclusion'}]
        result = summarize(d)
        self.assertEqual(result['input_design_cases'], 2)
        self.assertEqual(result['design_cases'], 1)
        self.assertEqual(result['excluded_special_cases'], 1)
        self.assertEqual(result['applicable_checks'], 2)
        self.assertEqual(result['statuses']['未执行'], 2)

    def test_included_special_with_missing_resource_still_unexecuted(self):
        d = fixture(); d['case_ids'] = ['MOBILE-SPECIAL']
        for c in d['checks']:
            c['case_id'] = 'MOBILE-SPECIAL'
        result = summarize(d)
        self.assertEqual(result['excluded_special_cases'], 0)
        self.assertEqual(result['statuses']['未执行'], 2)

    def test_special_scope_cannot_silently_drop_or_double_count_cases(self):
        d = fixture(); d['input_case_ids'] = ['C1', 'SPECIAL']
        with self.assertRaisesRegex(ValueError, 'inventory'):
            summarize(d)
        d['excluded_cases'] = [{'case_id': 'C1', 'categories': ['mobile'], 'reason': 'not enabled', 'enable_condition': 'include'}]
        with self.assertRaisesRegex(ValueError, 'overlap'):
            summarize(d)

    def test_all_input_cases_may_be_out_of_round_specials(self):
        d = fixture(); d['input_case_ids'] = ['C1']; d['case_ids'] = []; d['checks'] = []
        d['excluded_cases'] = [{'case_id': 'C1', 'categories': ['mobile'], 'reason': 'not enabled', 'enable_condition': 'include'}]
        result = summarize(d)
        self.assertEqual(result['design_cases'], 0)
        self.assertEqual(result['applicable_checks'], 0)
        self.assertEqual(sum(result['statuses'].values()), 0)


    def test_non_smoke_scope_exclusion_is_not_special_or_unexecuted(self):
        d = fixture(); d['input_case_ids'] = ['C1', 'FUNCTION-NON-SMOKE']
        d['excluded_cases'] = [{'case_id': 'FUNCTION-NON-SMOKE', 'kind': 'scope',
            'categories': ['functional'], 'reason': 'outside confirmed smoke list',
            'enable_condition': 'request functional scope'}]
        result = summarize(d)
        self.assertEqual(result['excluded_cases'], 1)
        self.assertEqual(result['excluded_special_cases'], 0)
        self.assertEqual(result['statuses']['未执行'], 2)
        self.assertEqual(result['matrix_checks'], 2)

    def test_scope_and_special_exclusions_count_separately(self):
        d = fixture(); d['input_case_ids'] = ['C1', 'NON-SMOKE', 'COMPAT']
        d['excluded_cases'] = [
            {'case_id': 'NON-SMOKE', 'kind': 'scope', 'categories': ['functional'],
             'reason': 'not smoke', 'enable_condition': 'include'},
            {'case_id': 'COMPAT', 'kind': 'special', 'categories': ['compatibility'],
             'reason': 'not enabled', 'enable_condition': 'include compatibility'}]
        result = summarize(d)
        self.assertEqual(result['input_design_cases'], 3)
        self.assertEqual(result['design_cases'], 1)
        self.assertEqual(result['excluded_cases'], 2)
        self.assertEqual(result['excluded_special_cases'], 1)


if __name__ == '__main__':
    unittest.main()
