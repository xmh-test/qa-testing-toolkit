#!/usr/bin/env python3
"""Render normalized, redacted acceptance data. No app/device or network operations."""
import argparse
from collections import Counter
from html import escape
import json
import os
from pathlib import Path
from urllib.parse import quote

LABELS = {
    'passed': '通过', 'failed': '失败', 'blocked': '阻塞', 'interrupted': '未完成',
    'skipped': '跳过', 'not_run': '未执行', 'not_implemented': '未编写',
    'not_applicable': '不适用', 'covered': '关联用例',
}
EXECUTION = {'passed', 'failed', 'blocked', 'interrupted', 'skipped'}
COVERAGE = {'not_run', 'not_implemented', 'not_applicable', 'covered', 'blocked'}
MODES = {'automated': '自动', 'host_assisted': '宿主自动化辅助', 'manual_assisted': '人工辅助'}


def esc(value):
    return escape(str(value), quote=True)


def content(value):
    if isinstance(value, list):
        return '<ol>' + ''.join('<li>' + esc(v) + '</li>' for v in value) + '</ol>'
    return '<p>' + esc(value or '') + '</p>'


def render(source, destination):
    reports = (Path.cwd() / 'reports').resolve()
    if not destination.is_relative_to(reports):
        raise ValueError('HTML output must be inside the current project reports/ directory')
    data = json.loads(source.read_text())
    if data.get('schema_version') != 1:
        raise ValueError('Expected normalized schema_version=1; adapt project results first')
    platforms = data['platforms']
    if not platforms or len(set(platforms)) != len(platforms):
        raise ValueError('platforms must be non-empty and unique')
    cases = data['cases']
    ids = [c['case_id'] for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate case_id')
    attempts = data.get('attempts', [])
    histories = {}
    for a in attempts:
        if a['case_id'] not in ids or a['platform'] not in platforms:
            raise ValueError('Attempt references an unknown case/platform')
        if a['status'] not in EXECUTION:
            raise ValueError('Attempt status must be an execution result')
        if not isinstance(a.get('started'), bool):
            raise ValueError('Every attempt must record started as a boolean')
        if a['status'] in {'failed', 'blocked', 'interrupted'} and not a.get('description'):
            raise ValueError('Failure/blocker/interruption requires a readable description')
        if a.get('automation_mode', 'automated') not in MODES:
            raise ValueError('Unknown automation_mode')
        histories.setdefault((a['case_id'], a['platform']), []).append(a)
    totals = {p: dict(recorded=0, started=0, outcomes=Counter(), coverage=Counter()) for p in platforms}

    def asset(value, label, picture=False):
        if not value:
            return ''
        path = (source.parent / value).resolve()
        if not path.is_relative_to(reports):
            raise ValueError('Evidence must stay inside reports/: ' + str(value))
        if not path.is_file():
            return '<p>证据缺失：' + esc(value) + '</p>'
        href = esc(quote(os.path.relpath(path, destination.parent), safe='/'))
        link = '<a target="_blank" rel="noopener noreferrer" href="' + href + '">' + label + '</a>'
        if picture:
            if path.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
                raise ValueError('Screenshot must be PNG/JPEG')
            return '<figure><img alt="真实失败现场" loading="lazy" src="' + href + '"><figcaption>' + link + '</figcaption></figure>'
        return '<p>' + link + '</p>'

    def attempt_body(a):
        mode = MODES[a.get('automation_mode', 'automated')]
        body = '<p>' + esc(a.get('run_id', '')) + ' · ' + esc(a.get('timestamp', '')) + ' · ' + esc(mode) + '</p>'
        body += content(a.get('description', ''))
        if a.get('explanation_source'):
            body += '<p>说明来源：' + esc(a['explanation_source']) + '</p>'
        if a.get('category'):
            body += '<p>问题分类：' + esc(a['category']) + '</p>'
        if a.get('manual_steps'):
            body += '<h4>辅助步骤（与自动断言分开）</h4>' + content(a['manual_steps'])
        if a.get('error'):
            body += '<details><summary>原始错误</summary><pre>' + esc(a['error']) + '</pre></details>'
        return body + asset(a.get('log'), '查看日志') + asset(a.get('screenshot'), '查看原图', True)

    rows = []
    for c in cases:
        row = '<details class="case"><summary>' + esc(c['case_id']) + ' ' + esc(c['title']) + '</summary>'
        row += '<p>模块：' + esc(c.get('module', '')) + '</p><h4>步骤</h4>' + content(c.get('steps', []))
        row += '<h4>预期</h4>' + content(c.get('expected', []))
        for p in platforms:
            history = histories.get((c['case_id'], p), [])
            if history:
                a = history[-1]
                status = a['status']
                totals[p]['recorded'] += 1
                totals[p]['started'] += int(a['started'])
                totals[p]['outcomes'][status] += 1
                row += '<h3>' + esc(p) + ' · ' + LABELS[status] + '</h3>' + attempt_body(a)
                if len(history) > 1:
                    row += '<details><summary>历史尝试 ' + str(len(history) - 1) + '</summary>'
                    for old in history[:-1]:
                        row += '<h4>' + LABELS[old['status']] + '</h4>' + attempt_body(old)
                    row += '</details>'
            else:
                status = c.get('availability', {}).get(p, 'not_implemented')
                if status not in COVERAGE:
                    raise ValueError('Invalid unexecuted availability: ' + status)
                totals[p]['coverage'][status] += 1
                label = '环境前置' if status == 'blocked' else LABELS[status]
                row += '<h3>' + esc(p) + ' · ' + label + '</h3>' + content(c.get('notes', {}).get(p, ''))
        rows.append(row + '</details>')
    summary = '<p>设计用例：' + str(len(cases)) + '；重试不增加用例数量。</p>'
    for p, t in totals.items():
        summary += '<section><h2>' + esc(p) + '</h2><p>运行记录 ' + str(t['recorded']) + '；实际启动 ' + str(t['started']) + '</p><p>'
        summary += ' / '.join(('运行阻塞' if k == 'blocked' else LABELS[k]) + ' ' + str(v) for k, v in sorted(t['outcomes'].items()))
        summary += '</p><p>尚无记录：' + ' / '.join(('环境前置' if k == 'blocked' else LABELS[k]) + ' ' + str(v) for k, v in sorted(t['coverage'].items())) + '</p></section>'
    issues = '<h2>本地问题</h2><pre>' + esc(json.dumps(data.get('issues', []), ensure_ascii=False, indent=2)) + '</pre>'
    title = esc(data.get('title', '验收测试报告'))
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>' + title + '</title>'
    page += '<style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:0 20px;line-height:1.6}section,.case{border:1px solid #ccc;padding:16px;margin:12px 0;border-radius:8px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%;max-height:600px}a{overflow-wrap:anywhere}</style>'
    page += '<h1>' + title + '</h1><p>结果来自已解析的执行记录；辅助动作单独标记，原生证据独立保留。</p>' + summary + ''.join(rows) + issues + '</html>'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page, encoding='utf-8')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(render(args.input.resolve(), args.output.resolve()))
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.exit(2, 'Report generation failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
