#!/usr/bin/env python3
"""Incrementally summarize paper abstracts with the free Gemini API."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUTPUT = DATA / 'summaries.json'
MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')


def paper_id(work):
    return work.get('doi') or work.get('openalex_id')


def request_batch(batch, key):
    papers = [{'id': paper_id(w), 'title': w.get('title', ''), 'abstract': w.get('abstract', '')} for w in batch]
    prompt = ('For every paper below, use only its abstract. Return a JSON array with one object per id, '
              'each exactly {"id":"...","summary":"two plain-language lines",'
              '"why":"one simple line on why it matters"}. Keep the summary to two sentences/lines. '
              'Do not add facts or infer claims absent from the abstract. Papers:\n' + json.dumps(papers, ensure_ascii=False))
    body = json.dumps({'contents': [{'parts': [{'text': prompt}]}],
                       'generationConfig': {'responseMimeType': 'application/json'}}).encode()
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(MODEL, safe="-")}:generateContent?key={urllib.parse.quote(key)}'
    for attempt in range(6):
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                payload = json.load(response)
            content = payload['candidates'][0]['content']['parts'][0]['text']
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                parsed = parsed.get('papers', parsed.get('results', []))
            return {str(x['id']): {'summary': str(x['summary']).strip(), 'why': str(x['why']).strip()}
                    for x in parsed if x.get('id') and x.get('summary') and x.get('why')}
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 5:
                raise RuntimeError(f'Gemini request failed with HTTP {exc.code}') from None
            time.sleep(min(60, 2 ** attempt * 2))
        except (KeyError, ValueError, IndexError) as exc:
            if attempt == 5:
                raise RuntimeError(f'Gemini returned invalid JSON: {type(exc).__name__}') from None
            time.sleep(min(30, 2 ** attempt))
    return {}


def main():
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        print('GEMINI_API_KEY is not set; summaries were not requested.')
        return 0
    try:
        summaries = json.loads(OUTPUT.read_text(encoding='utf-8')) if OUTPUT.exists() else {}
    except (OSError, json.JSONDecodeError):
        summaries = {}
    papers = []
    for path in sorted(DATA.glob('*.json')):
        if path.name == 'summaries.json' or path.name == 'curated.json':
            continue
        try:
            collection = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        for work in collection.get('works', []):
            ident = paper_id(work)
            if ident and work.get('abstract', '').strip() and ident not in summaries:
                papers.append(work)
    total = len(papers)
    for start in range(0, total, 20):
        result = request_batch(papers[start:start + 20], key)
        summaries.update(result)
        OUTPUT.write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Summarized {min(start + 20, total)} of {total} pending abstracts')
    if not total:
        print(f'No new abstracts to summarize; {len(summaries)} saved summaries retained.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
