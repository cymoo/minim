"""
minim.web
~~~~~~~~~

...

"""
import os
import sys
import threading
import re
from urllib.parse import parse_qs, quote as url_quote, unquote as url_unquote
from http.cookies import SimpleCookie
import time
from datetime import timedelta, date, datetime
from json import dumps as json_dumps
from json import loads as json_loads

from io import BytesIO

from utils import make_list, safe_bytes, safe_str
from structures import MultiDict, ConfigDict, FormsDict, HeadersDict, environ_property,\
    FileStorage, iter_multi_items, cached_property
from web_utils import RESPONSE_STATUSES, HttpError, not_found, not_allowed
from formpaser import default_stream_factory, FormDataParser, parse_options_header,\
    get_input_stream

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

    # __slots__ = ('environ',)

    # MAX_MEM_FILE = 102400
    charset = 'utf-8'

    #: the maximum content length. This is forwarded to the form data
    #: parsing function. When set and the :attr:'form' or :attr:'files'
    #: attribute is accessed and the parsing fails because more than the
    #: specified value is transmitted a 413 error is raised.
    MAX_CONTENT_LENGTH = 1024*1000*10

    #: the maximum form field size. This is forwarded to the form data
    #: parsing function. When set and the :attr:'form' and attr:'files'
    #: attribute is accessed and the data in memory for post data is longer
    #: than specified value a 413 error is raised.
    MAX_FORM_MEMORY_SIZE = 1024*1000

    def bind(self, environ=None):
        self.environ = {} if environ is None else environ

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

    def _get_file_stream(self, total_content_length, content_type, filename=None,
                         content_length=None):
        """Called to get a stream for the file upload. This must provide a file-like
        class with 'read()', 'readline()' and 'seek()' methods that is both writeable
        and readable.


        :param total_content_length:
        :param content_type: the mimetype of the uploaded file.
        :param filename: the filename of the uploaded file. May be 'None'.
        :param content_length: the length of this file. This value is usually not provided
                               because web browsers do not provide this value.
        :return:
        """
        return default_stream_factory(total_content_length)

    @property
    def want_form_data_parsed(self):
        """Returns True if the request method carries content."""
        return bool(self.content_type)

    # def make_form_data_parser(self):
    #     """Creates the form data parser."""
    #     return FormDataParser(self._get_file_stream,
    #                           max_form_memory_size=self.MAX_FORM_MEMORY_SIZE,
    #                           max_content_length=self.MAX_CONTENT_LENGTH,
    #                           cls=MultiDict)

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

        if self.want_form_data_parsed:
            content_type = self.content_type
            content_length = self.content_length
            mimetype, options = parse_options_header(content_type)
            parser = FormDataParser(self._get_file_stream, max_form_memory_size=self.MAX_FORM_MEMORY_SIZE,
                                    max_content_length=self.MAX_CONTENT_LENGTH)
            data = parser.parse(self._get_stream_for_parsing(),
                                mimetype, content_length, options)
            # print(data)
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
        return get_input_stream(self.environ)

    @environ_property
    def input_stream(self):
        """
        In general it's a bad idea to use this one because you can easily read past
        the boundary. Use the :attr:'stream' instead.
        :return:
        """
        return self.environ['wsgi.input']

    def get_data(self, cache=True, as_text=False, parse_form_data=False):
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
        :param as_text:
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
        if as_text:
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

    # @environ_property('environ', 'minim.request.params')
    # def params(self):
    #     """
    #     A :class:'FormsDict' with the combined values of :attr:'query' and
    #     :attr:'forms'. File uploads are stored in :attr:'files'.
    #     """
    #     params = FormsDict()
    #     for key, value in self.query.items():
    #         params.add(key, value)
    #     for key, value in self.forms.items():
    #         params.add(key, value)
    #
    #     return params
    #
    # @environ_property('environ', 'minim.request.json')
    # def json(self):
    #     """
    #     If the "Content-Type" header is "application/json", this property holds
    #     the parsed content of the request body. Only requests smaller than :attr:
    #     'MAX_MEM_FILE' are processed to avoid memory exhaustion.
    #     :return:
    #     """
    #     ctype = self.environ.get('CONTENT_TYPE', '').lower().split(';')[0]
    #
    #     if ctype == 'application/json':
    #         body_string = self._get_body_string()
    #         if not body_string:
    #             return None
    #         return json_loads(body_string)
    #     return None
    #
    # @environ_property('environ', 'minim.request.forms')
    # def forms(self):
    #     """
    #     Form values parsed from an "url-encoded" or "multipart/form-data" encoded POST
    #     or PUT request body.
    #     The result is returned as a :class:'FormsDict'. All keys and values are string.
    #     File uploads are stored separately in :attr:'files'.
    #
    #     :return:
    #     """
    #     forms = FormsDict()
    #     for name, item in self.POST.items():
    #         if not isinstance(item, FileStorage):
    #             forms.add(name, item)
    #     return forms
    #
    # @environ_property('environ', 'minim.request.files')
    # def files(self):
    #     """
    #     File uploads parsed from "multipart/form-data" encoded POST or PUT request
    #     body.
    #
    #     :return: Instances of :class:'FileStorage'.
    #     """
    #     files = FormsDict()
    #     for name, item in self.POST.lists():
    #         if isinstance(item, FileStorage):
    #             files[name] = item
    #     return files

    # def _iter_body(self, read_func, buffer_size):
    #     """
    #
    #     :param read_func:
    #     :param buffer_size:
    #     :return:
    #     """
    #     max_read = max(0, self.content_length)
    #     while max_read:
    #         segment = read_func(min(max_read, buffer_size))
    #         if not segment:
    #             break
    #         yield segment
    #         max_read -= len(segment)
    #
    # @staticmethod
    # def _iter_chunked(read_func, buffer_size):
    #     """
    #
    #     :param read_func:
    #     :param buffer_size:
    #     :return:
    #     """
    #     http_400_error = HttpError(400, 'Error while parsing chunked transfer body.')
    #     rn, sem, bs = safe_bytes('\r\n'), safe_bytes(';'), safe_bytes('')
    #     while True:
    #         header = read_func(1)
    #         while header[-2:] != rn:
    #             c = read_func(1)
    #             header += c
    #             if not c:
    #                 raise http_400_error
    #             if len(header) > buffer_size:
    #                 raise http_400_error
    #         size, _, _ = header.partition(sem)
    #         try:
    #             max_read = int(safe_str(size.strip()), 16)
    #         except ValueError:
    #             raise http_400_error
    #         if max_read == 0:
    #             break
    #
    #         buffer = bs
    #         while max_read > 0:
    #             if not buffer:
    #                 buffer = read_func(min(max_read, buffer_size))
    #
    #             segment, buffer = buffer[:max_read], buffer[max_read:]
    #             if not segment:
    #                 raise http_400_error
    #             yield segment
    #
    #             max_read -= len(segment)
    #
    #         if read_func(2) != rn:
    #             raise http_400_error
    #
    # @environ_property('environ', 'minim.request.body')
    # def _body(self):
    #     try:
    #         read_func = self.environ['wsgi.input'].read
    #     except KeyError:
    #         self.environ['wsgi.input'] = BytesIO()
    #         return self.environ['wsgi.input']
    #     body_iter = self._iter_chunked if self.is_chunked else self._iter_body
    #
    #     body, body_size, is_tmp_file = BytesIO(), 0, False
    #     for segment in body_iter(read_func, self.MAX_FORM_MEMORY_SIZE):
    #         body.write(segment)
    #         print('body-value', body.getvalue())
    #         body_size += len(segment)
    #         print('body-size', body_size)
    #
    #         # if not is_tmp_file and body_size > self.MAX_FORM_MEMORY_SIZE:
    #         #     body, tmp = TemporaryFile(), body
    #         #     body.write(tmp.getvalue())
    #         #     del tmp
    #         #     is_tmp_file = True
    #
    #     self.environ['wsgi.input'] = body
    #     body.seek(0)
    #     return body
    #
    # @property
    # def body(self):
    #     """
    #     The HTTP request body as a seek-able file-like object.
    #     Depending on :attr:'MEX_MEM_FILE', this is either a temporary file or
    #     a :class:'io.BytesIO' instance. Accessing this property for the first
    #     time reads and replaces the "wsgi.input" environ variable.
    #     Subsequent accesses just do a 'seek(0)' on the file object.
    #
    #     :return:
    #     """
    #     self._body.seek(0)
    #     return self._body
    #
    # def _get_body_string(self):
    #     """
    #     Read body until content-length or MAX_MEM_FILE into a string.
    #     Raise HTTPError(413) on requests that are too large.
    #     """
    #     length = self.content_length
    #
    #     if length > self.MAX_CONTENT_LENGTH:
    #         raise HttpError(413, 'Request entity too large')
    #     if length < 0:
    #         length = self.MAX_MEM_FILE + 1
    #     data = self.body.read(length)
    #
    #     # if len(data) > self.MAX_CONTENT_LENGTH:
    #     #     raise HttpError(413, 'Request entity too large')
    #
    #     return data
    #
    # # um, what is PEP8? Is it delicious?
    # @environ_property('environ', 'minim.request.get')
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

    @property
    def is_json(self):
        return None

    def json(self):
        pass
    #
    # # An alias for :attr:'GET'
    # query = GET
    #
    # @environ_property('environ', 'minim.request.post')
    # def POST(self):
    #     """
    #     The values of :attr:'forms' and :attr:'files' combined into a single
    #     :class:'FormsDict'. Values are either strings (form values) or
    #     instances of :class:'cgi.FieldStorage' (file uploads).
    #
    #     Default form content_type is "application/x-www-form-urlencoded".
    #
    #     :return:
    #     """
    #     # raw_data = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
    #     # self._POST = Dict()
    #     # for key in raw_data:
    #     #     if isinstance(raw_data[key], list):
    #     #         self._POST[key] = [v.value for v in raw_data[key]]
    #     #     elif raw_data[key].filename:
    #     #         self._POST[key] = raw_data[key]
    #     #     else:
    #     #         self._POST[key] = raw_data[key].value
    #     # return self._POST
    #
    #     post = FormsDict()
    #     if not self.content_type.startswith('multipart/'):
    #         # print(self._get_body_string())
    #         pairs = parse_qs(safe_str(self._get_body_string()))
    #         for key, value in pairs.items():
    #             post.setlist(key, value)
    #         return post
    #
    #     safe_env = {'QUERY_STRING': ''}
    #     for key in {'REQUEST_METHOD', 'CONTENT_TYPE', 'CONTENT_LENGTH'}:
    #         if key in self.environ:
    #             safe_env[key] = self.environ[key]
    #
    #     # args = dict(fp=self.body, environ=safe_env, keep_blank_values=True,
    #     #             encoding='utf-8')
    #
    #     # print('wsgi-input', self.environ['wsgi.input'].read())
    #
    #     # print('content-type', self.content_type)
    #
    #     data = cgi.FieldStorage(fp=self.body, environ=safe_env, keep_blank_values=True)
    #
    #     print('data-headers', data.headers)
    #     # http://bugs.python.org/issue18394
    #     # self['_cgi.FieldStorage'] = data
    #     data = data.list or []
    #
    #     for item in data:
    #         if item.filename:
    #             # print('filename', item.filename)
    #             # post[item.name] = FileStorage(item.file, item.filename, item.name)
    #             file = FileStorage(item.file, item.filename, item.name)
    #             print('item.file', item.file)
    #             print('item.filename', item.filename)
    #             print('item.name', item.name)
    #             print('item.headers', item.headers)
    #             print('item.content-type', item.type)
    #             print('item.type_options', item.type_options)
    #             print('request.content-type', self.content_type)
    #             post.add(item.name, file)
    #
    #         else:
    #             # post[item.name] = item.value
    #             post.add(item.name, item.value)
    #
    #     return post
    #
    # # An alias for :attr:'POST'
    # post = POST

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


    ####
    ####




    @environ_property('environ', 'minim.request.cookies')
    def cookies(self):
        """
        Cookies parsed into a :class:'FormsDict'.

        :return:
        """
        cookies = SimpleCookie(self.environ.get('HTTP_COOKIE', '')).values()

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

    # @property
    # def wsgi_headers(self):
    #     """
    #     Raw WSGI environ.
    #     """
    #     return self.environ

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

    # @property
    # def is_multithread(self):
    #     """'True' if the application is served."""
    #     return self.environ.get('wsgi.multithread')
    #
    # @property
    # def is_multiprocess(self):
    #     """'True' if the application is served by a WSGI server that
    #     spawns multiple processed.
    #     """
    #     return self.environ.get('wsgi.multiprocess')
    #
    # @property
    # def is_run_once(self):
    #     """'True' if the application will be executed only once in a
    #     process lifetime. This is the case for CGI for example, but
    #     it's not guaranteed that execution only happens one time.
    #     """
    #     return self.environ.get('wsgi.run_once')

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


class Response(threading.local):
    default_status_code = 200
    default_content_type = 'text/html; charset=utf-8'

    def __init__(self, headers=None, status_code=None, content_type=None):
        super().__init__()
        if isinstance(headers, HeadersDict):
            self._headers = headers
        elif not headers:
            self._headers = HeadersDict()
        else:
            self._headers = HeadersDict(headers)

        if status_code is None:
            status_code = self.default_status_code
        if isinstance(status_code, int):
            self.status_code = status_code
        else:
            self.status = status_code

        if content_type is None:
            self._headers['Content-Type'] = self.default_content_type
        else:
            self._headers['Content-Type'] = content_type

    def copy(self, cls=None):
        pass

    def __iter__(self):
        pass

    def close(self):
        pass

    def _get_status_code(self):
        return self._status_code

    def _set_status_code(self, code):
        self._status_code = code
        try:
            self._status = '%d %s' % (code, RESPONSE_STATUSES[code].upper())
        except KeyError:
            self._status = '%d UNKNOWN' % code

    status_code = property(_get_status_code, _set_status_code,
                           doc='The HTTP status code as number')

    del _get_status_code, _set_status_code

    def _get_status(self):
        return self._status

    def _set_status(self, value):
        self._status = value
        try:
            self._status_code = int(self._status.split(None, 1)[0])
        except ValueError:
            self._status_code = 0
            self._status = '0 %s' % self._status

    status = property(_get_status, _set_status, doc='The HTTP status code')

    del _get_status, _set_status

    @property
    def wsgi_headers(self):
        return self._headers.to_wsgi_list()

    def get_header(self, name, default):
        return self._headers.get(name, default)

    def set_header(self, name, value, **kw):
        self._headers.set(name, value, **kw)

    def add_header(self, name, value, **kw):
        self._headers.add(name, value, **kw)

    def remove_header(self, name):
        self._headers.remove(name)

    def clear_headers(self):
        self._headers.clear()

    def iter_headers(self):
        return iter(self._headers)

    @property
    def charset(self, default='utf-8'):
        return None

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
            self._cookies[name][k.replace('_', '-')] = v

    def delete_cookie(self, key, **kw):
        kw['max_age'] = -1
        kw['expires'] = 0
        self.set_cookie(key, '', **kw)

    def cache_control(self):
        pass

    def make_conditional(self, request_or_environ):
        pass

    def add_etag(self):
        pass

    def set_etag(self):
        pass

    def freeze(self):
        pass

    def _get_content_range(self):
        return None

    def _set_content_range(self):
        pass

    content_range = property(_get_content_range, _set_content_range, doc="""""")

    del _get_content_range, _set_content_range

    def __contains__(self, name):
        return name in self._headers

    def __delitem__(self, name):
        del self._headers[name]

    def __getitem__(self, name):
        return self._headers[name]

    def __setitem__(self, name, value):
        self._headers[name] = value

    def __repr__(self):
        pass


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

request = Request()
response = Response()
# session = Session()
g = threading.local()
app_stack = AppStack()