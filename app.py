# coding=utf-8
"""
minim.web
~~~~~~~~~

...

"""
import os
import sys
import threading
import re
from json import dumps as json_dumps

from utils import make_list
from structures import ConfigDict
from httputil import not_found, not_allowed

# from session import Session

__all__ = [
    'Router',
    'Route',
    'Minim'
]


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
            response.status_code = 200
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
            start_response(response.status, response.wsgi_headers)

            return out
        finally:
            pass

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

g = threading.local()
app_stack = AppStack()