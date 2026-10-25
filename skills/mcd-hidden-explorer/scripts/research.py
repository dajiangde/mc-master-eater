#!/usr/bin/env python3
"""Read a local research correspondence table without changing the public catalog."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from explore import lookup

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = SKILL_ROOT.parents[1] / 'work/assets/hidden-menu-photos-20261024/图片餐品对应表.json'
MODE = 'local_research'
NOTICE = '本地研究候选，非公开正式收录；待核项保留。参考门店记录是历史证据，不保证当前库存、价格或优惠可用。'
IMAGE_TYPES = {'.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
               '.png': 'image/png', '.gif': 'image/gif'}
PENDING_FIELDS = ('blocking_gaps', 'recipe_pending_items', 'product_name_pending_items',
                  'purchase_constraints', 'image_pending_items')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _source_url(url):
    _require(isinstance(url, str), 'Research source needs a URL')
    parts = urlsplit(url)
    _require(parts.scheme == 'https' and parts.hostname and not parts.username and not parts.password,
             'Research sources must use public HTTPS URLs')


def load_research(source):
    """Create an in-memory view. Never export, import, or promote catalog records."""
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ValueError('Local research data not found; provide --source with the correspondence JSON. '
                         'No fallback to the public catalog.')
    raw_bytes = source.read_bytes()
    raw = json.loads(raw_bytes)
    _require(isinstance(raw, dict) and raw.get('schema_version') == 3
             and isinstance(raw.get('entries'), list) and isinstance(raw.get('images'), list),
             'Expected research correspondence schema 3, not a public catalog')
    ids = [row.get('record_id') for row in raw['entries'] if isinstance(row, dict)]
    _require(len(ids) == len(raw['entries']) and all(isinstance(i, str) and re.fullmatch(r'[A-Z]{1,3}[0-9]{2,4}', i) for i in ids)
             and len(ids) == len(set(ids)), 'Invalid or duplicate research record IDs')
    image_root = (source.parent / 'images').resolve()
    images = {}
    for photo in raw['images']:
        _require(isinstance(photo, dict), 'Invalid research image record')
        image_id = photo.get('image_id')
        _require(isinstance(image_id, str) and image_id and image_id not in images, 'Invalid or duplicate image IDs')
        relative = photo.get('path')
        _require(isinstance(relative, str) and not Path(relative).is_absolute()
                 and Path(relative).parts[:1] == ('images',), 'Image path must be relative to images/')
        path = (source.parent / relative).resolve()
        _require(path.is_relative_to(image_root) and path.is_relative_to(source.parent)
                 and path.is_file(), 'Image missing or outside research images/: ' + relative)
        _require(path.suffix.lower() in IMAGE_TYPES, 'Unsupported research image type')
        _require(photo.get('record_id') in ids, 'Image references an unknown research record')
        digest = photo.get('sha256')
        _require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'Image SHA-256 is required')
        _require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'Image hash mismatch: ' + relative)
        images[image_id] = {**copy.deepcopy(photo), 'absolute_path': str(path),
                            'mime_type': IMAGE_TYPES[path.suffix.lower()]}
    entries = []
    attached_images = set()
    for original in raw['entries']:
        row = copy.deepcopy(original)
        _require(isinstance(row.get('dish_name'), str) and row['dish_name'].strip(), 'Research dish needs a name')
        _require(row.get('evidence_status') in ('cover_only', 'reported_recipe'), 'Unknown research evidence status')
        _require(isinstance(row.get('recipe_sources'), list) and row['recipe_sources'], 'Research sources are required')
        for origin in row['recipe_sources']:
            _require(isinstance(origin, dict), 'Invalid research source')
            _source_url(origin.get('url'))
        _require(isinstance(row.get('image_ids'), list), 'Research image_ids must be a list')
        _require(len(row['image_ids']) == len(set(row['image_ids'])), 'Duplicate image in a research record')
        photos = []
        for image_id in row['image_ids']:
            _require(image_id in images and images[image_id]['record_id'] == row['record_id'],
                     'Image-to-recipe association mismatch: ' + str(image_id))
            photos.append(copy.deepcopy(images[image_id]))
            attached_images.add(image_id)
        products = row.get('needed_products_as_reported', [])
        _require(isinstance(products, list) and all(isinstance(p, str) for p in products), 'Invalid reported products')
        method = row.get('method_as_reported')
        _require(method is None or isinstance(method, str), 'Invalid reported method')
        _require(row['evidence_status'] != 'cover_only' or (not products and not method),
                 'Cover-only leads cannot contain an inferred recipe')
        _require(type(row.get('eligible_for_actionable_pool', False)) is bool, 'Actionable status must be a boolean')
        mappings = row.get('product_name_mappings', [])
        _require(isinstance(mappings, list) and all(isinstance(p, dict) for p in mappings), 'Invalid product mappings')
        meals = []
        for mapping in mappings:
            name = mapping.get('mainland_display_name') or mapping.get('source_name')
            _require(isinstance(name, str) and name.strip(), 'Product mapping needs an evidenced display name')
            aliases = [mapping.get('source_name'), mapping.get('mainland_canonical_name')]
            meals.append({**copy.deepcopy(mapping), 'name': name,
                          'aliases': list(dict.fromkeys(x for x in aliases if x and x != name))})
        if not meals:
            meals = [{'name': product, 'aliases': [], 'mapping_status': 'source_term_only'} for product in products]
        entry = {'id': row['record_id'], 'name': row['dish_name'], 'aliases': [],
                 'recipe_status': row['evidence_status'], 'sources': copy.deepcopy(row['recipe_sources']),
                 'source_url': row['recipe_sources'][0]['url'], 'images': photos,
                 'associated_meals': meals, 'needed_products_as_reported': copy.deepcopy(products),
                 'method_as_reported': method, 'quantity_evidence': row.get('quantity_evidence'),
                 'collection_status': row.get('collection_status'),
                 'eligible_for_actionable_pool': row.get('eligible_for_actionable_pool', False),
                 'pending_items': {key: copy.deepcopy(row.get(key, [])) for key in PENDING_FIELDS},
                 'research_evidence': row}
        entries.append(entry)
    _require(attached_images == set(images), 'Unattached research images; repair the correspondence table')
    return {'schema_version': 'local-research-v1', 'mode': MODE, 'notice': NOTICE,
            'source_file': str(source), 'source_sha256': hashlib.sha256(raw_bytes).hexdigest(),
            'source_scope': raw.get('scope'), 'entries': entries, 'image_count': len(images)}


def envelope(data):
    return {key: data[key] for key in ('mode', 'notice', 'source_file', 'source_sha256', 'source_scope')}


def summary_entry(entry):
    return {key: value for key, value in entry.items() if key != 'research_evidence'}


def search(data, query):
    terms = query.casefold().split()
    _require(bool(terms), 'Provide a nonempty research keyword')
    found = []
    for row in data['entries']:
        raw = row['research_evidence']
        # Search names/observations, not unrelated metadata, URLs or boilerplate warnings.
        text = [row['id'], row['name'], raw.get('dish_name_as_reported', ''),
                raw.get('observed_content', ''), *row['needed_products_as_reported']]
        for meal in row['associated_meals']:
            text.extend([meal['name'], *meal.get('aliases', [])])
        haystack = ' '.join(str(part) for part in text if part).casefold()
        if all(term in haystack for term in terms):
            found.append(row)
    return found


def load_batch(path, data):
    batch = json.loads(Path(path).read_text(encoding='utf-8'))
    _require(isinstance(batch, dict) and batch.get('mode') == MODE
             and batch.get('source_sha256') == data['source_sha256'],
             'Wrong-mode or stale research batch; create a new batch for this source')
    ids = batch.get('ids')
    _require(isinstance(ids, list) and ids and all(isinstance(i, str) for i in ids)
             and len(ids) == len(set(ids)), 'Invalid research batch IDs')
    for ident in ids:
        lookup(data, ident)
    return batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE,
                        help='Local correspondence JSON; never the public catalog')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    sub.add_parser('list')
    find = sub.add_parser('search')
    find.add_argument('query')
    select = sub.add_parser('lookup')
    select.add_argument('selection')
    select.add_argument('--batch', type=Path)
    batch_parser = sub.add_parser('batch')
    batch_parser.add_argument('ids', nargs='+')
    batch_parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        data = load_research(args.source)
        result = envelope(data)
        if args.command == 'lookup':
            batch = load_batch(args.batch, data) if args.batch else None
            result.update(lookup(data, args.selection, batch))
            result['next_action'] = 'review_research_evidence'
        elif args.command == 'batch':
            ids = [lookup(data, ident)['canonical_id'] for ident in args.ids]
            _require(len(ids) == len(set(ids)), 'Research batch cannot repeat an ID')
            output = args.output.expanduser().resolve()
            _require(not output.is_relative_to(SKILL_ROOT), 'Keep research batch files outside the public Skill')
            with output.open('x', encoding='utf-8') as stream:
                json.dump({**envelope(data), 'ids': ids}, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            result.update(ids=ids, batch_file=str(output))
        elif args.command == 'validate':
            result.update(valid=True, count=len(data['entries']), images=data['image_count'],
                          actionable_count=sum(row['eligible_for_actionable_pool'] is True for row in data['entries']))
        else:
            rows = search(data, args.query) if args.command == 'search' else data['entries']
            result.update(count=len(rows), total_count=len(data['entries']),
                          entries=[summary_entry(row) for row in rows])
            if args.command == 'search':
                result['query'] = args.query
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
