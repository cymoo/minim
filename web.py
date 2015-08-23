#coding:utf-8

import os
import sys
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

from utils import make_list
from http_constants import RESPONSE_HEADER_DICT, RESPONSE_HEADERS,\
    RESPONSE_STATUSES, HEADER_X_POWERED_BY

# from session import Session


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

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError


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


class Request(threading.local):

    # __slots__ = ('_environ',)

    def bind(self, environ=None):
        # super().__init__()
        self._environ = {} if environ is None else environ
        # self._GET = None
        # self._POST = None
        # self._COOKIES = None
        # self._HEADERS = None
        # self.path = self._environ.get('PATH_INFO', '/').strip()
        # if not self.path.startswith('/'):
        #     self.path += '/'

    # def bind(self, environ):
    #     self._environ = environ

    @property
    def method(self):
        return self._environ.get('REQUEST_METHOD', 'GET').upper()

    @property
    def query_string(self):
        return self._environ.get('QUERY_STRING')

    @property
    def content_type(self):
        return self._environ.get('CONTENT_TYPE', '').lower()

    @property
    def input_length(self):
        try:
            return max(0, int(self._environ.get('CONTENT_LENGTH', '0')))
        except ValueError:
            return 0

    # um, what is PEP8? Is it delicious?
    @property
    def GET(self):
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
    def is_xhr(self):
        requested_with = self._environ.get('HTTP_X_REQUESTED_WITH', '')
        return requested_with.lower() == 'xmlhttprequest'

    @property
    def is_ajax(self):
        return self.is_xhr

    @property
    def path(self):
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
                status_str = RESPONSE_STATUSES.get(value, '')
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
        l = [(RESPONSE_HEADER_DICT.get(k, k), v) for k, v in self._headers.items()]
        if self._cookies is not None:
            for v in self._cookies.values():
                l.append(('Set-Cookie', v))
        l.append(HEADER_X_POWERED_BY)
        return l

    def header(self, name):
        key = name.upper()
        if not key in RESPONSE_HEADER_DICT:
            key = name
        return self._headers.get(key)

    def unset_header(self, name):
        key = name.upper()
        if not key in RESPONSE_HEADER_DICT:
            key = name
        if key in self._headers:
            del self._headers[key]

    def set_header(self, name, value):
        key = name.upper()
        if not key in RESPONSE_HEADER_DICT:
            key = name
        self._headers[key] = value

    # the options are max_age, expires, path, domain, httponly, secure
    def set_cookie(self, name, value, **options):
        if not self._cookies:
            self._cookies = SimpleCookie()

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
            # if k in ('secure', 'httponly') and not v:
            #     continue
            self._cookies[name][k.replace('_', '-')] = v

    def delete_cookie(self, key, **kw):
        kw['max_age'] = -1
        kw['expires'] = 0
        self.set_cookie(key, '', **kw)


def redirect(url, code=None):
    if not code:
        code = 303 if request.environ.get('SERVER_PROTOCOL') == 'HTTP/1.1' else 302
    response.status = code
    response.set_header('Location', url)
    return response


def send_file(directory, filename):
    filepath = os.path.join(directory, filename)
    if not os.path.isfile(filepath):
        raise not_found()
    mime_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
    response.set_header('content-type', mime_type)

    def _static_file_generator(path):
        block_size = 8192
        with open(path, 'rb') as f:
            block = f.read(block_size)
            while block:
                yield block
                block = f.read(block_size)

    return _static_file_generator(filepath)


class Router:
    def __init__(self):
        self.static_routes = {
            'GET': {},
            'POST': {},
            'PUT': {},
            'DELETE': {}
        }
        self.dynamic_routes = {
            'GET': {},
            'POST': {},
            'PUT': {},
            'DELETE': {}
        }

    @staticmethod
    def is_static(rule):
        pattern = re.compile(r'<[^/]+>')
        return True if pattern.search(rule) is None else False

    def add(self, rule, method, callback):
        if self.is_static(rule):
            self.static_routes[method][rule] = callback
        else:
            k = self._build_re(rule)
            self.dynamic_routes[method][k] = callback

    @staticmethod
    def _build_re(rule):
        slash_pat = re.compile(r'/')
        str_pat = re.compile(r'<\s*([a-zA-Z_]\w+)\s*>')
        int_pat = re.compile(r'<\s*int:\s*([a-zA-Z_]\w+)\s*>')
        float_pat = re.compile(r'<\s*float:\s*([a-zA-Z_]\w+)\s*>')
        re_list = ['^/']
        arg_list = []

        if rule.startswith('/'):
            rule = rule[1:]

        for seg in slash_pat.split(rule):
            if str_pat.match(seg):
                arg_name = str_pat.match(seg).group(1)
                arg_list.append(arg_name)
                re_list.append(r'(?P<%s>\w+)' % arg_name)
                re_list.append('/')
            elif int_pat.match(seg):
                arg_name = int_pat.match(seg).group(1)
                arg_list.append(arg_name + '_int_')
                re_list.append(r'(?P<%s>\d+)' % arg_name)
                re_list.append('/')
            elif float_pat.match(seg):
                arg_name = float_pat.match(seg).group(1)
                arg_list.append(arg_name + '_float_')
                re_list.append(r'(?P<%s>-?\d+\.\d{1,13})' % arg_name)
                re_list.append('/')
            else:
                re_list.append(seg)
                re_list.append('/')
        re_list.pop(-1)
        re_list.append('$')
        args = tuple(arg_list)
        return ''.join(re_list), args

    def match(self):
        method = request.method
        url = request.path
        static_func = self.static_routes[method].get(url)
        if static_func is not None:
            return static_func()

        for pattern_arg, dynamic_func in self.dynamic_routes[method].items():
            s = re.compile(pattern_arg[0]).match(url)
            if s is not None:
                params = make_list(s.groups())
                args = pattern_arg[1]
                for index, arg in enumerate(args):
                    if arg.endswith('_int_'):
                        params[index] = int(params[index])
                    if arg.endswith('_float_'):
                        params[index] = float(params[index])

                return dynamic_func(*params)

        # method not allowed
        for met, route in self.static_routes.items():
            if met == method:
                continue
            if route.get(url) is not None:
                raise not_allowed()

        for met, route in self.dynamic_routes.items():
            if met == method:
                continue
            for pair in route.keys():
                if re.compile(pair[0]).match(url) is not None:
                    raise not_allowed()
        # no match
        raise not_found()


class Route:
    def __init__(self, app, rule, method, callback):
        self.app = app
        self.rule = rule
        self.method = method
        self.callback = callback


class Cache:
    pass


class Minim:
    def __init__(self, import_name=__name__, template_path=None, static_path=None,
                 template_folder='templates', static_folder='static', auto_json=True, **kw):
        self.import_name = import_name
        self.template_path = template_path
        self.static_path = static_path
        self.template_folder = template_folder
        self.static_folder = static_folder
        self._running = False
        self._router = Router()
        self._routes = []
        self.auto_json = auto_json
        self._before_request_func = None
        self._after_request_func = None
        app_stack.push(self)

    def _is_running(self):
        if self._running:
            raise RuntimeError('A WSGIApplication is already running.')

    def get(self, rule, methods='GET'):
        return self.route(rule=rule, methods=methods)

    def post(self, rule, methods='POST'):
        return self.route(rule=rule, methods=methods)

    def put(self, rule, methods='PUT'):
        return self.route(rule=rule, methods=methods)

    def delete(self, rule, methods='DELETE'):
        return self.route(rule=rule, methods=methods)

    def head(self, path):
        pass

    def error(self, code=500):
        pass

    def before_request(self, func):
        self._before_request_func = func
        return func

    def after_request(self, func):
        self._after_request_func = func
        return func

    def match(self):
        return self._router.match()

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

    def _handle(self, environ):
        try:
            request.bind(environ)
            # should not set that here, but something curious with the thread stuff; just for test
            response.set_header('content-type', 'text/html; charset=UTF-8')
            response.status = 200
            try:
                if self._before_request_func is not None:
                    self._before_request_func()
                return self.match()
            finally:
                if self._after_request_func is not None:
                    self._after_request_func()
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception:
            raise

    def _cast(self, out):
        if self.auto_json and isinstance(out, (dict, list)):
            out = [json_dumps(out).encode('utf-8')]
        elif not out:
            out = []
            response.set_header('Content-Length', '0')
        elif isinstance(out, str):
            # test
            response.set_header('Content-Length', str(len(out.encode('utf-8'))))
            out = [out.encode('utf-8')]
        elif isinstance(out, bytes):
            out = [out]
        elif hasattr(out, 'read'):
            # out = request.environ.get('wsgi.file_wrapper', lambda x: iter(lambda: x.read(8192), ''))(out)
            pass
        elif not hasattr(out, '__iter__'):
            raise TypeError('Request handler returned [%s] which is not iterable.' % type(out).__name__)
        return out

    def cached(self, max_age=None, max_page_num=None):
        pass

    def wsgi(self, environ, start_response):
        try:
            out = self._cast(self._handle(environ))
            start_response(response.status, response.headers)

            return out
        finally:
            del request._environ
            response._cookies = None
            response._status = '200 OK'
            response._headers = {'CONTENT-TYPE': 'text/html; charset=UTF-8'}

    def __call__(self, environ, start_response):
        return self.wsgi(environ, start_response)

    def run(self, host='127.0.0.1', port=9000):
        from wsgiref.simple_server import make_server
        sys.stderr.write('Minim is running...Hit Ctrl-C to quit.\n')
        sys.stderr.write('Listening on http://%s:%d/.\n' % (host, port))
        server = make_server(host, port, self)
        server.serve_forever()


def render(template_name, **kwargs):
    from template import MiniTemplate
    app = app_stack.head
    if app.template_path is None:
        app.template_path = os.getcwd()
    full_path = os.path.join(app.template_path, app.template_folder, template_name)
    tpl = MiniTemplate(full_path)
    return tpl.render(**kwargs)


class FileUpload:
    pass


class AppStack(list):
    """
    A stack-like list. Calling it returns the head of the stack.
    """
    @property
    def head(self):
        return self[-1]

    def push(self, ins):
        """
        Add a new 'Minim' instance to the stack
        """
        if not isinstance(ins, Minim):
            ins = Minim()
        self.append(ins)
        return ins

# Module initialization

request = Request()
response = Response()
# session = Session()
g = threading.local()
app_stack = AppStack()