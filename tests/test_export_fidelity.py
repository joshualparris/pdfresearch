from pathlib import Path

import fitz

from pdfresearch.pipeline import _write_segment_pdf
from pdfresearch.fidelity import compare_pages


def widget_values(page):
    return sorted((w.field_name, w.field_type, w.field_value) for w in page.widgets() or [])


def test_export_preserves_pdf_features_and_cross_document_navigation(tmp_path: Path):
    source = tmp_path / 'source.pdf'
    output = tmp_path / 'split' / 'export.pdf'
    with fitz.open() as doc:
        for i in range(4):
            page = doc.new_page(width=460 if i == 2 else 595, height=710 if i == 2 else 842)
            page.insert_text((50, 150), f'Synthetic source page {i}')
        page = doc[1]
        page.draw_rect(fitz.Rect(80, 200, 200, 300), color=(1, 0, 0), fill=(0, 0, 1), fill_opacity=0.35)
        doc.xref_set_key(page.xref, 'Group', '<</Type/Group/S/Transparency/CS/DeviceRGB>>')
        widget = fitz.Widget()
        widget.field_name = 'synthetic_name'
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_value = 'Editable synthetic value'
        widget.rect = fitz.Rect(40, 50, 350, 80)
        page.add_widget(widget)
        page.add_text_annot((350, 220), 'Synthetic annotation')
        page.add_highlight_annot(fitz.Rect(40, 140, 230, 154))
        page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(30, 400, 130, 420), 'uri': 'https://example.com/synthetic'})
        page.insert_link({'kind': fitz.LINK_GOTO, 'from': fitz.Rect(30, 430, 130, 450), 'page': 3, 'to': fitz.Point(50, 150)})
        page.insert_link({'kind': fitz.LINK_GOTO, 'from': fitz.Rect(30, 460, 130, 480), 'page': 0, 'to': fitz.Point(50, 150)})
        page.insert_link({'kind': fitz.LINK_LAUNCH, 'from': fitz.Rect(30, 490, 130, 510), 'file': 'notes.txt'})
        page = doc.reload_page(page)
        file_spec = doc.get_new_xref()
        doc.update_object(file_spec, '<</Type/Filespec/F(notes.txt)/UF(notes.txt)/Desc(Synthetic retained description)>>')
        action = doc.get_new_xref()
        doc.update_object(action, f'<</S/Launch/F {file_spec} 0 R>>')
        doc.xref_set_key(page.get_links()[-1]['xref'], 'A', f'{action} 0 R')
        shared = doc[3]
        shared.insert_link({'kind': fitz.LINK_LAUNCH, 'from': fitz.Rect(30, 490, 130, 510), 'file': 'notes.txt'})
        shared = doc.reload_page(shared)
        doc.xref_set_key(shared.get_links()[-1]['xref'], 'A', f'{action} 0 R')
        page = doc[2]
        image = b'P6\n2 2\n255\n' + bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0])
        page.insert_image(fitz.Rect(50, 250, 180, 380), stream=image)
        page.set_cropbox(fitz.Rect(10, 20, 450, 700))
        page.set_rotation(90)
        doc.save(source)
    with fitz.open(source) as src:
        _write_segment_pdf(src, [2, 3, 4], output, 'Synthetic feature coverage')
        with fitz.open(output) as dst:
            for original, exported in [(1, 0), (2, 1), (3, 2)]:
                a, b = src[original], dst[exported]
                assert a.get_text() == b.get_text()
                assert (a.rect, a.mediabox, a.cropbox, a.rotation) == (b.rect, b.mediabox, b.cropbox, b.rotation)
                assert widget_values(a) == widget_values(b)
                assert [x.type for x in a.annots() or []] == [x.type for x in b.annots() or []]
                assert a.get_pixmap().samples == b.get_pixmap().samples
                audit = compare_pages(a, b, page_mapping={1: 0, 2: 1, 3: 2},
                                      source_path=source, output_path=output, render=True)
                assert not audit['mismatches'], audit
            assert dst.xref_get_key(dst[0].xref, 'Group')[0] == 'dict'
            links = dst[0].get_links()
            assert len(links) == 4
            assert next(x for x in links if x['kind'] == fitz.LINK_GOTO)['page'] == 2
            remote = next(x for x in links if x['kind'] == fitz.LINK_GOTOR)
            assert remote['page'] == 0
            assert (output.parent / remote['file']).resolve() == source.resolve()
            assert next(x for x in links if x['kind'] == fitz.LINK_URI)['uri'] == 'https://example.com/synthetic'
            launched = next(x for x in links if x.get('file', '').endswith('notes.txt'))
            assert (output.parent / launched['file']).resolve() == (source.parent / 'notes.txt').resolve()
            assert dst.xref_get_key(launched['xref'], 'A/S')[1] == '/Launch'
            assert dst.xref_get_key(launched['xref'], 'A/F/Desc')[1] == 'Synthetic retained description'
            assert dst[0].first_widget is not None


def test_export_uses_unsaved_in_memory_edits(tmp_path: Path):
    source = tmp_path / 'source.pdf'
    output = tmp_path / 'output.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((50, 50), 'Original')
        doc.save(source)
    with fitz.open(source) as doc:
        doc[0].insert_text((50, 80), 'Unsaved addition')
        _write_segment_pdf(doc, [1], output, 'Edited')
    with fitz.open(output) as doc:
        assert 'Unsaved addition' in doc[0].get_text()


def test_uri_misreported_as_file_action_is_not_rewritten(tmp_path: Path):
    source = tmp_path / 'source.pdf'
    output = tmp_path / 'split' / 'output.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(10, 10, 100, 30), 'uri': 'www.example.org'})
        doc.save(source)
    with fitz.open(source) as src:
        _write_segment_pdf(src, [1], output, 'URI preservation')
        with fitz.open(output) as dst:
            link = dst[0].get_links()[0]
            assert dst.xref_get_key(link['xref'], 'A/URI')[1] == 'www.example.org'
            assert dst.xref_get_key(link['xref'], 'A/F')[0] == 'null'
            assert not compare_pages(src[0], dst[0], page_mapping={0: 0},
                                     source_path=source, output_path=output)['mismatches']


def test_platform_specific_file_paths_and_spaces(tmp_path: Path):
    from pdfresearch.pdf_links import file_spec_value

    source = tmp_path / 'source.pdf'
    output = tmp_path / 'split' / 'output.pdf'
    targets = ['C:\\Docs\\Notes.pdf', ':Users:fixture:Notes.pdf', 'notes with spaces.txt']
    with fitz.open() as doc:
        page = doc.new_page()
        for i, target in enumerate(targets):
            page.insert_link({'kind': fitz.LINK_LAUNCH, 'from': fitz.Rect(10, 10+i*30, 100, 30+i*30), 'file': target})
        page = doc.reload_page(page)
        for link, target in zip(page.get_links(), targets):
            doc.xref_set_key(link['xref'], 'A/F', fitz.get_pdf_str(target))
        doc.save(source)
    with fitz.open(source) as src:
        _write_segment_pdf(src, [1], output, 'File path preservation')
        with fitz.open(output) as dst:
            paths = [file_spec_value(dst, link['xref']) for link in dst[0].get_links()]
            assert paths == targets[:2] + ['../notes with spaces.txt']
            assert not compare_pages(src[0], dst[0], page_mapping={0: 0},
                                     source_path=source, output_path=output)['mismatches']


def test_unresolved_named_link_is_retained(tmp_path: Path):
    source = tmp_path / 'source.pdf'
    output = tmp_path / 'output.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 50), 'Unresolved synthetic reference')
        page.insert_link({'kind': fitz.LINK_GOTO, 'from': fitz.Rect(40, 40, 250, 60),
                          'page': -1, 'to': 'missing_synthetic_destination'})
        doc.save(source)
    with fitz.open(source) as src:
        assert len(src[0].get_links()) == 1
        _write_segment_pdf(src, [1], output, 'Unresolved link preserved')
        with fitz.open(output) as dst:
            assert len(dst[0].get_links()) == 1
            assert not compare_pages(src[0], dst[0], page_mapping={0: 0},
                                     source_path=source, output_path=output, render=True)['mismatches']


def test_indirect_uri_and_file_strings(tmp_path: Path):
    source = tmp_path / 'source.pdf'
    output = tmp_path / 'split' / 'output.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(10, 10, 100, 30), 'uri': 'https://example.org'})
        page.insert_link({'kind': fitz.LINK_LAUNCH, 'from': fitz.Rect(10, 40, 100, 60), 'file': 'notes.txt'})
        page = doc.reload_page(page)
        for link, key, value in zip(page.get_links(), ['URI', 'F'], ['https://example.org', 'notes.txt']):
            xref = doc.get_new_xref()
            doc.update_object(xref, fitz.get_pdf_str(value))
            doc.xref_set_key(link['xref'], 'A/' + key, f'{xref} 0 R')
        doc.save(source)
    with fitz.open(source) as src:
        _write_segment_pdf(src, [1], output, 'Indirect strings')
        with fitz.open(output) as dst:
            assert not compare_pages(src[0], dst[0], page_mapping={0: 0},
                                     source_path=source, output_path=output)['mismatches']
