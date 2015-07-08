#coding:utf-8

import threading
import re
import urllib.parse

from io import StringIO

# thread local object for storing request and response:
ctx = threading.local()


# Dict object:
class Dict(dict):
    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value


# all known response statues:

_RESPONSE_STATUSES = {
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

_RE_RESPONSE_STATUS = re.compile(r'^\d\d\d( [\w ]+)?$')

_RESPONSE_HEADERS = (
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

_RESPONSE_HEADER_DICT = dict(zip(map(lambda x: x.upper(), _RESPONSE_HEADERS), _RESPONSE_HEADERS))

_HEADER_X_POWERED_BY = ('X-Powered-By', 'minim/0.1')


# HTTP错误类
class HttpError(Exception):
    """
    HttpError that defines http error code.
    """
    def __init__(self, code):
        """
        Init an HttpError with response code.
        """
        super(HttpError, self).__init__()
        self.status = '%d %s' % (code, _RESPONSE_STATUSES[code])

    def header(self, name, value):
        if not hasattr(self, '_headers'):
            self._headers = [_HEADER_X_POWERED_BY]
        self._headers.append((name, value))

    @property
    def headers(self):
        if hasattr(self, '_headers'):
            return self._headers
        return []

    def __str__(self):
        return self.status

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


def badrequest():
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


def notfound():
    """
    Send a not found response.
    """
    return HttpError(404)


def conflict():
    """
    Send a conflict response.
    """
    return HttpError(409)


def internalerror():
    """
    Send an internal error response.
    """
    return HttpError(500)


def redirect(location):
    """
    Do permanent redirect.
    """
    return RedirectError(301, location)


def found(location):
    """
    Do temporary redirect.
    """
    return RedirectError(302, location)


def seeother(location):
    """
    Do temporary redirect.
    """
    return RedirectError(303, location)


def _quote(s):
    """
    Url quote as str.
    """
    return urllib.parse.quote(s)


def _unquote(s):
    """
    Url unquote as unicode.
    """
    return urllib.parse.unquote(s)


def get(path):
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'GET'
        return func
    return _decorator


def post(path):
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'POST'
        return func
    return _decorator


_re_route = re.compile(r'(:[a-zA-Z_]\w*)')


# request对象
class Request:
    # 根据key返回value
    def get(self, key, default=None):
        pass

    # 返回key-value的dict
    def input(self):
        pass

    # 返回URL的path
    @property
    def path_info(self):
        return None

    # 返回HTTP Headers:
    @property
    def headers(self):
        return None

    # 根据key返回Cookie value
    def cookie(self, name, default=None):
        pass


# response对象
class Response:
    # 设置header
    def set_header(self, key, value):
        pass

    # 设置cookie
    def set_cookie(self, name, value, max_age=None, expires=None, path='/'):
        pass

    # 设置status
    @property
    def status(self):
        return None

    @status.setter
    def status(self, value):
        pass


# 定义模板
def view(path):
    pass


# 定义拦截器
def interceptor(pattern):
    pass


# 定义模板引擎
class BaseTemplate:
    def __call__(self, path, model):
        pass


# 定义默认模板引擎
class MinimTemplate(BaseTemplate):
    pass


# 定义WSGIApplication
class WSGIApplication:
    def __init__(self, document_root=None, **kw):
        pass

    # 添加一个URL定义
    def add_url(self, func):
        pass

    # 添加一个Interceptor定义
    def add_interceptor(self, func):
        pass

    # 设置TemplateEngine
    @property
    def template_engine(self):
        return None

    @template_engine.setter
    def template_engine(self, engine):
        pass

    # 返回WSGI处理函数
    def get_wsgi_application(self):
        def wsgi(env, start_response):
            pass
        return wsgi




