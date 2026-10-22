"""Story -> animation jobs: runs the Claude CLI against the MCP server, then renders."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config
from .production.render import render_production
from .production.studio import Studio

STYLE_DESC = {
    'anime': 'Japanese anime: expressive faces, big eyes, cel shading, dramatic reactions.',
    'cartoon': 'Desi web-cartoon comedy in the spirit of Indian storytelling channels like "Not Your '
               'Type": big heads (~3 heads tall), big googly eyes with heavy eyelids, thick ink outlines, '
               'curly/messy hair, hoodies and striped tees, relatable everyday humour, exaggerated reactions. '
               'Prefer hair_style curly/messy/undercut/ponytail and Indian skin tones (fair, wheat, tan, brown).',
}
LANG_DESC = {
    'en': 'English.',
    'en-IN': 'Indian English (Indian names and settings are welcome).',
    'hi': 'Hindi written in Devanagari script.',
    'ja': 'Japanese.',
}


@dataclass
class JobOptions:
    title: str = 'My Anime'
    style: str = 'anime'
    minutes: float = 1.0
    language: str = 'en'
    resolution: str = '720p'
    tts_engine: str = 'edge'
    model: str = ''


@dataclass
class Job:
    id: str
    story: str
    options: JobOptions
    status: str = 'queued'  # queued directing rendering done error cancelled
    production_id: str = ''
    log: list[dict] = field(default_factory=list)
    render: dict = field(default_factory=dict)
    output: str = ''
    error: str = ''
    created: float = field(default_factory=time.time)
    cost_usd: float | None = None

    def public(self) -> dict:
        d = asdict(self)
        d['log'] = self.log[-300:]
        return d


class JobRunner:
    def __init__(self, studio: Studio | None = None) -> None:
        self.studio = studio or Studio()
        self.jobs: dict[str, Job] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._pool = ThreadPoolExecutor(1)  # one production at a time (rendering is heavy)
        self.dir = config.home() / 'jobs'
        self.dir.mkdir(parents=True, exist_ok=True)
        self._load()

    # -- persistence ----------------------------------------------------------
    def _load(self) -> None:
        for f in sorted(self.dir.glob('*.json')):
            try:
                d = json.loads(f.read_text(encoding='utf-8'))
                d['options'] = JobOptions(**d['options'])
                job = Job(**d)
                if job.status in ('queued', 'directing', 'rendering'):
                    job.status, job.error = 'error', 'interrupted (server restarted)'
                self.jobs[job.id] = job
            except Exception:
                continue

    def _save(self, job: Job) -> None:
        (self.dir / ('%s.json' % job.id)).write_text(json.dumps(asdict(job)), encoding='utf-8')

    def _log(self, job: Job, kind: str, text: str) -> None:
        job.log.append({'t': round(time.time() - job.created, 1), 'kind': kind, 'text': text[:2000]})
        if len(job.log) % 5 == 0:
            self._save(job)

    # -- API ---------------------------------------------------------------
    def submit(self, story: str, options: JobOptions) -> Job:
        if not story.strip():
            raise ValueError('story is empty')
        options.minutes = max(0.2, min(10.0, float(options.minutes)))
        job = Job(uuid.uuid4().hex[:10], story.strip(), options)
        self.jobs[job.id] = job
        self._save(job)
        self._pool.submit(self._run, job)
        return job

    def rerender(self, job_id: str) -> Job:
        job = self.jobs[job_id]
        if not job.production_id:
            raise ValueError('job has no production')
        job.status, job.error = 'queued', ''
        self._pool.submit(self._render_safe, job)
        return job

    def _render_safe(self, job: Job) -> None:
        try:
            self._render(job)
        except Exception as e:
            job.status, job.error = 'error', str(e)
            self._log(job, 'error', str(e))
            self._save(job)

    def cancel(self, job_id: str) -> None:
        job = self.jobs[job_id]
        proc = self._procs.get(job_id)
        if proc and proc.poll() is None:
            proc.kill()
        job.status = 'cancelled'
        self._save(job)

    # -- work ----------------------------------------------------------------
    def _run(self, job: Job) -> None:
        if job.status == 'cancelled':
            return
        try:
            o = job.options
            prod = self.studio.create(o.title, story=job.story, style=o.style,
                                      resolution=o.resolution, language=o.language,
                                      target_minutes=o.minutes, tts_engine=o.tts_engine)
            job.production_id = prod.id
            job.status = 'directing'
            self._save(job)
            self._direct(job)
            if job.status == 'cancelled':
                return
            if not self.studio.load(prod.id).shots:
                raise RuntimeError('Claude finished without creating any shots')
            self._render(job)
        except Exception as e:
            if job.status != 'cancelled':
                job.status, job.error = 'error', str(e)
                self._log(job, 'error', str(e))
        finally:
            self._save(job)

    def _direct(self, job: Job) -> None:
        o = job.options
        template = (config.PACKAGE_DIR / 'prompts' / 'director.md').read_text(encoding='utf-8')
        prompt = template.format(
            production_id=job.production_id, target_minutes=o.minutes,
            target_seconds=int(o.minutes * 60), style_desc=STYLE_DESC.get(o.style, o.style),
            language_desc=LANG_DESC.get(o.language, o.language), story=job.story)
        cfg = self.dir / ('%s.mcp.json' % job.id)
        cfg.write_text(json.dumps({'mcpServers': {'opentoonz': {
            'command': sys.executable,
            'args': [str(config.AI_DIR / 'run_mcp.py')],
            'env': {'OTAI_HOME': str(config.home())},
        }}}), encoding='utf-8')
        claude = shutil.which('claude') or shutil.which('claude.exe')
        if not claude:
            raise RuntimeError('Claude CLI not found on PATH (install Claude Code)')
        cmd = [claude, '-p', '--output-format', 'stream-json', '--verbose',
               '--mcp-config', str(cfg), '--strict-mcp-config',
               '--allowedTools', 'mcp__opentoonz', '--permission-mode', 'dontAsk']
        if o.model:
            cmd += ['--model', o.model]
        self._log(job, 'info', 'Starting Claude CLI director')
        env = dict(os.environ)
        env.setdefault('MCP_TOOL_TIMEOUT', '600000')
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                errors='replace', env=env, cwd=str(config.home()),
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self._procs[job.id] = proc
        proc.stdin.write(prompt)
        proc.stdin.close()
        err_lines: list[str] = []
        threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True).start()
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                self._log(job, 'raw', line)
                continue
            self._event(job, ev)
        code = proc.wait()
        if job.status == 'cancelled':
            return
        if code != 0:
            raise RuntimeError('Claude CLI exited with %d: %s' % (code, ''.join(err_lines)[-1500:]))

    def _event(self, job: Job, ev: dict) -> None:
        t = ev.get('type')
        if t == 'assistant':
            for block in ev.get('message', {}).get('content', []):
                if block.get('type') == 'text' and block.get('text', '').strip():
                    self._log(job, 'claude', block['text'].strip())
                elif block.get('type') == 'tool_use':
                    name = block.get('name', '').replace('mcp__opentoonz__', '')
                    self._log(job, 'tool', '%s %s' % (name, _brief(block.get('input', {}))))
        elif t == 'user':
            for block in ev.get('message', {}).get('content', []) or []:
                if isinstance(block, dict) and block.get('type') == 'tool_result' and block.get('is_error'):
                    self._log(job, 'tool_error', _text(block.get('content')))
        elif t == 'result':
            job.cost_usd = ev.get('total_cost_usd')
            self._log(job, 'result', str(ev.get('result', ''))[:1500])

    def _render(self, job: Job) -> None:
        job.status = 'rendering'
        self._save(job)
        self._log(job, 'info', 'Rendering video')

        def progress(state):
            job.render = state

        out = render_production(self.studio, job.production_id, progress=progress)
        self.studio.contact_sheet(job.production_id)
        thumb = self.studio.dir(job.production_id) / 'render' / 'thumbnail.png'
        if not thumb.exists():
            self.studio.thumbnail(job.production_id)
        job.output = str(out)
        job.status = 'done'
        self._log(job, 'info', 'Done: %s' % out)
        self._save(job)


def _brief(inp: dict) -> str:
    if 'character' in inp and isinstance(inp['character'], dict):
        return inp['character'].get('name', '')
    if 'background' in inp and isinstance(inp['background'], dict):
        b = inp['background']
        return '%s (%s, %s)' % (b.get('name'), b.get('location'), b.get('time_of_day', 'day'))
    if 'shots' in inp:
        return '%d shots' % len(inp.get('shots') or [])
    if 'shot_id' in inp:
        return inp['shot_id']
    return ''


def _text(content) -> str:
    if isinstance(content, str):
        return content[:500]
    if isinstance(content, list):
        return ' '.join(c.get('text', '') for c in content if isinstance(c, dict))[:500]
    return str(content)[:500]
