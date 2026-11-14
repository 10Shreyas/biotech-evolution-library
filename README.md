# Biotechnology Evolution Library

A living library of recent biotechnology research from leading journals, with abstracts, DOIs, and legal open access links where available. Data comes from OpenAlex, Europe PMC, and public journal feeds.

## Run locally

```sh
python3 fetch.py --all
python3 summarize.py  # Optional: set GEMINI_API_KEY for Gemini Flash summaries
python3 -m http.server 8000
```

Open <http://localhost:8000>. The browser needs an HTTP server to load the collection JSON files.

## Features

- Browse papers by research area and journal, search the library, and explore OpenAlex topic maps.
- Expand a paper to see its abstract and, when available, an AI summary generated from that abstract.
- Pick papers to export a single Markdown source for NotebookLM.
- Chat with picked papers or the current area using your own Gemini API key. The key is stored in this browser's localStorage and sent directly to Gemini. Use **Forget key** to remove it.
- Listen to weekly research roundup episodes in the Podcast tab. Run `python3 podcast.py --force` to create an episode manually. Install `edge-tts` first.

Summaries are stored incrementally in `data/summaries.json`; missing `GEMINI_API_KEY` cleanly skips summarization. GitHub Actions refreshes data daily at 00:30 UTC, summarizes abstracts, creates at most one podcast episode per week, and pushes data updates. Add a `GEMINI_API_KEY` repository secret to enable Gemini features in automation.
