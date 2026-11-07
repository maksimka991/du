import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_DIR = BASE_DIR / "data"
DATA_DIR = Path(os.environ.get("DU_DATA_DIR", BASE_DIR / ".du-data")).resolve()


def prepare_storage() -> None:
    if DATA_DIR.exists() and any(DATA_DIR.iterdir()):
        (DATA_DIR / "audio").mkdir(exist_ok=True)
        return
    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".du-migrate-", dir=DATA_DIR.parent) as temporary:
        staged = Path(temporary) / "library"
        staged.mkdir()
        legacy_db = DEMO_DIR / "du_learning.db"
        if legacy_db.is_file():
            with closing(sqlite3.connect(legacy_db.as_uri() + "?mode=ro", uri=True)) as source:
                with closing(sqlite3.connect(staged / legacy_db.name)) as destination:
                    source.backup(destination)
        if (DEMO_DIR / "audio").is_dir():
            shutil.copytree(DEMO_DIR / "audio", staged / "audio")
        else:
            (staged / "audio").mkdir()
        try:
            if DATA_DIR.is_dir():
                DATA_DIR.rmdir()
            staged.rename(DATA_DIR)
        except OSError:
            if not (DATA_DIR / "audio").is_dir():
                raise
