from web_utils import RESPONSE_STATUSES
from web_utils import HEADER_X_POWERED_BY

class HttpError(Exception):
    """
    HttpError that defines http error code.
    """
    def __init__(self, code, msg=''):
        """
        Init an HttpError with response code.
        """
        super(HttpError, self).__init__()
        self.status = '%d %s' % (code, RESPONSE_STATUSES[code])
        self.msg = msg

    def header(self, name, value):
        if not hasattr(self, '_headers'):
            self._headers = [HEADER_X_POWERED_BY]
        self._headers.append((name, value))

    @property
    def headers(self):
        if hasattr(self, '_headers'):
            return self._headers
        return []

    def __str__(self):
        return self.status + ': ' + self.msg if self.msg else self.status

    __repr__ = __str__


class RedirectError(HttpError):
    """
    RedirectError that defines http redirect code.
    """
    def __init__(self, code, location):
        """
        Init an HttpError with response code.
        """
        super(RedirectError, self).__init__(code)
        self.location = location

    def __str__(self):
        return '%s, %s' % (self.status, self.location)

    __repr__ = __str__


def bad_request():
    """
    Send a bad request response.
    """
    return HttpError(400)


def unauthorized():
    """
    Send an unauthorized response.
    """
    return HttpError(401)


def forbidden():
    """
    Send a forbidden response.
    """
    return HttpError(403)


def not_found():
    """
    Send a not found response.
    """
    return HttpError(404)


def not_allowed():
    """
    Send a method not allowed response.
    """
    return HttpError(405)


def conflict():
    """
    Send a conflict response.
    """
    return HttpError(409)


def internal_error():
    """
    Send an internal error response.
    """
    return HttpError(500)


def found(location):
    """
    Do temporary redirect.
    """
    return RedirectError(302, location)


def see_other(location):
    """
    Do temporary redirect.
    """
    return RedirectError(303, location)

import builtins
