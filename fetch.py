#!/usr/bin/env python3
"""Fetch recent Enzymes journal works from OpenAlex and configured public RSS feeds."""
import json
import os
import re
import time
import argparse
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOURNALS = json.loads((ROOT / 'journals.json').read_text(encoding='utf-8'))
SUBJECT = next(s for s in JOURNALS['subjects'] if s['slug'] == 'enzymes-and-enzyme-technology')
OUT = ROOT / 'data' / f"{SUBJECT['slug']}.json"
UA = JOURNALS.get('meta', {}).get('user_agent', 'Biotechnology-Evolution-Library/0.1')
BASE = 'https://api.openalex.org/works'
# Public RSS/Atom endpoints; the journal names and exact URLs are saved into the output.
FEEDS = {
    'Nature Catalysis': 'https://www.nature.com/natcatal.rss',
    'ACS Catalysis': 'https://pubs.acs.org/action/showFeed?type=etoc&feed=rss&jc=accacs',
    'Enzyme and Microbial Technology': 'https://rss.sciencedirect.com/publication/science/01410229',
    'Applied Microbiology and Biotechnology': 'https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id=253',
    'Catalysis Science & Technology': 'https://pubs.rsc.org/en/journals/journalissues/cy#!recentarticles&adv',
    'Biocatalysis and Agricultural Biotechnology': 'https://rss.sciencedirect.com/publication/science/2215017X',
    'Process Biochemistry': 'https://rss.sciencedirect.com/publication/science/13595113',
    'Applied Biochemistry and Biotechnology': 'https://link.springer.com/search.rss?facet-content-type=Article&facet-journal-id=12010',
    'Protein Engineering Design and Selection': 'https://academic.oup.com/rss/site_5067/advanceAccess_2429.xml',
    'ChemCatChem': 'https://onlinelibrary.wiley.com/feed/18673899/most-recent',
    'Molecular Catalysis': 'https://rss.sciencedirect.com/publication/science/24688231',
    'Advanced Synthesis & Catalysis': 'https://onlinelibrary.wiley.com/feed/16154169/most-recent',
    'ChemBioChem': 'https://onlinelibrary.wiley.com/feed/14397633/most-recent',
    'Biotechnology Advances': 'https://rss.sciencedirect.com/publication/science/07349750',
    'Biocatalysis and Biotransformation': 'https://www.tandfonline.com/feed/rss/ibab20',
}

def request(url, timeout=18):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json, application/atom+xml, application/rss+xml, application/xml'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()

def abstract_from_index(index):
    if not index:
        return ''
    words = []
    for word, positions in index.items():
        for pos in positions:
            words.append((pos, word))
    return ' '.join(word for _, word in sorted(words))

def europe_pmc_abstract(doi):
    if not doi:
        return ''
    url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urllib.parse.urlencode({'query': 'DOI:"' + doi + '"', 'format': 'json', 'resultType': 'core', 'pageSize': 1})
    try:
        results = json.loads(request(url))['resultList']['result']
        return results[0].get('abstractText', '') if results else ''
    except Exception:
        return ''

def unpaywall(doi):
    email = os.environ.get('UNPAYWALL_EMAIL')
    if not (doi and email):
        return None
    url = 'https://api.unpaywall.org/v2/' + urllib.parse.quote(doi, safe='') + '?' + urllib.parse.urlencode({'email': email})
    try:
        data = json.loads(request(url))
        loc = data.get('best_oa_location') or {}
        return {'url': loc.get('url_for_pdf') or loc.get('url'), 'license': loc.get('license')}
    except Exception:
        return None

def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).date().isoformat()
    except ValueError:
        return None

def parse_feed(xml, journal):
    root = ET.fromstring(xml)
    out = []
    for item in root.iter():
        tag = item.tag.rsplit('}', 1)[-1].lower()
        if tag not in ('item', 'entry'):
            continue
        vals = {}
        for child in item.iter():
            name = child.tag.rsplit('}', 1)[-1].lower()
            if name in ('title', 'description', 'summary', 'pubdate', 'published', 'updated', 'link') and name not in vals:
                vals[name] = ''.join(child.itertext()).strip()
                if name == 'link' and not vals[name]:
                    vals[name] = child.attrib.get('href', '')
        url = vals.get('link', '')
        if not url:
            link = next((x for x in item if x.tag.rsplit('}',1)[-1].lower() == 'link'), None)
            if link is not None: url = link.attrib.get('href', '')
        rawdate = vals.get('pubdate') or vals.get('published') or vals.get('updated', '')
        out.append({'journal': journal, 'title': re.sub(r'<[^>]+>', '', vals.get('title', '')), 'summary': re.sub(r'<[^>]+>', '', vals.get('description') or vals.get('summary', ''))[:700], 'date': rawdate[:25], 'url': url})
    return out

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true', help='Fetch every broad research area')
    args = parser.parse_args()
    today = date.today()
    since = today - timedelta(days=30)
    collections = JOURNALS.get('areas', []) if args.all else [dict(SUBJECT, journals=SUBJECT['journals'])]
    for area in collections:
      works, errors, feed_items, feed_urls = [], [], [], []
      seen = set()
      for journal in area['journals']:
        name, source = journal['display_name'], journal['openalex_source_id']
        params = {'filter': f'from_publication_date:{since.isoformat()},to_publication_date:{today.isoformat()},primary_location.source.id:{source}', 'sort': 'publication_date:desc', 'per-page': '50'}
        url = BASE + '?' + urllib.parse.urlencode(params)
        try:
            data = json.loads(request(url))
            for w in data.get('results', [])[:50]:
                key = w.get('doi') or w.get('id')
                if key in seen: continue
                seen.add(key)
                doi = w.get('doi')
                loc = w.get('best_oa_location') or {}
                oa_url = loc.get('landing_page_url') or loc.get('pdf_url')
                license_name = loc.get('license')
                if not oa_url and doi:
                    fallback = unpaywall(doi)
                    if fallback:
                        oa_url, license_name = fallback.get('url'), fallback.get('license')
                abstract = abstract_from_index(w.get('abstract_inverted_index'))
                if not abstract:
                    abstract = europe_pmc_abstract(doi)
                authors = [a.get('author', {}).get('display_name') for a in w.get('authorships', []) if a.get('author', {}).get('display_name')]
                journal_url = (w.get('primary_location') or {}).get('landing_page_url') or journal.get('homepage_url')
                works.append({'title': w.get('title') or '', 'authors': authors, 'journal': name, 'date': w.get('publication_date'), 'doi': doi, 'abstract': abstract, 'oa_url': oa_url, 'license': license_name, 'journal_url': journal_url, 'openalex_id': w.get('id')})
            print(f"OpenAlex {name}: {len(data.get('results', []))} works")
        except Exception as e:
            errors.append({'source': f'OpenAlex: {name}', 'url': url, 'error': f'{type(e).__name__}: {e}'})
            print(f"FAILED OpenAlex {name}: {e}")
        time.sleep(0.12)
      if not args.all:
        for name, url in FEEDS.items():
            feed_urls.append({'journal': name, 'url': url})
            try:
                feed_items.extend(parse_feed(request(url), name))
            except Exception as e:
                errors.append({'source': f'RSS: {name}', 'url': url, 'error': f'{type(e).__name__}: {e}'})
            time.sleep(0.08)
      works.sort(key=lambda x: x.get('date') or '', reverse=True)
      result = {'subject': area['name'], 'subject_slug': area['slug'], 'fetched_at': datetime.now(timezone.utc).isoformat(), 'period': {'from': since.isoformat(), 'to': today.isoformat()}, 'counts_by_journal': {j['display_name']: sum(w['journal'] == j['display_name'] for w in works) for j in area['journals']}, 'works': works, 'feeds': feed_items, 'feed_urls': feed_urls, 'errors': errors}
      out = ROOT / 'data' / f"{area['slug']}.json"
      out.parent.mkdir(exist_ok=True)
      out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
      print(f"Saved {len(works)} works to {out.relative_to(ROOT)}; failed sources: {len(errors)}")

if __name__ == '__main__':
    main()
