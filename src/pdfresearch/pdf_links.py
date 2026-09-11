"""Read file actions without the link API's URI/path coercions."""
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import unquote


def file_spec_value(doc, link_xref, api_fallback=''):
    kind, value = doc.xref_get_key(link_xref, 'A/F')
    if kind == 'string':
        return value
    if kind in {'dict', 'xref'}:
        for key in ['A/F/UF', 'A/F/F']:
            kind, value = doc.xref_get_key(link_xref, key)
            if kind == 'string':
                return value
    # An indirect scalar string has no dictionary keys. The link API resolves
    # it but percent-encodes file paths; undo that encoding for the fallback.
    return unquote(api_fallback)


def is_relative_file(value):
    decoded = unquote(value)
    return bool(value) and not (
        Path(decoded).is_absolute()
        or PureWindowsPath(decoded).is_absolute()
        or decoded.startswith(':')  # legacy Macintosh path syntax
        or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', decoded)
    )


def resolved_file(value, containing_pdf):
    if is_relative_file(value):
        return str((Path(containing_pdf).resolve().parent / value).resolve())
    return value
