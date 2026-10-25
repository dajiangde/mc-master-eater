#!/usr/bin/env python3
"""Build a standalone gallery from processed cards. Never publishes or changes Git."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit, urlunsplit


class GalleryReferences(HTMLParser):
    def __init__(self):
        super().__init__(); self.local = []; self.images = []; self.ids = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'article':
            match = re.match(r'U\d+\b', attrs.get('data-search', ''))
            if match: self.ids.append(match[0])
        for key in ('href', 'src'):
            value = attrs.get(key)
            if not value: continue
            uri = urlsplit(value)
            if uri.scheme:
                if uri.scheme != 'https' or not uri.hostname or uri.username or uri.password:
                    raise ValueError('Only attribution HTTPS URLs are allowed')
                if uri.query or uri.fragment or 'xhscdn' in uri.hostname:
                    raise ValueError('Signed/direct image references are not allowed')
            else:
                if value.startswith(('/', '#')) or '..' in Path(value).parts:
                    raise ValueError('All local references must stay in gallery')
                self.local.append(value)
        if tag == 'img': self.images.append(attrs.get('src', ''))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(card_root, output):
    card_root = Path(card_root).resolve(); output = Path(output).resolve()
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Use a new output directory with an existing parent')
    catalog = json.loads((card_root / 'catalog.json').read_text())
    rows = catalog['entries']; ids = [row['id'] for row in rows]
    if not ids or len(set(ids)) != len(ids) or 'U12' in ids:
        raise ValueError('Missing, duplicate, or retired card ID')
    checked = {}
    for row in rows:
        if not re.fullmatch(r'U\d{2,}', row['id']): raise ValueError('Invalid ID')
        for kind, folder in [('card', 'cards'), ('thumbnail', 'thumbnails')]:
            relative = f"{folder}/{row['id']}.png"
            path = (card_root / relative).resolve()
            if row[kind] != relative or not path.is_relative_to(card_root) or not path.is_file():
                raise ValueError('Processed asset missing or outside gallery')
            if digest(path) != row[kind + '_sha256']:
                raise ValueError('Processed asset hash mismatch')
            checked[relative] = path
    html = (card_root / 'index.html').read_text()
    # Remove maintenance-only entry and every bulk/data download from the footer.
    html, n = re.subn(r'<a\b[^>]*href="\.\./[^\"]*"[^>]*>.*?</a>', '', html, flags=re.S)
    if n != 1: raise ValueError('Unexpected maintenance navigation')
    html = re.sub(r'(<footer>)(.*?)(</footer>)',
                  lambda m: m[1] + re.sub(r'<a\b[^>]*>.*?</a>', '', m[2], flags=re.S).rstrip(' ·') + m[3],
                  html, flags=re.S)
    html = html.replace('下载原图', '下载卡片')
    html = html.replace('图片仅供本地研究。', '民间吃法整理，配图出处见来源链接。')
    html = html.replace('麦麦隐藏吃法 · 基础卡图库', '麦门老吃家 · 隐藏吃法图库')
    html = re.sub(r'href="(https://[^\"]+)"', lambda m: 'href="' + urlunsplit((*urlsplit(m[1])[:3], '', '')) + '"', html)
    if any(value in html for value in ['/Users/', '127.0.0.1', 'file://', 'source-images/', 'source_image', 'xsec_token', 'xhscdn']):
        raise ValueError('Local/research reference in gallery HTML')
    parser = GalleryReferences(); parser.feed(html)
    if parser.ids != ids or parser.images != [f'thumbnails/{i}.png' for i in ids]:
        raise ValueError('Gallery/card ID mismatch')
    if set(parser.local) != set(checked):
        raise ValueError('Unexpected gallery dependency')
    output.mkdir()
    for relative, path in checked.items():
        target = output / relative; target.parent.mkdir(exist_ok=True)
        shutil.copy2(path, target)
    (output / 'index.html').write_text(html)
    (output / '.nojekyll').write_text('')
    files = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    return {'card_count': len(ids), 'file_count': len(files), 'original_files': 0,
            'site_bytes': sum((output / name).stat().st_size for name in files), 'files': files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cards', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try: result = build(args.cards, args.output)
    except (ValueError, OSError, KeyError) as exc: parser.error(str(exc))
    if args.report: args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'files'}, ensure_ascii=False))


if __name__ == '__main__': main()
