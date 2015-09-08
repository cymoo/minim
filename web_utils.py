"""
minim.http_utils
~~~~~~~~~~~~~~~~


"""

import os
import mimetypes

# all known response statues:

RESPONSE_STATUSES = {
    # Informational
    100: 'Continue',
    101: 'Switching Protocols',
    102: 'Processing',

    # Successful
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi Status',
    226: 'IM Used',

    # Redirection
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',

    # Client Error
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    418: "I'm a teapot",
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    426: 'Upgrade Required',

    # Server Error
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    507: 'Insufficient Storage',
    510: 'Not Extended',
}

# _RE_RESPONSE_STATUS = re.compile(r'^\d\d\d( [\w ]+)?$')

RESPONSE_HEADERS = (
    'Accept-Ranges',
    'Age',
    'Allow',
    'Cache-Control',
    'Connection',
    'Content-Encoding',
    'Content-Language',
    'Content-Length',
    'Content-Location',
    'Content-MD5',
    'Content-Disposition',
    'Content-Range',
    'Content-Type',
    'Date',
    'ETag',
    'Expires',
    'Last-Modified',
    'Link',
    'Location',
    'P3P',
    'Pragma',
    'Proxy-Authenticate',
    'Refresh',
    'Retry-After',
    'Server',
    'Set-Cookie',
    'Strict-Transport-Security',
    'Trailer',
    'Transfer-Encoding',
    'Vary',
    'Via',
    'Warning',
    'WWW-Authenticate',
    'X-Frame-Options',
    'X-XSS-Protection',
    'X-Content-Type-Options',
    'X-Forwarded-Proto',
    'X-Powered-By',
    'X-UA-Compatible',
)


HEADER_X_POWERED_BY = ('X-Powered-By', 'minim/0.1')


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


# an incomplete func
def redirect(req, res, url, code=None):
    if not code:
        code = 303 if req.environ.get('SERVER_PROTOCOL') == 'HTTP/1.1' else 302
    res.status = code
    res.set_header('Location', url)
    return res


# an incomplete func
def send_file(res, directory, filename):
    filepath = os.path.join(directory, filename)
    if not os.path.isfile(filepath):
        raise not_found()
    mime_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
    res.set_header('content-type', mime_type)

    def _static_file_generator(path):
        block_size = 8192
        with open(path, 'rb') as f:
            block = f.read(block_size)
            while block:
                yield block
                block = f.read(block_size)

    return _static_file_generator(filepath)


def environ_from_url(path):
    """Used for test.

    :return
    """
    pass


def environ_add_POST(env, data, content_type=None):
    """Used for test.

    :param env:
    :param data:
    :param content_type:
    :return:
    """
    pass

###########

###########


