"""Single-origin application for the rig and firmware workspace."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from control.main import create_app as create_control
from develop.main import SPAStaticFiles, create_app as create_develop

control = create_control()
develop = create_develop()


@asynccontextmanager
async def lifespan(app):
    # Mounted ASGI applications do not receive lifespan events automatically.
    async with control.router.lifespan_context(control):
        async with develop.router.lifespan_context(develop):
            yield


app = FastAPI(title="EMFI", lifespan=lifespan)
app.mount('/api/control', control)
app.mount('/api/develop', develop)
app.mount('/develop', SPAStaticFiles(directory=str(Path(__file__).parent / 'develop' / 'frontend' / 'build'), html=True))
app.mount('/', SPAStaticFiles(directory=str(Path(__file__).parent / 'view' / 'build'), html=True))
