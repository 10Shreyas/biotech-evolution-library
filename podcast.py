#!/usr/bin/env python3
"""Create a weekly spoken research roundup from saved AI summaries."""
import asyncio
import json
import os
import argparse
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
PODCAST = ROOT / 'podcast'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='Generate a new episode even if one exists this week')
    args = parser.parse_args()
    episode_index = PODCAST / 'episodes.json'
    if not args.force and episode_index.exists():
        try:
            previous = json.loads(episode_index.read_text(encoding='utf-8'))
            this_week = date.today().isocalendar()[:2]
            if any(tuple(date.fromisoformat(e['date']).isocalendar()[:2]) == this_week for e in previous):
                print('A podcast episode already exists for this week; use --force to generate another.')
                return 0
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        print('GEMINI_API_KEY is not set; podcast was not generated.')
        return 0
    summaries_path = DATA / 'summaries.json'
    summaries = json.loads(summaries_path.read_text(encoding='utf-8')) if summaries_path.exists() else {}
    cutoff = date.today().isoformat()
    papers = []
    seen = set()
    for path in sorted(DATA.glob('*.json')):
        if path.name in ('summaries.json', 'curated.json'):
            continue
        try:
            works = json.loads(path.read_text(encoding='utf-8')).get('works', [])
        except (OSError, json.JSONDecodeError):
            continue
        for w in works:
            ident = w.get('doi') or w.get('openalex_id')
            if ident in summaries and ident not in seen and (w.get('date') or '')[:10] <= cutoff:
                seen.add(ident)
                papers.append({'title': w.get('title'), 'journal': w.get('journal'), 'date': w.get('date'), **summaries[ident]})
    papers.sort(key=lambda x: x.get('date') or '', reverse=True)
    papers = papers[:8]
    if not papers:
        print('No summarized papers are available for the podcast.')
        return 0
    prompt = ('Write a concise spoken script (about 2 to 3 minutes) for a weekly biotechnology research roundup. '
              'Use only these titles, journals, dates, summaries and why lines. Do not add claims. '
              'Begin with a brief welcome and end with a sign-off.\n' + json.dumps(papers, ensure_ascii=False))
    model = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model, safe="-")}:generateContent?key={urllib.parse.quote(key)}'
    req = urllib.request.Request(url, json.dumps({'contents': [{'parts': [{'text': prompt}]}]}).encode(),
                                 {'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            script = json.load(response)['candidates'][0]['content']['parts'][0]['text'].strip()
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        print(f'Podcast script generation failed: {type(exc).__name__}', file=sys.stderr)
        return 1
    try:
        import edge_tts
    except ImportError:
        print('edge-tts is not installed; podcast script was not converted to audio.', file=sys.stderr)
        return 1
    PODCAST.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    audio_path = PODCAST / f'{stamp}.mp3'
    asyncio.run(edge_tts.Communicate(script, 'en-IN-NeerjaNeural').save(str(audio_path)))
    episodes_path = episode_index
    try:
        episodes = json.loads(episodes_path.read_text(encoding='utf-8')) if episodes_path.exists() else []
    except json.JSONDecodeError:
        episodes = []
    episodes = [e for e in episodes if e.get('date') != stamp]
    episodes.insert(0, {'date': stamp, 'audio': audio_path.name, 'script': script, 'paper_count': len(papers)})
    episodes_path.write_text(json.dumps(episodes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Saved podcast/{audio_path.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
