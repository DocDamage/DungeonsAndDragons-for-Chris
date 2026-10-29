from dungeonforge.compendium.db import CompendiumDB, CompendiumEntry
from dungeonforge.compendium.indexer import CompendiumIndexer

_DEFAULT_DB = None

def get_compendium_db() -> CompendiumDB:
    global _DEFAULT_DB
    if _DEFAULT_DB is None:
        _DEFAULT_DB = CompendiumDB()
    return _DEFAULT_DB
