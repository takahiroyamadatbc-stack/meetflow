import json


class BadRequest(Exception):
    """Raised by handlers for malformed request bodies; caught centrally by
    `router.dispatch` rather than repeated in every handler.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def parse_body(event: dict) -> dict:
    try:
        return json.loads(event.get("body") or "{}")
    except ValueError:
        raise BadRequest("リクエストボディの形式が不正です")
