#coding:utf-8

import os
import threading
import re
import cgi
import mimetypes
import urllib.parse
import logging
from http.cookies import SimpleCookie
import time
from datetime import timedelta, date, datetime
from json import dumps as json_dumps

from io import StringIO


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


# convert tuple, list, set to list
def make_list(data):
    if isinstance(data, (tuple, list, set)):
        return list(data)
    elif data:
        return [data]
    else:
        return []


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

# _RE_RESPONSE_STATUS = re.compile(r'^\d\d\d( [\w ]+)?$')

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

response_header_dict = _RESPONSE_HEADER_DICT
_HEADER_X_POWERED_BY = ('X-Powered-By', 'minim/0.1')


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


def see_other(location):
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


def _to_bytes(s):
    if isinstance(s, str):
        return s.encode('utf-8')
    if isinstance(s, bytes):
        return s

# _re_route = re.compile(r'(:[a-zA-Z_]\w*)')


# def _build_re(path):
#     re_list = ['^']
#     var_list = []
#     is_var = False
#
#     for v in _re_route.split(path):
#         if is_var:
#             var_name = v[1:]
#             var_list.append(var_name)
#             re_list.append(r'(?P<%s>[^/]+)' % var_name)
#         else:
#             s = ''
#             for ch in v:
#                 if '0' <= ch <= '9':
#                     s += ch
#                 elif 'a' <= ch <= 'z':
#                     s += ch
#                 elif 'A' <= ch <= 'Z':
#                     s += ch
#                 else:
#                     s += ch
#             re_list.append(s)
#         is_var = not is_var
#     re_list.append('$')
#     return ''.join(re_list)


# class Route:
#     """
#     A Route object is a callable object.
#     """
#     def __init__(self, func):
#         self.path = func.__web_route__
#         self.method = func.__web_method__
#         self.is_static = _re_route.search(self.path) is None
#         if not self.is_static:
#             self.route = re.compile(_build_re(self.path))
#         self.func = func
#
#     # needs modified...
#     def match(self, url):
#         m = self.route.match(url)
#         if m:
#             return m.groups()
#         return None
#
#     def __call__(self, *args, **kw):
#         return self.func(*args, **kw)
#
#     def __str__(self):
#         if self.is_static:
#             return 'Route(static, %s, path=%s)' % (self.method, self.path)
#         return 'Route(dynamic, %s, path=%s)' % (self.method, self.path)
#
#     __repr__ = __str__


def _static_file_generator(fpath):
    block_size = 8192
    with open(fpath, 'rb') as f:
        block = f.read(block_size)
        while block:
            yield block
            block = f.read(block_size)


# class StaticFileRoute:
#     def __init__(self):
#         self.method = 'GET'
#         self.is_static = False
#         self.route = re.compile(r'^/static/(.+)$')
#
#     def match(self, url):
#         if url.startswith('/static/'):
#             return (url[1:],)
#         return None
#
#     def __call__(self, *args):
#         fpath = os.path.join(ctx.application.document_root, args[0])
#         if not os.path.isfile(fpath):
#             raise notfound()
#         fext = os.path.splitext(fpath)[1]
#         ctx.response.content_type = mimetypes.types_map.get(fext.lower(), 'application/octet-stream')
#         return _static_file_generator(fpath)


# def favicon_handler():
    # return static_file_handler('/favicon.ico')


class MultipartFile:
    """
    Multipart file storage get from request input
    """
    def __init__(self, storage):
        self.filename = storage.filename
        self.file = storage.file


class Request(threading.local):
    def __init__(self, environ=None):
        super().__init__()
        self._environ = {} if environ is None else environ
        self._GET = None
        self._POST = None
        self._COOKIES = None
        self._HEADERS = None
        self.path = self._environ.get('PATH_INFO', '/').strip()
        if not self.path.startswith('/'):
            self.path += '/'

    def bind(self, environ):
        self._environ = environ

    @property
    def method(self):
        return self._environ.get('REQUEST_METHOD', 'GET').upper()

    @property
    def query_string(self):
        return self._environ.get('QUERY_STRING', '')

    @property
    def input_length(self):
        try:
            return max(0, int(self._environ.get('CONTENT_LENGTH', '0')))
        except ValueError:
            return 0

    # um, what is PEP8? Is it delicious?
    @property
    def GET(self):
        if self._GET is None:
            raw_dict = urllib.parse.parse_qs(self.query_string, keep_blank_values=True)
            self._GET = Dict()
            for key, value in raw_dict.items():
                if len(value) == 1:
                    self._GET[key] = value[0]
                else:
                    self._GET[key] = value
        return self._GET

    @property
    def POST(self):
        if self._POST is None:
            raw_data = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
            self._POST = Dict()
            for key in raw_data:
                if isinstance(raw_data[key], list):
                    self._POST[key] = [v.value for v in raw_data[key]]
                elif raw_data[key].filename:
                    self._POST[key] = raw_data[key]
                else:
                    self._POST[key] = raw_data[key].value
        return self._POST

    @property
    def cookies(self):
        if self._COOKIES is None:
                raw_dict = SimpleCookie(self._environ.get('HTTP_COOKIE', ''))
                self._COOKIES = Dict()
                for cookie in raw_dict.values():
                    self._COOKIES[cookie.key] = _unquote(cookie.value)
        return self._COOKIES

    @property
    def headers(self):
        if self._HEADERS is None:
            self._HEADERS = Dict()
            for key, value in self._environ.items():
                if key.startswith('HTTP_'):
                     # convert 'HTTP_ACCEPT_ENCODING' to 'ACCEPT-ENCODING'
                    self._HEADERS[key[5:].replace('_', '-').upper()] = value
        return self._HEADERS

    @property
    def remote_addr(self):
        return self._environ.get('REMOTE_ADDR', '0.0.0.0')

    @property
    def document_root(self):
        return self._environ.get('DOCUMENT_ROOT', '')

    @property
    def environ(self):
        return self._environ

    @property
    def request_method(self):
        return self._environ['REQUEST_METHOD']

    @property
    def path_info(self):
        return _unquote(self._environ.get('PATH_INFO', ''))

    @property
    def host(self):
        return self._environ.get('HTTP_HOST', '')


class Response(threading.local):
    default_content_type = 'text/html; charset=UTF-8'

    def __init__(self, status=None, headers=None, **more_headers):
        super().__init__()
        self._cookies = None
        self._status = '200 OK'
        self._headers = {'CONTENT-TYPE': 'text/html; charset=UTF-8'}

    @property
    def status_code(self):
        return int(self._status[:3])

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if isinstance(value, int):
            if 100 <= value <= 999:
                status_str = _RESPONSE_STATUSES.get(value, '')
                if status_str:
                    self._status = '%d %s' % (value, status_str)
                else:
                    self._status = str(value)
            else:
                raise ValueError('Bad response code: %d.' % value)
        else:
            raise TypeError('Bad type of response code.')

    @property
    def headers(self):
        l = [(_RESPONSE_HEADER_DICT.get(k, k), v) for k, v in self._headers.items()]
        if self._cookies is not None:
            for v in self._cookies.values():
                l.append(('Set-Cookie', v))
        l.append(_HEADER_X_POWERED_BY)
        return l

    def header(self, name):
        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        return self._headers.get(key)

    def unset_header(self, name):
        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        if key in self._headers:
            del self._headers[key]

    def set_header(self, name, value):
        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        self._headers[key] = value

    def set_cookie(self, name, value, secret=None, **options):
        if not self._cookies:
            self._cookies = SimpleCookie()
        if secret:
            pass

        if len(value) > 4096:
            raise ValueError('Cookie value too long.')
        self._cookies[name] = value

        for k, v in options.items():
            if k == 'max_age':
                if isinstance(v, timedelta):
                    v = v.seconds + v.days*24*3600
            if k == 'expires':
                if isinstance(v, (date, datetime)):
                    v = v.timetuple()
                elif isinstance(v, (int, float)):
                    v = time.gmtime(v)
                v = time.strftime('%a, %d %b %Y %H:%M:%S GMT', v)
            if k in ('secure', 'httponly') and not v:
                continue

            self._cookies[name][k.replace('_', '-')] = v

    def delete_cookie(self, key, **kw):
        kw['max_age'] = -1
        kw['expires'] = 0
        self.set_cookie(key, '', **kw)


class Router:
    def __init__(self):
        self.static_routes = {}
        self.dynamic_routes = {}
        self.dynamic_re_routes = {}

    def add(self, rule, method, callback):
        pass

    def _build_re(self, rule):
        slash_pattern = re.compile(r'/')
        str_pattern = re.compile(r'<\s*([a-zA-Z_]\w+)\s*>')
        int_pattern = re.compile(r'<\s*int:\s*([a-zA-Z_]\w+)\s*>')
        float_pattern = re.compile(r'<\s*float:\s*([a-zA-Z_]\w+)\s*>')
        re_pattern = re.compile(r'<\s*re:\s*(.+):\s*([a-zA-Z_]\w+)\s*>')
        re_list = ['^/']
        arg_list = []

        if rule.startswith('/'):
            rule = rule[1:]

        for seg in slash_pattern.split(rule):
            if str_pattern.match(seg):
                arg_name = str_pattern.match(seg).group(1)
                arg_list.append(arg_name)
                re_list.append(r'(?P<%s>\w+)' % arg_name)
                re_list.append('/')
            elif int_pattern.match(seg):
                arg_name = int_pattern.match(seg).group(1)
                arg_list.append(arg_name)
                re_list.append(r'(?P<%s>\d+)' % arg_name)
                re_list.append('/')
            elif float_pattern.match(seg):
                arg_name = float_pattern.match(seg).group(1)
                arg_list.append(arg_name)
                re_list.append(r'(?P<%s>\d+\.\d+)' % arg_name)
                re_list.append('/')
            elif re_pattern.match(seg):
                re_result = re_pattern.match(seg)
                inner_re = re_result.group(1)
                arg_name = re_result.group(2)
                arg_list.append(arg_name)
                re_list.append(r'(?P<%s>%s)' % (arg_name, inner_re))
                re_list.append('/')
            else:
                re_list.append(seg)
                re_list.append('/')
        re_list.pop(-1)
        re_list.append('$')
        return re.compile(''.join(re_list))

    def match(self, environ):
        pass


class Route:
    def __init__(self, app, rule, method, callback):
        self.app = app
        self.rule = rule
        self.methods = method
        self.callback = callback


class Cache:
    pass


class BaseTemplate:
    def __call__(self, path, model):
        pass


class MinimTemplate(BaseTemplate):
    pass


class Minim:
    def __init__(self, template_dir=None, Static_dir=None, auto_json=True, **kw):
        self._running = False
        self._router = Router()
        self._routes = []
        self.auto_json = auto_json

    def _is_running(self):
        if self._running:
            raise RuntimeError('A WSGIApplication is already running.')

    # def add_url(self, func):
    #     route = Route(func)
    #     if route.is_static:
    #         if route.method == 'GET':
    #             self._get_static[route.path] = route
    #         if route.method == 'POST':
    #             self._post_static[route.path] = route
    #     else:
    #         if route.method == 'GET':
    #             self._get_dynamic.append(route)
    #         if route.method == 'POST':
    #             self._post_dynamic.append(route)
    #     logging.info('Add route: %s' % str(route))

    def before_request(self):
        pass

    def after_request(self):
        pass

    def get(self, path):
        pass

    def post(self, path):
        pass

    def put(self, path):
        pass

    def delete(self, path):
        pass

    def patch(self, path):
        pass

    def head(self, path):
        pass

    def error(self, code=500):
        pass

    def match(self, environ):
        return self._router.match(environ)

    def add_route(self, route):
        self._routes.append(route)
        self._router.add(route.rule, route.method, route.callback)

    def route(self, rule=None, methods='GET'):
        def _decorator(func):
            for verb in make_list(methods):
                verb = verb.upper()
                route = Route(self, rule, verb, func)
                self.add_route(route)
            return func
        return _decorator

    def _handle(self):
        pass

    def _cast(self, out):
        if self.auto_json and isinstance(out, (dict, list)):
            out = [json_dumps(out).encode('utf-8')]
        elif not out:
            out = []
            response.set_header('Content-Length', '0')
        elif isinstance(out, str):
            out = [out.encode('utf-8')]
        elif isinstance(out, bytes):
            out = [out]
        elif hasattr(out, 'read'):
            # out = request.environ.get('wsgi.file_wrapper', lambda x: iter(lambda: x.read(8192), ''))(out)
            pass
        elif not hasattr(out, '__iter__'):
            raise TypeError('Request handler returned [%s] which is not iterable.' % type(out).__name__)
        return out

    def render(self):
        pass

    def cached(self, max_age=None, max_page_num=None):
        pass

    def wsgi(self, environ, start_response):
        request.bind(environ)
        start_response(response.status, response.headers)
        return self._cast('Hello Minim!')

    # def run(self):
    #     pass

    def __call__(self, environ, start_response):
        return self.wsgi(environ, start_response)

    def run(self, host='127.0.0.1', port=9000):
        from wsgiref.simple_server import make_server
        logging.warning('application will start at %s:%s...' % (host, port))
        server = make_server(host, port, self)
        server.serve_forever()

    # def get_wsgi_app(self):
    #     self._check_not_running()
    #
    #     self._running = True
    #
    #     def fn_route():
    #         request_method = ctx.request.request_method
    #         path_info = ctx.request.path_info
    #         if request_method == 'GET':
    #             fn = self._get_static.get(path_info, None)
    #             if fn:
    #                 return fn()
    #             for fn in self._get_dynamic:
    #                 args = fn.match(path_info)
    #                 if args:
    #                     return fn(*args)
    #             raise notfound()
    #         if request_method == 'POST':
    #             fn = self._post_static.get(path_info, None)
    #             if fn:
    #                 return fn()
    #             for fn in self._post_dynamic:
    #                 args = fn.match(path_info)
    #                 if args:
    #                     return fn(*args)
    #             raise notfound()
    #         raise badrequest()
    #
    #     def wsgi(env, start_response):
    #         ctx.request = Request(env)
    #         response = ctx.response = Response()
    #         start_response('200 OK', [('Content-Type', 'text/plain')])
    #         r = fn_route()
    #         return self._cast(r)
    #
    #     return wsgi

    # def add_interceptor(self, func):
    #     pass
    #
    # @property
    # def template_engine(self):
    #     return None
    #
    # @template_engine.setter
    # def template_engine(self, engine):
    #     pass

# Module initialization

request = Request()
response = Response()
local = threading.local()