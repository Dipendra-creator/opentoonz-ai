"""Story-to-animation web screen.

Run:  python -m otai.web   (serves http://127.0.0.1:8765)
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .. import config
from ..pipeline import JobOptions, JobRunner

STATIC = Path(__file__).resolve().parent / 'static'

app = FastAPI(title='OpenToonz AI Studio')
runner = JobRunner()


class JobRequest(BaseModel):
    story: str = Field(..., min_length=20, max_length=60000)
    title: str = Field('My Anime', max_length=80)
    style: str = Field('anime', pattern='^(anime|cartoon)$')
    minutes: float = Field(1.0, ge=0.2, le=10.0)
    language: str = Field('en', pattern='^(en|en-IN|hi|ja)$')
    resolution: str = Field('720p', pattern='^(480p|720p|1080p)$')
    tts_engine: str = Field('edge', pattern='^(edge|sapi|none)$')
    model: str = Field('', max_length=60)


@app.get('/', response_class=HTMLResponse)
def index() -> str:
    return (STATIC / 'index.html').read_text(encoding='utf-8')


@app.get('/api/env')
def env() -> dict:
    return {'claude': bool(shutil.which('claude') or shutil.which('claude.exe')),
            'tcomposer': str(config.tcomposer_exe() or ''),
            'productions_dir': str(runner.studio.root)}


@app.post('/api/jobs')
def create_job(req: JobRequest) -> dict:
    opts = JobOptions(title=req.title, style=req.style, minutes=req.minutes,
                      language=req.language, resolution=req.resolution,
                      tts_engine=req.tts_engine, model=req.model)
    return runner.submit(req.story, opts).public()


@app.get('/api/jobs')
def list_jobs() -> list[dict]:
    jobs = sorted(runner.jobs.values(), key=lambda j: j.created, reverse=True)
    out = []
    for j in jobs[:50]:
        d = j.public()
        d['log'] = d['log'][-1:]
        d['story'] = d['story'][:160]
        out.append(d)
    return out


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str) -> dict:
    job = runner.jobs.get(job_id)
    if not job:
        raise HTTPException(404, 'no such job')
    d = job.public()
    if job.production_id:
        try:
            d['production'] = runner.studio.summary(job.production_id)
        except Exception:
            pass
    return d


@app.post('/api/jobs/{job_id}/cancel')
def cancel_job(job_id: str) -> dict:
    if job_id not in runner.jobs:
        raise HTTPException(404, 'no such job')
    runner.cancel(job_id)
    return {'ok': True}


@app.post('/api/jobs/{job_id}/rerender')
def rerender_job(job_id: str) -> dict:
    if job_id not in runner.jobs:
        raise HTTPException(404, 'no such job')
    return runner.rerender(job_id).public()


@app.get('/media/{pid}/{name}')
def media(pid: str, name: str):
    allowed = {'final.mp4', 'contact_sheet.png'}
    if name not in allowed and not (name.startswith('cast_') and name.endswith('.png')):
        raise HTTPException(404)
    path = runner.studio.dir(pid) / 'render' / name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


def main() -> None:
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765, log_level='warning')
