#!/usr/bin/env python3
"""Check local HTML evidence links without accessing devices or the network."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        key = 'href' if tag == 'a' else 'src' if tag == 'img' else None
        if key and attrs.get(key):
            self.links.append((tag, attrs, attrs[key]))


def check(path):
    reports = (Path.cwd() / 'reports').resolve()
    errors = []
    if not path.is_relative_to(reports):
        errors.append('Report must be inside reports/')
    parser = Links()
    parser.feed(path.read_text(encoding='utf-8'))
    for tag, attrs, href in parser.links:
        if href.startswith('#'):
            continue
        url = urlsplit(href)
        if tag == 'a' and attrs.get('target') != '_blank':
            errors.append('Link must open a new tab: ' + href)
        if tag == 'a' and not {'noopener', 'noreferrer'}.issubset(set(attrs.get('rel', '').split())):
            errors.append('Missing link rel protection: ' + href)
        if url.scheme in {'http', 'https'}:
            continue
        if tag == 'img' and href.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,')):
            continue
        if url.scheme or url.netloc:
            errors.append('Unsupported link scheme: ' + href)
            continue
        target = (path.parent / unquote(url.path)).resolve()
        if not target.is_relative_to(reports):
            errors.append('Evidence outside reports/: ' + href)
        elif not target.is_file():
            errors.append('Missing local evidence: ' + href)
    return errors, len(parser.links)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    try:
        errors, count = check(args.report.resolve())
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
    if errors:
        parser.exit(1, '\n'.join(errors) + '\n')
    print('HTML link check passed: ' + str(count) + ' links/images; no business assertions checked')


if __name__ == '__main__':
    main()
