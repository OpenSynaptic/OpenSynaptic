from .base import BaseDBDriver
from .sqlite_driver import SQLiteDriver
from .mysql_driver import MySQLDriver
from .postgresql_driver import PostgresDriver
PostageSQLDriver = PostgresDriver

def create_driver(dialect, config):
    d = str(dialect or '').strip().lower()
    if d in ('sqlite', 'sqlite3'):
        return SQLiteDriver(config)
    if d in ('mysql',):
        return MySQLDriver(config)
    if d in ('postgres', 'postgresql', 'postagesql', 'psql'):
        return PostgresDriver(config)
    raise ValueError('Unsupported SQL dialect')
__all__ = ['BaseDBDriver', 'SQLiteDriver', 'MySQLDriver', 'PostgresDriver', 'PostageSQLDriver', 'create_driver']
