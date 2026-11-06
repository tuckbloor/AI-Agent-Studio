"""Safe, deterministic, read-only tools; exposed through Studio's MCP endpoint.

No filesystem, shell, arbitrary external requests, or dynamic Python execution.
"""
from collections import Counter
import csv
import io
import json
import re
import textwrap
from datetime import datetime, timezone

EMAIL = re.compile(r'(?<![\w.])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.])', re.I)
URL = re.compile(r'https?://[^\s<>"\']+', re.I)
PHONE = re.compile(r'(?<!\w)(?:\+?\d[\d .()\-]{8,}\d)(?!\w)')
DATE = re.compile(r'\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b')
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
ERROR = re.compile(r'\b(?:HTTP\s*[45]\d{2}|(?:error|exception|failed|failure|timeout|refused|deadlock|traceback)\b[^\n]{0,110})', re.I)

# ID, name, description, category, input field
CATALOG = [
 ('word_count', 'Count words & characters', 'Count words, characters and lines in text.', 'Text'),
 ('extract_emails', 'Find email addresses', 'Extract distinct email addresses from text.', 'Extract'),
 ('extract_urls', 'Find website links', 'Extract http and https links from text.', 'Extract'),
 ('extract_dates', 'Find dates', 'Find dates written as 2026-11-05 or 05/11/2026.', 'Extract'),
 ('extract_phones', 'Find telephone numbers', 'Find phone-number-like sequences; check before using.', 'Extract'),
 ('extract_actions', 'Find action items', 'Pick out lines containing TODO, ACTION or checkbox items.', 'Work'),
 ('extract_errors', 'Find error clues', 'Extract errors, timeouts and HTTP failure codes from pasted logs.', 'Work'),
 ('extract_numbers', 'Find numbers', 'Extract numbers, including decimal values.', 'Extract'),
 ('extract_headings', 'List Markdown headings', 'Find # heading lines from Markdown notes.', 'Documents'),
 ('extract_hashtags', 'Find hashtags', 'Extract tags such as #project and #priority.', 'Extract'),
 ('clean_whitespace', 'Clean up text', 'Normalise excess spaces and blank lines.', 'Text'),
 ('sort_lines', 'Sort lines', 'Sort non-empty text lines alphabetically.', 'Text'),
 ('unique_lines', 'Remove duplicate lines', 'Remove repeated lines while keeping their first occurrence.', 'Text'),
 ('frequent_words', 'Top repeated words', 'Show the most frequent words; simple counts, not AI analysis.', 'Text'),
 ('redact_emails', 'Hide email addresses', 'Mask email addresses in supplied text.', 'Privacy'),
 ('redact_phones', 'Hide telephone numbers', 'Mask telephone-number-like strings.', 'Privacy'),
 ('json_validate', 'Check JSON format', 'Validate JSON and show where errors appear.', 'Documents'),
 ('json_pretty', 'Format JSON', 'Indent valid JSON for easier reading.', 'Documents'),
 ('csv_preview', 'Preview CSV data', 'Show headers and the first five CSV records.', 'Documents'),
 ('make_checklist', 'Make a checklist', 'Turn non-empty lines into a Markdown to-do checklist.', 'Work'),
]

TOOL_BY_ID = {f'builtin:{id}': {'id':f'builtin:{id}', 'name':name, 'description':description,
 'category':category, 'kind':'builtin', 'source':'builtin',
 'inputSchema':{'type':'object','properties':{'text':{'type':'string','description':'Text to process'}},'required':['text']}}
 for id,name,description,category in CATALOG}
assert len(TOOL_BY_ID) == 20


def _lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def _found(values):
    items = list(dict.fromkeys(values))[:80]
    return '\n'.join(items) if items else 'No matches found.'


def execute(tool_id: str, text: str) -> str:
    if tool_id not in TOOL_BY_ID:
        raise ValueError('This built-in tool does not exist.')
    if not isinstance(text, str) or len(text) > 30000:
        raise ValueError('Supply text of up to 30,000 characters.')
    k = tool_id.removeprefix('builtin:')
    if k == 'word_count': return f'Words: {len(WORD.findall(text))}\nCharacters: {len(text)}\nLines: {len(text.splitlines())}'
    if k == 'extract_emails': return _found(EMAIL.findall(text))
    if k == 'extract_urls': return _found(url.rstrip('.,);]') for url in URL.findall(text))
    if k == 'extract_dates': return _found(DATE.findall(text))
    if k == 'extract_phones': return _found(x.strip() for x in PHONE.findall(text))
    if k == 'extract_actions': return _found(line for line in _lines(text) if re.search(r'\b(todo|action|required|follow.up)\b|^[-*]\s*\[[ xX]\]',line,re.I))
    if k == 'extract_errors': return _found(ERROR.findall(text))
    if k == 'extract_numbers': return _found(re.findall(r'(?<![\w])[-+]?\d+(?:[.,]\d+)*(?!\w)',text))
    if k == 'extract_headings': return _found(_lines(text) and [line for line in _lines(text) if re.match(r'^#{1,6}\s+',line)] or [])
    if k == 'extract_hashtags': return _found(re.findall(r'(?<!\w)#[\w-]+',text))
    if k == 'clean_whitespace': return '\n'.join(' '.join(line.split()) for line in text.splitlines() if line.strip()) or '(No text)'
    if k == 'sort_lines': return '\n'.join(sorted(_lines(text),key=str.casefold)) or '(No lines)'
    if k == 'unique_lines': return '\n'.join(dict.fromkeys(_lines(text))) or '(No lines)'
    if k == 'frequent_words':
        counts=Counter(w.lower() for w in WORD.findall(text) if len(w)>2)
        return '\n'.join(f'{w}: {n}' for w,n in counts.most_common(12)) or '(No words)'
    if k == 'redact_emails': return EMAIL.sub('[EMAIL REDACTED]',text)
    if k == 'redact_phones': return PHONE.sub('[PHONE REDACTED]',text)
    if k in ('json_validate','json_pretty'):
        try: data=json.loads(text)
        except json.JSONDecodeError as exc: return f'Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})'
        if k=='json_validate': return f'Valid JSON. Top-level type: {type(data).__name__}.'
        return json.dumps(data,ensure_ascii=False,indent=2)[:30000]
    if k == 'csv_preview':
        try:
            reader=csv.reader(io.StringIO(text)); rows=[]
            for i,row in enumerate(reader):
                if i>=5:break
                rows.append(row[:20])
        except csv.Error as exc:return f'CSV could not be read: {exc}'
        return '\n'.join(' | '.join(row) for row in rows) if rows else '(No CSV rows)'
    if k == 'make_checklist': return '\n'.join(f'- [ ] {line}' for line in _lines(text)[:60]) or '(No items)'
    raise ValueError('Unknown built-in tool.')


def public_tools():
    return [dict(v) for v in TOOL_BY_ID.values()]
