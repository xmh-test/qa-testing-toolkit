#!/usr/bin/env python3
"""Validate current execution snapshots and derive consistent statistics. No device access."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import tempfile

STATUSES = ('通过', '失败', '阻塞', '未执行', '不适用')
CATEGORIES = {'product', 'environment', 'permission', 'tool', 'data', 'requirement'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(values, label):
    require(len(values) == len(set(values)), f'Duplicate {label}')


def evidence(paths, root):
    require(isinstance(paths, list), 'evidence must be an array')
    for raw in paths:
        p = Path(raw)
        require(not p.is_absolute() and p.parts and '..' not in p.parts, 'Evidence must be a relative in-run path')
        if root is not None:
            target = (root / p).resolve()
            require(target.is_relative_to(root.resolve()) and target.is_file(), f'Missing evidence: {raw}')


def summarize(run, root=None):
    require(run.get('schema_version') == 1, 'Unsupported schema_version')
    case_ids, platforms = run['case_ids'], run['platforms']
    unique(case_ids, 'case IDs')
    unique(platforms, 'platform IDs')
    require(platforms, 'Platform inventory cannot be empty')
    input_case_ids = run.get('input_case_ids', case_ids)
    unique(input_case_ids, 'input case IDs')
    excluded = run.get('excluded_cases', [])
    excluded_ids = [c['case_id'] for c in excluded]
    unique(excluded_ids, 'excluded case IDs')
    require(not set(case_ids) & set(excluded_ids), 'Included and excluded cases overlap')
    require(set(case_ids) | set(excluded_ids) == set(input_case_ids), 'Input inventory must match included plus excluded cases')
    for c in excluded:
        require(c.get('categories') and c.get('reason') and c.get('enable_condition'), 'Excluded case needs category, reason and enable condition')
    for c in excluded:
        require(c.get('kind', 'special') in ('scope', 'special'), 'Excluded case kind must be scope or special')
    attempts = run['attempts']
    unique([a['id'] for a in attempts], 'attempt IDs')
    by_id = {a['id']: a for a in attempts}
    for a in attempts:
        require(a['case_id'] in case_ids and a['platform'] in platforms, 'Attempt outside declared matrix')
        require(a.get('build') and a.get('at') and isinstance(a.get('steps'), list) and a['steps'], 'Attempt needs build/time/actual steps')
        evidence(a.get('evidence', []), root)
    bugs = run['bugs']
    unique([b['id'] for b in bugs], 'bug IDs: merge duplicate records first')
    bug_ids = {b['id'] for b in bugs}
    rows, keys = [], []
    for c in run['checks']:
        key = (c['case_id'], c['platform'])
        keys.append(key)
        require(key[0] in case_ids and key[1] in platforms, 'Check outside declared matrix')
        require(c.get('build'), 'Check needs actual build or explicit unverified label')
        require(isinstance(c['applicable'], bool), 'applicable must be boolean')
        ids = c.get('attempt_ids', [])
        unique(ids, 'check attempt IDs')
        for aid in ids:
            require(aid in by_id, f'Unknown attempt: {aid}')
            require((by_id[aid]['case_id'], by_id[aid]['platform']) == key, 'Cross-platform/case attempt reuse')
        assertions = c['assertions']
        unique([a['id'] for a in assertions], 'assertion IDs')
        require(assertions or not c['applicable'], 'Applicable check needs predefined required assertions')
        for a in assertions:
            require(a['result'] in ('pass', 'fail', 'not_run'), 'Unknown assertion result')
            if a['result'] != 'not_run':
                require(a.get('attempt_id') in ids, 'Executed assertion needs linked attempt')
                require(by_id[a['attempt_id']]['build'] == c['build'], 'Cannot inherit assertion from another build')
                require(a.get('evidence'), 'Executed assertion needs supporting evidence')
                evidence(a['evidence'], root)
        results = [a['result'] for a in assertions]
        done = bool(results) and all(r != 'not_run' for r in results)
        current_ids = [aid for aid in ids if by_id[aid]['build'] == c['build']]
        progress = '完成' if done else '部分完成' if current_ids or any(r != 'not_run' for r in results) else '未开始'
        cause = c.get('cause')
        if c['applicable'] and not done:
            require(cause and cause.get('category') in CATEGORIES and cause.get('details') and cause.get('resume_condition'), 'Incomplete check needs cause and resume condition')
        if cause:
            require(cause.get('category') in CATEGORIES, 'Unknown cause category')
            require(set(cause.get('bug_ids', [])) <= bug_ids, 'Unknown associated bug')
            if cause['category'] == 'product':
                require(cause.get('bug_ids'), 'Product blocker needs bug linkage')
        require(set(c.get('bug_ids', [])) <= bug_ids, 'Unknown check bug')
        if not c['applicable']:
            require(c.get('applicability_basis'), 'Not applicable needs explicit basis')
            status, progress = '不适用', '完成'
        elif 'fail' in results:
            require(c.get('bug_ids'), 'Failed check needs local bug linkage')
            status = '失败'
        elif done:
            status = '通过'
        elif cause['category'] == 'product':
            status = '阻塞'
        else:
            status = '未执行'
        rows.append(dict(case_id=key[0], platform=key[1], build=c['build'], status=status, progress=progress,
                         attempted_current_build=bool(current_ids)))
    unique(keys, 'case/platform checks')
    require(set(keys) == {(c, p) for c in case_ids for p in platforms}, 'Matrix must include every case/platform, including not applicable')
    for aid, a in by_id.items():
        require(any(aid in c.get('attempt_ids', []) for c in run['checks']), f'Orphan attempt: {aid}')
    counts = dict.fromkeys(STATUSES, 0)
    counts.update(Counter(r['status'] for r in rows))
    grouped = []
    for platform, build in sorted({(r['platform'], r['build']) for r in rows}):
        subset = [r for r in rows if (r['platform'], r['build']) == (platform, build)]
        grouped.append(dict(platform=platform, build=build, statuses={s: sum(r['status'] == s for r in subset) for s in STATUSES},
                            partial_progress=sum(r['progress'] == '部分完成' for r in subset)))
    return dict(schema_version=1, design_cases=len(case_ids), input_design_cases=len(input_case_ids),
                excluded_cases=len(excluded),
                excluded_special_cases=sum(c.get('kind', 'special') == 'special' for c in excluded), matrix_checks=len(rows),
                applicable_checks=len(rows)-counts['不适用'], statuses=counts,
                attempts=len(attempts), unique_bugs=len(bugs),
                attempted_checks=sum(r['attempted_current_build'] and r['status'] != '不适用' for r in rows),
                complete_assertion_checks=sum(r['progress'] == '完成' and r['status'] != '不适用' for r in rows),
                incomplete_checks=sum(r['progress'] != '完成' for r in rows),
                partial_progress=sum(r['progress'] == '部分完成' for r in rows), by_platform_build=grouped, checks=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = summarize(json.loads(args.input.read_text()), args.input.parent)
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    data = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        require(args.output.resolve() != args.input.resolve(), 'Output must not overwrite execution source')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=args.output.parent, prefix='.summary-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(data)
            os.replace(name, args.output)
        finally:
            Path(name).unlink(missing_ok=True)
    else:
        print(data, end='')


if __name__ == '__main__':
    main()
