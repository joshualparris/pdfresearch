"""Value-redacted PDF fidelity measurements for local corpus audits.

Hashes compare values without writing text, form values, annotation contents or
link addresses into reports. A matching render is evidence at one resolution,
not a proof of all interactive PDF behaviour.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import fitz
from .pdf_links import file_spec_value, resolved_file


def digest(value) -> str:
    material = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(material.encode()).hexdigest()


def coordinates(value):
    return [round(float(x), 5) for x in value]


def widget_signature(page):
    values = []
    for w in page.widgets() or []:
        values.append({
            'name': w.field_name, 'value': w.field_value, 'type': w.field_type,
            'flags': w.field_flags, 'rect': coordinates(w.rect),
        })
    return len(values), digest(sorted(values, key=lambda x: json.dumps(x, sort_keys=True)))


def annotation_signature(page):
    values = []
    types = []
    for a in page.annots() or []:
        types.append(a.type[1])
        values.append({
            'type': a.type, 'rect': coordinates(a.rect), 'flags': a.flags,
            'opacity': a.opacity, 'colors': a.colors, 'vertices': a.vertices,
            'info': {k: v for k, v in a.info.items() if k != 'id'},
        })
    return sorted(types), digest(values)


def link_signatures(page, *, page_mapping=None, source_path=None, output_path=None):
    links = []
    for link in page.get_links():
        item = {k: v for k, v in link.items() if k not in {'xref', 'id'}}
        action = page.parent.xref_get_key(link['xref'], 'A/S')[1]
        if action == '/URI':
            item = {'kind': fitz.LINK_URI, 'from': link['from'],
                    'uri': link.get('uri', link.get('file', ''))}
        elif action in {'/Launch', '/GoToR'}:
            item['file'] = file_spec_value(page.parent, link['xref'], link.get('file', ''))
            if action == '/Launch':
                item['kind'] = fitz.LINK_LAUNCH
                for key in ['page', 'to', 'zoom']:
                    item.pop(key, None)
        for key in ['from', 'to']:
            if key in item and not isinstance(item[key], str):
                item[key] = coordinates(item[key])
        # The convenience API returns (0, 0) for some GoToR destinations. Audit
        # the original PDF view mode and coordinates rather than accepting that
        # lossy representation as a faithful destination measurement.
        dtype, dest = page.parent.xref_get_key(link['xref'], 'A/D')
        if dtype == 'null':
            dtype, dest = page.parent.xref_get_key(link['xref'], 'Dest')
        if dtype == 'array':
            item['destination_view'] = re.sub(r'^\[\s*\d+(?:\s+\d+\s+R)?\s*', '[', dest)
            item.pop('to', None)
            item.pop('zoom', None)
        if page_mapping is not None and item['kind'] == fitz.LINK_GOTO and item.get('page', -1) >= 0:
            target = item['page']
            if target in page_mapping:
                item['page'] = page_mapping[target]
            elif source_path is not None:
                item['kind'] = fitz.LINK_GOTOR
                item['file'] = str(Path(source_path).resolve())
        if item.get('file') and output_path is not None:
            item['file'] = resolved_file(item['file'], output_path)
        links.append(item)
    return len(links), digest(sorted(links, key=lambda x: json.dumps(x, sort_keys=True, default=str)))


def compare_pages(source, exported, *, page_mapping, source_path, output_path, render=False):
    """Compare one mapped page, returning hashes/counts and mismatch labels only."""
    result = {'source_page': source.number + 1, 'export_page': exported.number + 1, 'mismatches': []}
    pairs = {
        'text': (digest(source.get_text()), digest(exported.get_text())),
        'widgets': (widget_signature(source), widget_signature(exported)),
        'annotations': (annotation_signature(source), annotation_signature(exported)),
        'geometry': (
            (coordinates(source.mediabox), coordinates(source.cropbox), coordinates(source.rect), source.rotation),
            (coordinates(exported.mediabox), coordinates(exported.cropbox), coordinates(exported.rect), exported.rotation),
        ),
        'links': (
            link_signatures(source, page_mapping=page_mapping, source_path=source_path, output_path=source_path),
            link_signatures(exported, output_path=output_path),
        ),
        'transparency_group_present': (
            source.parent.xref_get_key(source.xref, 'Group')[0] != 'null',
            exported.parent.xref_get_key(exported.xref, 'Group')[0] != 'null',
        ),
    }
    if render:
        def pixels(page):
            pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
            return (pix.width, pix.height, hashlib.sha256(pix.samples).hexdigest())
        pairs['render_72dpi'] = (pixels(source), pixels(exported))
    for key, (a, b) in pairs.items():
        result[key] = {'source': a, 'export': b}
        if a != b:
            result['mismatches'].append(key)
    return result
