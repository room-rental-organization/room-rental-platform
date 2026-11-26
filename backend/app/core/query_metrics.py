"""Query counts without SQL text, parameters, URLs, or user identifiers."""
from contextvars import ContextVar
from dataclasses import dataclass
from sqlalchemy import Engine, event


@dataclass
class QueryCount:
    statements: int = 0
    selects: int = 0


request_queries: ContextVar[QueryCount | None] = ContextVar('request_queries', default=None)


@event.listens_for(Engine, 'before_cursor_execute')
def count_query(connection, cursor, statement, parameters, context, executemany):
    counts = request_queries.get()
    if counts is not None:
        counts.statements += 1
        counts.selects += int(statement.lstrip().upper().startswith('SELECT'))
