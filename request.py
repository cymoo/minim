# coding=utf-8

from urllib.parse import parse_qs, quote as url_quote, unquote as url_unquote
from http.cookies import SimpleCookie
import time
from datetime import timedelta, date, datetime
from json import dumps as json_dumps
from json import loads as json_loads

from io import BytesIO

from structures import MultiDict, ConfigDict, FormsDict, HeadersDict, environ_property,\
    iter_multi_items, cached_property
from formpaser import LimitedStream, FormDataParser, parse_options_header


class Request:
    """
    The request object contains the information transmitted by the client (web browser).
    which is created with the WSGI environ.

    Request objects are **read only**.
    """
    #: the maximum content length. This is forwarded to the form data
    #: parsing function. When set and the :attr:'form' or :attr:'files'
    #: attribute is accessed and the parsing fails because more than the
    #: specified value is transmitted a 413 error is raised.
    MAX_CONTENT_LENGTH = 1024*1000*100

    #: the maximum form field size. This is forwarded to the form data
    #: parsing function. When set and the :attr:'form' and attr:'files'
    #: attribute is accessed and the data in memory for post data is longer
    #: than specified value a 413 error is raised.
    MAX_FORM_MEMORY_SIZE = 1024*1000*10

    charset = 'utf-8'

    def __init__(self, environ=None):
        self.environ = {} if environ is None else environ

    def bind_env(self, environ):
        self.environ = environ

    @property
    def method(self):
        return self.environ.get('REQUEST_METHOD', 'GET').upper()

    @property
    def query_string(self):
        return self.environ.get('QUERY_STRING', '')

    @property
    def content_type(self):
        return self.environ.get('CONTENT_TYPE', '')

    @property
    def is_chunked(self):
        """
        True if Chunked transfer encoding was.
        see ** https://en.wikipedia.org/wiki/Chunked_transfer_encoding
            http://www.tuicool.com/articles/IBrUZj **
        for a preview of what 'transfer_encoding' is.
        :return:
        """
        return 'chunked' in self.environ.get('HTTP_TRANSFER_ENCODING', '').lower()

    @property
    def content_length(self):
        """
        The request body length as an integer. The client is responsible to
        set this header. Otherwise, the real length of the body is unknown
        and -1 is returned. In this case, :attr:'body' will be empty.

        :return:
        """
        return int(self.environ.get('CONTENT_LENGTH') or -1)

    def _load_form_data(self):
        """
        Method used internally to retrieve submitted data. After calling this sets
        'form' and 'files' on the request object to multi dicts filled with the
        incoming form data. As a matter of fact the input stream will be empty
        afterwards. You can also call this method to force the parsing of the
        form data.
        :return:
        """
        if 'form' in self.__dict__:
            return

        if bool(self.content_type):
            content_type = self.content_type
            content_length = self.content_length
            mimetype, options = parse_options_header(content_type)
            parser = FormDataParser(max_form_memory_size=self.MAX_FORM_MEMORY_SIZE,
                                    max_content_length=self.MAX_CONTENT_LENGTH)
            data = parser.parse(self._get_stream_for_parsing(),
                                mimetype, content_length, options)
        else:
            data = (self.stream, MultiDict(), MultiDict)

        d = self.__dict__
        d['stream'], d['form'], d['files'] = data

    def _get_stream_for_parsing(self):
        """
        This is the same as accessing: attr:'stream' with the difference that if it
        finds cached data from calling: meth:'get_data' first it will create a new
        stream out of the cached data.
        :return:
        """
        cached_data = getattr(self, '_cached_data', None)
        if cached_data is not None:
            return BytesIO(cached_data)
        return self.stream

    @cached_property
    def stream(self):
        """
        The stream to read incoming data from. Unlike :attr:'input_stream' this stream
        is properly guarded that you can't accidentally read past the length of the input.
        Minim will internally always refer to this stream to read data which makes it
        possible to wrap this object with a stream that does filtering.

        This stream is now always available but might be consumed by the form parser later
        on. Previously the stream was only set if no parsing happened.
        :return:
        """
        return self.get_input_stream()

    def get_input_stream(self, safe_fallback=True):
        """Returns the input stream from the WSGI environment and wraps it
        in the most sensible way possible. The stream returned is not the
        raw WSGI stream in most cases but one that is safe to read from
        without taking into account the content length.

        :param safe_fallback: indicates whether the function should use an empty
                     stream as safe fallback or just return the original
                     WSGI input stream if it can't wrap it safely.  The
                     default is to return an empty string in those cases.
        """
        stream = self.environ['wsgi.input']
        # A wsgi extension that tells us if the input is terminated.  In
        # that case we return the stream unchanged as we know we can safely
        # read it until the end.
        if self.environ.get('wsgi.has_received_stream'):
            return stream
        content_length = self.content_length

        if content_length == -1:
            return safe_fallback and BytesIO() or stream

        return LimitedStream(stream, content_length)

    def get_data(self, cache=True, to_unicode=False, parse_form_data=False):
        """
        This reads the buffered incoming data from the client into one byte string.
        By default this is cached but that behavior can be changed by setting 'cache'
        to 'False'.
        Usually it's a bad idea to call this method without checking the content length
        first as client could send dozens of megabytes or more to cause memory problems
        on the server.

        Note that if the form data was already parsed this method will not return anything
        as form data parsing does not cache the data like this method does. To implicitly
        invoke form data parsing function set 'parse_form_data' to 'True'. When this is
        done the return value of this method will be an empty string if the form parser
        handles the data. This generally is not necessary as if the whole data is cached
        (which is the default) the form parser will used the cached data to parse the form
        data. Please be generally aware of checking the content length first in any case
        before calling this method to avoid exhausting server memory.

        If 'as_text' is set to 'True' the return value will be a decoded unicode string.

        :param cache:
        :param to_unicode:
        :param parse_form_data:
        :return:
        """

        rv = getattr(self, '_cached_data', None)
        if rv is None:
            if parse_form_data:
                self._load_form_data()
            rv = self.stream.read()
            if cache:
                self._cached_data = rv
        if to_unicode:
            rv = rv.decode(self.charset)
        return rv

    def close(self):
        """
        Closes associated resources of this request object. This closes all file
        handles explicitly. You can also use the request object in a with statement
        which will automatically close it.
        :return:
        """
        files = self.__dict__.get('files')
        for key, value in iter_multi_items(files or ()):
            value.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @cached_property
    def form(self):
        """
        The form parameters. A :class:'MultiDict' is returned from this function.
        """
        self._load_form_data()
        return self.form

    @cached_property
    def files(self):
        """
        A :class:'MultiDict' object containing all uploaded files. Each key in
        :attr:'files' is the name from the "<input type='file' name="">". Each value
        in :attr:'files' is a :class:'FileStorage' object.

        Note that :attr:'files' will only contain data if the request method was POST,
        PUT or DELETE and "<form>" that posted to the request had "enctype="multipart
        /form-data"". It will empty otherwise.
        :return:
        """
        self._load_form_data()
        return self.files

    @cached_property
    def values(self):
        """
        Return a multi dict for :attr:'args' and :attr:'form'.
        """
        pass

    @cached_property
    def GET(self):
        """
        The :attr:'query_string' parsed into a :class:'FormsDict'.
        These values are sometimes called "URL arguments" or "GET parameters".

        :return:
        """
        get = FormsDict()
        pairs = parse_qs(self.query_string, keep_blank_values=True)
        for key, value in pairs.items():
            get.setlist(key, value)
        return get

    args = query = GET

    @cached_property
    def POST(self):
        pass

    @property
    def is_json(self):
        return None

    def json(self):
        pass

    def accept_mimetypes(self):
        pass

    def accept_charsets(self):
        pass

    def accept_encoding(self):
        pass

    def accept_language(self):
        pass

    def cache_control(self):
        pass

    def if_match(self):
        pass

    def if_none_match(self):
        pass

    def is_modified_since(self):
        pass

    def if_unmodified_since(self):
        pass

    def if_range(self):
        pass

    def range(self):
        pass

    def user_agent(self):
        pass

    def authorization(self):
        pass

    @environ_property('environ', 'minim.request.cookies')
    def cookies(self):
        """
        Cookies parsed into a :class:'FormsDict'.

        :return:
        """
        cookies = SimpleCookie(self.environ.get('HTTP_COOKIE', '')).values()

        return FormsDict((c.key, c.value) for c in cookies)

    def get_cookie(self, key, default=None):
        """
        The content of a cookie.

        :param key:
        :return:
        """
        return self.cookies.get(key) or default

    @property
    def referer(self):
        """"""
        return self.environ.get('HTTP_REFERER', '0.0.0.0')

    @property
    def host(self):
        """
        Returns the real host. First checks the 'X-Forwarded-Host' header, then the normal
        'Host' header, and finally the 'SERVER_NAME' environment variable.
        :return:
        """
        if 'HTTP_X_FORWARDED_HOST' in self.environ:
            rv = self.environ['HTTP_X_FORWARDED_HOST'].split(',', 1)[0].strip()
        elif 'HTTP_HOST' in self.environ:
            rv = self.environ['HTTP_HOST']
        else:
            rv = self.environ['SERVER_NAME']
            if (self.environ['wsgi.url_scheme'], self.environ['SERVER_PORT']) not \
                    in (('https', '443'), ('http', '80')):
                rv += ':' + self.environ['SERVER_PORT']
        return rv

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
        """
        env = self.environ
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
        env = self.environ
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

    @property
    def path(self):
        """
        Requested path. This works a bit like the regular path info in
        the WSGI environment, but always include a leading slash, even if
        the URL root is accessed.
        :return:
        """
        return url_unquote(self.environ.get('PATH_INFO', ''))

    @environ_property('environ', 'minim.request.full_path')
    def full_path(self):
        """
        Requested path including the query string.
        :return:
        """
        qs = self.query_string
        return self.path + '?' + qs if qs else self.path

    @environ_property('environ', 'minim.request.script_root')
    def script_root(self):
        """
        The root path of the script without the trailing slash.
        :return:
        """
        raw_path = self.environ.get('SCRIPT_NAME') or ''
        return raw_path.rstrip('/')

    def _get_current_url(self, environ, root_only=False, strip_qs=False,
                         host_only=False):
        """
        A handy helper function that recreates the full URL for the current request.
        :param environ: the WSGI environment.
        :param root_only: set to 'True' if you only want the root URL.
        :param strip_qs: set to 'True' if you don't want the query string.
        :param host_only: set to 'True' if the host url should be returned.
        :return:
        """
        tmp = [environ['wsgi.url_scheme'], '://', self.host]
        cat = tmp.append
        if host_only:
            return ''.join(tmp) + '/'
        cat(url_quote(environ.get('SCRIPT_NAME', '')).rstrip('/'))
        cat('/')
        if not root_only:
            cat(environ.get('PATH_INFO', '').lstrip('/'))
            if not strip_qs:
                qs = self.query_string
                if qs:
                    cat('?' + qs)
        return ''.join(tmp)

    @environ_property('environ', 'minim.request.url')
    def url(self):
        """
        The reconstructed current URL as IRI.
        :return:
        """
        return self._get_current_url(self.environ)

    @environ_property('environ', 'minim.request.base_url')
    def base_url(self):
        """
        Like :attr: 'url' but without the query string.
        :return:
        """
        return self._get_current_url(self.environ, strip_qs=True)

    @environ_property('environ', 'minim.request.url_root')
    def url_root(self):
        """
        The full URL root (with hostname), this is the application root as IRI.
        :return:
        """
        return self._get_current_url(self.environ, root_only=True)

    @environ_property('environ', 'minim.request.host_url')
    def host_url(self):
        """
        Just the host with scheme as IRI.
        :return:
        """
        return self._get_current_url(self.environ, host_only=True)

    @property
    def is_xhr(self):
        requested_with = self.environ.get('HTTP_X_REQUESTED_WITH', '')
        return requested_with.lower() == 'xmlhttprequest'

    # An alias for :attr:'is_xhr'
    is_ajax = is_xhr

    @property
    def is_secure(self):
        """'True' if the request is secure."""
        return self.environ.get('wsgi.url_scheme', '') == 'https'

    def copy(self):
        """
        Return a new :class:'Request' with a shallow :attr:'environ' copy.
        """
        return Request(self.environ.copy())

    def get(self, name, default=None):
        """
        Return the environ item.
        """
        return self.environ.get(name, default)

    def keys(self):
        return self.environ.keys()

    def __getitem__(self, key):
        return self.environ[key]

    # def __setitem__(self, key, value):
    #     raise KeyError('The request object is read-only.')

    # def __delitem__(self, key):
    #     self[key] = ''
    #     del self._environ[key]

    def __iter__(self):
        return iter(self.environ)

    def __len__(self):
        return len(self.environ)

    def __repr__(self):
        return '<%s: %s %s>' % (self.__class__.__name__, self.method, self.url)