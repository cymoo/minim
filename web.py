#coding:utf-8

import os
import sys
import threading
import re
import cgi
import mimetypes
from urllib.parse import parse_qs, quote, unquote
from tempfile import TemporaryFile
import logging
from http.cookies import SimpleCookie
import time
from datetime import timedelta, date, datetime
from json import dumps as json_dumps
from json import loads as json_loads

from io import StringIO, BytesIO

from utils import make_list, DictProperty,\
    safe_bytes, safe_str, FileStorage
from structures import ConfigDict, FormsDict, WSGIHeaderDict
from http_utils import RESPONSE_HEADER_DICT, RESPONSE_HEADERS,\
    RESPONSE_STATUSES, HEADER_X_POWERED_BY, HttpError, not_found, not_allowed

# from session import Session

__all__ = [
    'Request',
    'Response',
    'Router',
    'Route',
    'Minim'
]


class Request(threading.local):
    """
    The request object contains the information transmitted by the client (web browser).
    which is created with the WSGI environ.

    Request objects are **read only**.
    """

    # __slots__ = ('_environ',)

    MAX_MEM_FILE = 102400

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
        return self._environ.get('QUERY_STRING', '')

    @property
    def content_type(self):
        return self._environ.get('CONTENT_TYPE', '').lower()

    @property
    def is_chunked(self):
        """
        True if Chunked transfer encoding was.
        see ** https://en.wikipedia.org/wiki/Chunked_transfer_encoding
            http://www.tuicool.com/articles/IBrUZj **
        for a preview of what 'transfer_encoding' is.
        :return:
        """
        return 'chunked' in self._environ.get('HTTP_TRANSFER_ENCODING', '').lower()

    @property
    def content_length(self):
        """
        The request body length as an integer. The client is responsible to
        set this header. Otherwise, the real length of the body is unknown
        and -1 is returned. In this case, :attr:'body' will be empty.

        :return:
        """
        return int(self._environ.get('CONTENT_LENGTH') or -1)

    @DictProperty('environ', 'minim.request.params')
    def params(self):
        """
        A :class:'FormsDict' with the combined values of :attr:'query' and
        :attr:'forms'. File uploads are stored in :attr:'files'.

        :return:
        """
        params = FormsDict()
        for key, value in self.query.items():
            params[key] = value
        for key, value in self.forms.items():
            params[key] = value

        return params

    @DictProperty('environ', 'minim.request.json')
    def json(self):
        """
        If the "Content-Type" header is "application/json", this property holds
        the parsed content of the request body. Only requests smaller than :attr:
        'MAX_MEM_FILE' are processed to avoid memory exhaustion.
        :return:
        """
        ctype = self._environ.get('CONTENT_TYPE', '').lower().split(';')[0]

        if ctype == 'application/json':
            body_string = self._get_body_string()
            if not body_string:
                return None
            return json_loads(body_string)
        return None

    @DictProperty('environ', 'minim.request.forms')
    def forms(self):
        """
        Form values parsed from an "url-encoded" or "multipart/form-data" encoded POST
        or PUT request body.
        The result is returned as a :class:'FormsDict'. All keys and values are string.
        File uploads are stored separately in :attr:'files'.

        :return:
        """
        forms = FormsDict()
        for name, item in self.POST.items():
            if not isinstance(item, FileStorage):
                forms[name] = item
        return forms

    @DictProperty('environ', 'minim.request.files')
    def files(self):
        """
        File uploads parsed from "multipart/form-data" encoded POST or PUT request
        body.

        :return: Instances of :class:'FileStorage'.
        """
        files = FormsDict()
        for name, item in self.POST.items():
            if isinstance(item, FileStorage):
                files[name] = item
        return files

    def _iter_body(self, read_func, buffer_size):
        """

        :param read_func:
        :param buffer_size:
        :return:
        """
        max_read = max(0, self.content_length)
        while max_read:
            segment = read_func(min(max_read, buffer_size))
            if not segment:
                break
            yield segment
            # should be removed?
            max_read -= len(segment)

    @staticmethod
    def _iter_chunked(read_func, buffer_size):
        """

        :param read_func:
        :param buffer_size:
        :return:
        """
        http_400_error = HttpError(400, 'Error while parsing chunked transfer body.')
        rn, sem, bs = safe_bytes('\r\n'), safe_bytes(';'), safe_bytes('')
        while True:
            header = read_func(1)
            while header[-2:] != rn:
                c = read_func(1)
                header += c
                if not c:
                    raise http_400_error
                if len(header) > buffer_size:
                    raise http_400_error
            size, _, _ = header.partition(sem)
            try:
                max_read = int(safe_str(size.strip()), 16)
            except ValueError:
                raise http_400_error
            if max_read == 0:
                break

            buffer = bs
            while max_read > 0:
                if not buffer:
                    buffer = read_func(min(max_read, buffer_size))

                segment, buffer = buffer[:max_read], buffer[max_read:]
                if not segment:
                    raise http_400_error
                yield segment

                max_read -= len(segment)

            if read_func(2) != rn:
                raise http_400_error

    @DictProperty('environ', 'minim.request.body')
    def _body(self):
        try:
            read_func = self._environ['wsgi.input'].read
        except KeyError:
            self._environ['wsgi.input'] = BytesIO()
            return self._environ['wsgi.input']
        body_iter = self._iter_chunked if self.is_chunked else self._iter_body

        body, body_size, is_tmp_file = BytesIO(), 0, False
        for segment in body_iter(read_func, self.MAX_MEM_FILE):
            body.write(segment)
            body_size += len(segment)

            if not is_tmp_file and body_size > self.MAX_MEM_FILE:
                body, tmp = TemporaryFile(), body
                body.write(tmp.getvalue())
                del tmp
                is_tmp_file = True

        self._environ['wsgi.input'] = body
        body.seek(0)
        return body

    @property
    def body(self):
        """
        The HTTP request body as a seek-able file-like object.
        Depending on :attr:'MEX_MEM_FILE', this is either a temporary file or
        a :class:'io.BytesIO' instance. Accessing this property for the first
        time reads and replaces the "wsgi.input" environ variable.
        Subsequent accesses just do a 'seek(0)' on the file object.

        :return:
        """
        self._body.seek(0)
        return self._body

    def _get_body_string(self):
        """
        Read body until content-length or MAX_MEM_FILE into a string.
        Raise HTTPError(413) on requests that are too large.
        """
        length = self.content_length
        # I don't think the following is right...
        if length > self.MAX_MEM_FILE:
            raise HttpError(413, 'Request entity too large')
        if length < 0:
            length = self.MAX_MEM_FILE + 1
        data = self.body.read(length)

        if len(data) > self.MAX_MEM_FILE:
            raise HttpError(413, 'Request entity too large')

        return data

    # um, what is PEP8? Is it delicious?
    @DictProperty('environ', 'minim.request.get')
    def GET(self):
        """
        The :attr:'query_string' parsed into a :class:'FormsDict'.
        These values are sometimes called "URL arguments" or "GET parameters".

        :return:
        """
        get = FormsDict()
        pairs = parse_qs(self.query_string, keep_blank_values=True)
        for key, value in pairs:
            get[key] = value
        return get

    # An alias for :attr:'GET'
    query = GET

    @DictProperty('environ', 'minim.request.post')
    def POST(self):
        """
        The values of :attr:'forms' and :attr:'files' combined into a single
        :class:'FormsDict'. Values are either strings (form values) or
        instances of :class:'cgi.FieldStorage' (file uploads).

        Default form content_type is "application/x-www-form-urlencoded".

        :return:
        """
        # raw_data = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
        # self._POST = Dict()
        # for key in raw_data:
        #     if isinstance(raw_data[key], list):
        #         self._POST[key] = [v.value for v in raw_data[key]]
        #     elif raw_data[key].filename:
        #         self._POST[key] = raw_data[key]
        #     else:
        #         self._POST[key] = raw_data[key].value
        # return self._POST

        post = FormsDict()
        if not self.content_type.startswith('multipart/'):
            # Bottle decode it using 'latin1', why?
            pairs = parse_qs(safe_str(self._get_body_string()))
            for key, value in pairs:
                post[key] = value
            return post

        safe_env = {'QUERY_STRING': ''}
        for key in {'REQUEST_METHOD', 'CONTENT_TYPE', 'CONTENT_LENGTH'}:
            if key in self._environ:
                safe_env[key] = self.environ[key]

        args = dict(fp=self.body, environ=safe_env, keep_blank_values=True,
                    encoding='utf-8')

        data = cgi.FieldStorage(**args)

        # http://bugs.python.org/issue18394
        self['_cgi.FieldStorage'] = data
        data = data.list or []

        for item in data:
            if item.filename:
                post[item.name] = FileStorage(item.file, item.filename,
                                              item.name)

            else:
                post[item.name] = item.value

        return post

    # An alias for :attr:'POST'
    post = POST

    @DictProperty('environ', 'minim.request.cookies')
    def cookies(self):
        """
        Cookies parsed into a :class:'FormsDict'.

        :return:
        """
        cookies = SimpleCookie(self._environ.get('HTTP_COOKIE', '')).values()

        return FormsDict((c.key, c.value) for c in cookies)

        # if self._COOKIES is None:
        #         raw_dict = SimpleCookie(self._environ.get('HTTP_COOKIE', ''))
        #         self._COOKIES = Dict()
        #         for cookie in raw_dict.values():
        #             self._COOKIES[cookie.key] = unquote(cookie.value)
        # return self._COOKIES

    def get_cookie(self, key, default=None):
        """
        The content of a cookie.

        :param key:
        :return:
        """
        return self.cookies.get(key) or default

    @DictProperty('environ', 'minim.request.headers')
    def headers(self):
        """
        A :class:'WSGIHeaderDict' that provides case-insensitive access to
        HTTP request headers.

        :return:
        """
        return WSGIHeaderDict(self._environ)

        # if self._HEADERS is None:
        #     self._HEADERS = Dict()
        #     for key, value in self._environ.items():
        #         if key.startswith('HTTP_'):
        #              # convert 'HTTP_ACCEPT_ENCODING' to 'ACCEPT-ENCODING'
        #             self._HEADERS[key[5:].replace('_', '-').upper()] = value
        # return self._HEADERS
    def get_header(self, name):
        """

        :param name:
        :return:
        """
        return self.headers.get(name, None)

    @property
    def client_addr(self):
        """
        Returns the effective client IP as a string.
        If the "HTTP_X_FORWARDED_FOR" header exists in the WSGI environ, the attribute
        returns the client IP address present in that header (e.g. if the header value
        is '192.168.1.1, 192.168.1.2', the value will be '192.168.1.1'). If no "HTTP_
        FORWARDED_FOR" header is present in the environ at all, this attribute will
        return the value of the "REMOTE_ADDR" header. if the "REMOTE_ADDR" header is
        unset, this attribute will return the value "0.0.0.0".

        Warning:
        It is possible for user agents to put someone else's IP or just any string in
        "HTTP_X_FORWARDED_FOR" as it is a normal HTTP header. Forward proxies can provide
        incorrect values (private IP address etc). You cannot "blindly" trust the result
        of this method to provide you with valid data unless you're certain that "HTTP_
        X_FORWARDED_FOR" has the correct values. The WSGI server must be behind a trusted
        proxy for this to be true.
        """
        env = self._environ
        xff = env.get('HTTP_X_FORWARDED_FOR')
        if xff is not None:
            addr = xff.split(',')[0].strip()
        else:
            addr = env.get('REMOTE_ADDR', '0.0.0.0')
        return addr

    @property
    def host_port(self):
        """
        The effective server port number as a string. if the "HTTP_HOST" header exists in
        the WSGI environ, this attribute returns the port number present in that header.
        If the "HTTP_HOST" header exists but contains no explicit port number: if the WSGI
        url scheme is "https", this attribute returns "443"; if "http" then returns "80".
        If no "HTTP_HOST" header is present in the environ, returns the value of the "SERVER_PORT"
        header (which is guaranteed to be present).
        """
        env = self._environ
        host = env.get('HTTP_HOST')
        if host is not None:
            if ':' in host:
                port = host.split(':', 1)[1]
            else:
                url_scheme = env['wsgi.url_scheme']
                if url_scheme == 'https':
                    port = '443'
                else:
                    port = '80'
        else:
            port = env['SERVER_PORT']
        return port

    # @DictProperty('environ', 'minim.request.path', read_only=True)
    @property
    def path(self):
        """
        Requested path. This works a bit like the regular path info in
        the WSGI environment, but always include a leading slash, even if
        the URL root is accessed.
        :return:
        """
        return unquote(self._environ.get('PATH_INFO', ''))

    @DictProperty('environ', 'minim.request.full_path', read_only=True)
    def full_path(self):
        """
        Requested path including the query string.
        :return:
        """

    @DictProperty('environ', 'minim.request.script_root', read_only=True)
    def script_root(self):
        """
        The root path of the script without the trailing slash.
        :return:
        """

    @DictProperty('environ', 'minim.request.url', read_only=True)
    def url(self):
        """
        The reconstructed current URL as IRI.
        :return:
        """

    @DictProperty('environ', 'minim.request.base_url', read_only=True)
    def base_url(self):
        """
        Like :attr: 'url' but without the query string.
        :return:
        """

    @DictProperty('environ', 'minim.request.url_root', read_only=True)
    def url_root(self):
        """
        The full URL root (with hostname), this is the application root as IRI.
        :return:
        """

    @DictProperty('environ', 'minim.request.host_url', read_only=True)
    def host_url(self):
        """
        Just the host with scheme as IRI.
        :return:
        """

    # @property
    # def document_root(self):
    #     return self._environ.get('DOCUMENT_ROOT', '')

    @property
    def is_xhr(self):
        requested_with = self._environ.get('HTTP_X_REQUESTED_WITH', '')
        return requested_with.lower() == 'xmlhttprequest'

    # An alias for :attr:'is_xhr'
    is_ajax = is_xhr

    # @property
    # def path(self):
    #     return unquote(self._environ.get('PATH_INFO', ''))

    @property
    def host(self):
        return self._environ.get('HTTP_HOST', '')

    def copy(self):
        """
        Return a new :class:'Request' with a shallow :attr:'environ' copy.
        """
        return Request(self._environ.copy())

    def get(self, name, default=None):
        """
        Return the environ item.
        """
        return self._environ.get(name, default)

    def keys(self):
        return self._environ.keys()

    def __getitem__(self, key):
        return self._environ[key]

    def __setitem__(self, key, value):
        raise KeyError('The request object is read-only.')

    def __delitem__(self, key):
        self[key] = ''
        del self._environ[key]

    # def __getattr__(self, name):
    #     pass
    #
    # def __setattr__(self, key, value):
    #     pass

    def __iter__(self):
        return iter(self._environ)

    def __len__(self):
        return len(self._environ)

    def __repr__(self):
        return '<%s: %s %s>' % (self.__class__.__name__, self.method, self.url)


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
        print(url)
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


class Minim:
    def __init__(self, import_name=__name__, template_path=None, static_path=None,
                 template_folder='templates', static_folder='static', auto_json=True, **kw):
        self.config = ConfigDict(import_name)  # ...
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

    def cached(self, timeout=None):
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