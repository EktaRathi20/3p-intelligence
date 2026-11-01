"""Throwaway FastAPI import shim for the sandbox (NOT part of the deliverable).

The sandbox has no Python 3.11 runtime, so the real `fastapi` package
(which needs pydantic-core's cp311 binary) cannot import on the available
Python 3.14. This stub provides only `HTTPException` with the real
constructor semantics so pure-logic tests of modules that import it
(`disaster_intelligence`, `hazard_intelligence`) can run. It shadows the
real package ONLY when this directory is first on PYTHONPATH, and only
for the modules exercised below — route/Socket.IO tests still skip.
"""


class HTTPException(Exception):
    def __init__(self, status_code: int, detail=None, headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
