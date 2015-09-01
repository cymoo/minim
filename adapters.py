"""
minim.adapters
~~~~~~~~~~~~~~

Adapters for template engines and WSGI servers.

"""

__all__ = [
    'ServerAdapter',
    'WSGIRefServer',
    'CherryPyServer',
    'PasteServer',
    'TornadoServer',
    'TwistedServer',
    'GeventServer',
    'GunicornServer',
    'AiohttpServer',

    'TemplateAdapter',
    'MiniTemplate',
    'Jinja2Template',
    'MakoTemplate',
    'CheetahTemplate'
]


class ServerAdapter:
    def __init__(self, host='127.0.0.1', port=8000, **options):
        self.host = host
        self.port = int(port)
        self.options = options

    def run(self, handler):
        pass

    def __repr__(self):
        args = ', '.join(['%s=%s' % (k, repr(v))
                         for k, v in self.options.items()])
        return '%s(%s)' % (self.__class__.__name__, args)


class WSGIRefServer(ServerAdapter):
    def run(self, app):
        pass


class CherryPyServer(ServerAdapter):
    def run(self, handler):
        pass


class PasteServer(ServerAdapter):
    def run(self, handler):
        pass


class TornadoServer(ServerAdapter):
    def run(self, handler):
        pass


class TwistedServer(ServerAdapter):
    def run(self, handler):
        pass


class GeventServer(ServerAdapter):
    def run(self, handler):
        pass


class GunicornServer(ServerAdapter):
    def run(self, handler):
        pass


class AiohttpServer(ServerAdapter):
    def run(self, handler):
        pass


class AutoServer(ServerAdapter):
    adapters = []

    def run(self, handler):
        pass


server_names = {
    'wsgiref': WSGIRefServer,
    'cherrypy': CherryPyServer,
    'paste': PasteServer,
    'tornado': TornadoServer,
    'twisted': TwistedServer,
    'gevent': GeventServer,
    'gunicorn': GunicornServer,
    'aiohttp': AiohttpServer,
    'auto': AutoServer
}


class TemplateAdapter:
    extensions = ['html', 'thtml', 'tpl', 'stpl']
    #: used in :meth:'prepare'
    setting = {}
    #: used in :meth:'render'
    defaults = {}

    def __init__(self, source=None, name=None, lookup=None, **setting):
        pass

    @classmethod
    def search(cls, name, lookup=None):
        pass

    @classmethod
    def global_config(cls, key, *args):
        pass

    def prepare(self, **options):
        raise NotImplementedError

    def render(self, *args, **kwargs):
        raise NotImplementedError


class MiniTemplate(TemplateAdapter):

    def prepare(self, **options):
        pass

    def render(self, *args, **kwargs):
        pass


class Jinja2Template(TemplateAdapter):

    def prepare(self, **options):
        pass

    def render(self, *args, **kwargs):
        pass

    def loader(self, name):
        pass


class MakoTemplate(TemplateAdapter):

    def prepare(self, **options):
        pass

    def render(self, *args, **kwargs):
        pass


class CheetahTemplate(TemplateAdapter):

    def prepare(self, **options):
        pass

    def render(self, *args, **kwargs):
        pass