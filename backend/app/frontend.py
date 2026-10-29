"""Serve only the compiled public frontend; never the project/data directories."""

from pathlib import Path

from starlette.staticfiles import StaticFiles


def install_frontend(application, directory):
    directory = Path(directory)
    if not (directory / "index.html").is_file():
        return False
    application.mount("/", StaticFiles(directory=directory, html=True, follow_symlink=False), name="frontend")
    return True
