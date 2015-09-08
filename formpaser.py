"""
minim.formparser
~~~~~~~~~~~~~~~

This module was inspired greatly by werkzurg.


"""


import re
from tempfile import TemporaryFile
from io import BytesIO
import codecs
from itertools import chain, repeat, tee
from functools import update_wrapper

from structures import FormsDict, FilesDict, HeadersDict, FileStorage
from utils import safe_str, safe_bytes


__all__ = [
    'FormDataParser',
    'URLEncodedParser',
    'MultiPartParser',
    'LimitedStream',
    'get_input_stream'
]


#: an iterator that yields empty strings
_empty_string_iter = repeat('')

#: a regular expression for multipart boundaries
_multipart_boundary_re = re.compile('^[ -~]{0,200}[!-~]$')

#: supported http encodings that are also available in python we support
#: for multipart messages.
_supported_multipart_encodings = frozenset(['base64', 'quoted-printable'])


def default_stream_factory(total_content_length):
    """Creates a stream depending on content_length."""
    if total_content_length > 1024 * 500:
        return TemporaryFile('wb+')
    return BytesIO()


def exhaust_stream(f):
    """Helper decorator for methods that exhausts the stream on return."""

    def wrapper(self, stream, *args, **kwargs):
        try:
            return f(self, stream, *args, **kwargs)
        finally:
            exhaust = getattr(stream, 'exhaust', None)
            if exhaust is not None:
                exhaust()
            else:
                while 1:
                    chunk = stream.read(1024 * 64)
                    if not chunk:
                        break
    return update_wrapper(wrapper, f)


class FormDataParser(object):

    """This class implements parsing of form data for Minim. By itself
    it can parse multipart and url encoded form data.  It can be subclassed
    and extended but for most mimetypes it is a better idea to use the
    untouched stream and expose it as separate attributes on a request
    object.

    If the mimetype of the data transmitted is `multipart/form-data` the
    files multidict will be filled with `FileStorage` objects.  If the
    mimetype is unknown the input stream is wrapped and returned as first
    argument, else the stream is empty.


    :param stream_factory: An optional callable that returns a new read and
                           writeable file descriptor.  This callable works
                           the same as :meth:`~BaseResponse._get_file_stream`.
    :param charset: The character set for URL and url encoded form data.
    :param errors: The encoding error behavior.
    :param max_form_memory_size: the maximum number of bytes to be accepted for
                           in-memory stored form data.  If the data
                           exceeds the value specified an
                           :exc:`~exceptions.RequestEntityTooLarge`
                           exception is raised.
    :param max_content_length: If this is provided and the transmitted data
                               is longer than this value an
                               :exc:`~exceptions.RequestEntityTooLarge`
                               exception is raised.
    :param silent: If set to False parsing errors will not be caught.
    """

    def __init__(self, stream_factory=None, charset='utf-8',
                 errors='replace', max_form_memory_size=None,
                 max_content_length=None, silent=True):
        if stream_factory is None:
            stream_factory = default_stream_factory
        self.stream_factory = stream_factory
        self.charset = charset
        self.errors = errors
        self.max_form_memory_size = max_form_memory_size
        self.max_content_length = max_content_length
        self.silent = silent

    def get_parse_func(self, mimetype, options):
        return self.parse_functions.get(mimetype)

    def parse_from_environ(self, environ):
        """Parses the information from the environment as form data.

        :param environ: the WSGI environment to be used for parsing.
        :return: A tuple in the form ``(stream, form, files)``.
        """
        content_type = environ.get('CONTENT_TYPE', '')
        try:
            content_length = max(0, int(environ.get('CONTENT_LENGTH')))
        except (TypeError, ValueError):
            raise Exception('content-length is missing, are you using transfer encoding?'
                            'sorry, Minim does not support it currently.')

        mimetype, options = parse_options_header(content_type)
        return self.parse(get_input_stream(environ), mimetype,
                          content_length, options)

    def parse(self, stream, mimetype, content_length, options=None):
        """Parses the information from the given stream, mimetype,
        content length and mimetype parameters.

        :param stream: an input stream
        :param mimetype: the mimetype of the data
        :param content_length: the content length of the incoming data
        :param options: optional mimetype parameters (used for
                        the multipart boundary for instance)
        :return: A tuple in the form ``(stream, form, files)``.
        """
        if self.max_content_length is not None and \
           content_length is not None and \
           content_length > self.max_content_length:
            # raise exceptions.RequestEntityTooLarge()
            raise Exception('foo')
        if options is None:
            options = {}

        parse_func = self.get_parse_func(mimetype, options)

        if parse_func is not None:
            try:
                return parse_func(self, stream, mimetype,
                                  content_length, options)
            except ValueError:
                if not self.silent:
                    raise

        return stream, FormsDict(), FilesDict()

    @exhaust_stream
    def _parse_multipart(self, stream, mimetype, content_length, options):
        parser = MultiPartParser(self.stream_factory, self.charset, self.errors,
                                 max_form_memory_size=self.max_form_memory_size)
        boundary = options.get('boundary')
        if boundary is None:
            raise ValueError('Missing boundary')
        if isinstance(boundary, str):
            boundary = boundary.encode('ascii')

        form, files = parser.parse(stream, boundary, content_length)
        return stream, form, files

    @exhaust_stream
    def _parse_urlencoded(self, stream, mimetype, content_length, options):
        parser = URLEncodedParser(charset=self.charset, errors=self.errors)

        if self.max_form_memory_size is not None and \
           content_length is not None and \
           content_length > self.max_form_memory_size:
            # raise exceptions.RequestEntityTooLarge()
            raise Exception('foo')
        form = parser.parse(stream)
        return stream, form, FilesDict()

    #: mapping of mimetypes to parsing functions
    parse_functions = {
        'multipart/form-data':                  _parse_multipart,
        'application/x-www-form-urlencoded':    _parse_urlencoded,
        'application/x-url-encoded':            _parse_urlencoded
    }


class URLEncodedParser:
    def __init__(self, charset='utf-8', errors='replace'):
        self.charset = charset
        self.errors = errors

    def parse(self, stream, keep_blank=True, separator='&', limit=None):
        """Works like :func:`url_decode` but decodes a stream.  The behavior
        of stream and limit follows functions like :func:`.make_line_iter`.
        The generator of pairs is directly fed to the :class:'MultiDict',
        so you can consume the data while it's parsed.

        :param stream: a stream with the encoded querystring
        :param keep_blank: Set to `False` if you don't want empty values to
                              appear in the dict.
        :param separator: the pair separator to be used, defaults to ``&``
        :param limit: the content length of the URL data.  Not necessary if
                      a limited stream is provided.
        """
        pair_iter = self.make_chunk_iter(stream, separator, limit)
        return FormsDict(_url_decode_impl(pair_iter, self.charset,
                                          keep_blank, self.errors))

    @staticmethod
    def make_chunk_iter(stream, separator, limit=None, buffer_size=1024*10):
        """Works like :func:`make_line_iter` but accepts a separator
        which divides chunks.  If you want newline based processing
        you should use :func:`make_line_iter` instead as it
        supports arbitrary newline markers.
           added support for iterators as input stream.
        :param stream: the stream or iterate to iterate over.
        :param separator: the separator that divides chunks.
        :param limit: the limit in bytes for the stream.  (Usually
                      content length.  Not necessary if the `stream`
                      is otherwise already limited).
        :param buffer_size: The optional buffer size.
        """
        _iter = _make_chunk_iter(stream, limit, buffer_size)

        first_item = next(_iter, '')
        if not first_item:
            return

        _iter = chain((first_item,), _iter)
        if isinstance(first_item, str):
            separator = safe_str(separator)
            _split = re.compile(r'(%s)' % re.escape(separator)).split
            _join = ''.join
        else:
            separator = safe_bytes(separator)
            _split = re.compile(b'(' + re.escape(separator) + b')').split
            _join = b''.join

        buffer = []
        while True:
            new_data = next(_iter, '')
            if not new_data:
                break
            chunks = _split(new_data)
            new_buf = []
            for item in chain(buffer, chunks):
                if item == separator:
                    yield _join(new_buf)
                    new_buf = []
                else:
                    new_buf.append(item)
            buffer = new_buf
        if buffer:
            yield _join(buffer)


_begin_form = 'begin_form'
_begin_file = 'begin_file'
_content = 'content'
_end = 'end'


def is_valid_multipart_boundary(boundary):
    """Checks if the string given is a valid multipart boundary."""
    return _multipart_boundary_re.match(boundary) is not None


def _line_parse(line):
    """Removes line ending characters and returns a tuple (`stripped_line`,
    `is_terminated`).
    """
    if line[-2:] in ['\r\n', b'\r\n']:
        return line[:-2], True
    elif line[-1:] in ['\r', '\n', b'\r', b'\n']:
        return line[:-1], True
    return line, False


def parse_multipart_headers(iterable):
    """Parses multipart headers from an iterable that yields lines (including
    the trailing newline symbol).  The iterable has to be newline terminated.

    The iterable will stop at the line where the headers ended so it can be
    further consumed.

    :param iterable: iterable of strings that are newline terminated
    """

    result = []
    print('it', list(iterable))
    for line in iterable:
        line = safe_str(line)
        print('str(line)', str(line))
        line, line_terminated = _line_parse(line)
        print('line,line-ter', line, line_terminated)
        if not line_terminated:
            # why this exception is not raised.......
            raise ValueError('unexpected end of line in multipart header')
        if not line:
            break
        elif line[0] in ' \t' and result:
            key, value = result[-1]
            result[-1] = (key, value + '\n ' + line[1:])
        else:
            parts = line.split(':', 1)
            if len(parts) == 2:
                result.append((parts[0].strip(), parts[1].strip()))

    # we link the list to the headers, no need to create a copy, the
    # list was not shared anyways.
    return HeadersDict(result)


class MultiPartParser:

    def __init__(self, stream_factory=None, charset='utf-8', errors='replace',
                 max_form_memory_size=None, buffer_size=64 * 1024):
        self.stream_factory = stream_factory
        self.charset = charset
        self.errors = errors
        self.max_form_memory_size = max_form_memory_size
        if stream_factory is None:
            stream_factory = default_stream_factory
        # if cls is None:
        #     cls = MultiDict
        # self.cls = cls

        # make sure the buffer size is divisible by four so that we can base64
        # decode chunk by chunk
        assert buffer_size % 4 == 0, 'buffer size has to be divisible by 4'
        # also the buffer size has to be at least 1024 bytes long or long headers
        # will freak out the system
        assert buffer_size >= 1024, 'buffer size has to be at least 1KB'

        self.buffer_size = buffer_size

    def _fix_ie_filename(self, filename):
        """Internet Explorer 6 transmits the full file name if a file is
        uploaded.  This function strips the full path if it thinks the
        filename is Windows-like absolute.
        """
        if filename[1:3] == ':\\' or filename[:2] == '\\\\':
            return filename.split('\\')[-1]
        return filename

    def _find_terminator(self, iterator):
        """The terminator might have some additional newlines before it.
        There is at least one application that sends additional newlines
        before headers (the python setuptools package).
        """
        for line in iterator:
            if not line:
                break
            line = line.strip()
            if line:
                return line
        return b''

    def fail(self, message):
        raise ValueError(message)

    def get_part_encoding(self, headers):
        transfer_encoding = headers.get('content-transfer-encoding')
        if transfer_encoding is not None and \
           transfer_encoding in _supported_multipart_encodings:
            return transfer_encoding

    def get_part_charset(self, headers):
        # Figure out input charset for current part
        content_type = headers.get('content-type')
        if content_type:
            mimetype, ct_params = parse_options_header(content_type)
            return ct_params.get('charset', self.charset)
        return self.charset

    def start_file_streaming(self, filename, headers, total_content_length):
        if isinstance(filename, bytes):
            filename = filename.decode(self.charset, self.errors)
        filename = self._fix_ie_filename(filename)
        content_type = headers.get('content-type')
        try:
            content_length = int(headers['content-length'])
        except (KeyError, ValueError):
            content_length = 0
        container = self.stream_factory(total_content_length, content_type,
                                        filename, content_length)
        return filename, container

    def in_memory_threshold_reached(self, bytes):
        # raise exceptions.RequestEntityTooLarge()
        raise Exception('foo')

    def validate_boundary(self, boundary):
        if not boundary:
            self.fail('Missing boundary')
        if not is_valid_multipart_boundary(boundary):
            self.fail('Invalid boundary: %s' % boundary)
        if len(boundary) > self.buffer_size:  # pragma: no cover
            # this should never happen because we check for a minimum size
            # of 1024 and boundaries may not be longer than 200.  The only
            # situation when this happens is for non debug builds where
            # the assert is skipped.
            self.fail('Boundary longer than buffer size')

    def parse_lines(self, file, boundary, content_length):
        """Generate parts of
        ``('begin_form', (headers, name))``
        ``('begin_file', (headers, name, filename))``
        ``('cont', bytestring)``
        ``('end', None)``

        Always obeys the grammar
        parts = ( begin_form cont* end |
                  begin_file cont* end )*
        """
        next_part = b'--' + boundary
        last_part = next_part + b'--'

        iterator = chain(make_line_iter(file, limit=content_length,
                                        buffer_size=self.buffer_size),
                         _empty_string_iter)

        terminator = self._find_terminator(iterator)
        print('terminator', terminator)
        print('last-part', last_part)
        print('next-part', next_part)

        if terminator == last_part:
            print('1')
            return
        elif terminator != next_part:
            print('2')
            self.fail('Expected boundary at start of multipart data')
        #
        # print('terminator', terminator)
        # print('last_part', last_part)

        while terminator != last_part:
            headers = parse_multipart_headers(iterator)

            disposition = headers.get('content-disposition')

            if disposition is None:
                self.fail('Missing Content-Disposition header')
            disposition, extra = parse_options_header(disposition)
            transfer_encoding = self.get_part_encoding(headers)
            name = extra.get('name')
            filename = extra.get('filename')

            # if no content type is given we stream into memory.  A list is
            # used as a temporary container.
            if filename is None:
                yield _begin_form, (headers, name)

            # otherwise we parse the rest of the headers and ask the stream
            # factory for something we can write in.
            else:
                yield _begin_file, (headers, name, filename)

            buf = b''
            for line in iterator:
                if not line:
                    self.fail('unexpected end of stream')

                if line[:2] == b'--':
                    terminator = line.rstrip()
                    if terminator in (next_part, last_part):
                        break

                if transfer_encoding is not None:
                    if transfer_encoding == 'base64':
                        transfer_encoding = 'base64_codec'
                    try:
                        line = codecs.decode(line, transfer_encoding)
                    except Exception:
                        self.fail('could not decode transfer encoded chunk')

                # we have something in the buffer from the last iteration.
                # this is usually a newline delimiter.
                if buf:
                    yield _content, buf
                    buf = b''

                # If the line ends with windows CRLF we write everything except
                # the last two bytes.  In all other cases however we write
                # everything except the last byte.  If it was a newline, that's
                # fine, otherwise it does not matter because we will write it
                # the next iteration.  this ensures we do not write the
                # final newline into the stream.  That way we do not have to
                # truncate the stream.  However we do have to make sure that
                # if something else than a newline is in there we write it
                # out.
                if line[-2:] == b'\r\n':
                    buf = b'\r\n'
                    cutoff = -2
                else:
                    buf = line[-1:]
                    cutoff = -1
                yield _content, line[:cutoff]

            else:  # pragma: no cover
                raise ValueError('unexpected end of part')

            # if we have a leftover in the buffer that is not a newline
            # character we have to flush it, otherwise we will chop of
            # certain values.
            if buf not in (b'', b'\r', b'\n', b'\r\n'):
                yield _content, buf

            yield _end, None

    def parse_parts(self, file, boundary, content_length):
        """Generate ``('file', (name, val))`` and
        ``('form', (name, val))`` parts.
        """
        in_memory = 0

        for ellt, ell in self.parse_lines(file, boundary, content_length):
            if ellt == _begin_file:
                headers, name, filename = ell
                is_file = True
                guard_memory = False
                filename, container = self.start_file_streaming(
                    filename, headers, content_length)
                _write = container.write

            elif ellt == _begin_form:
                headers, name = ell
                is_file = False
                container = []
                _write = container.append
                guard_memory = self.max_form_memory_size is not None

            elif ellt == _content:
                _write(ell)
                # if we write into memory and there is a memory size limit we
                # count the number of bytes in memory and raise an exception if
                # there is too much data in memory.
                if guard_memory:
                    in_memory += len(ell)
                    if in_memory > self.max_form_memory_size:
                        self.in_memory_threshold_reached(in_memory)

            elif ellt == _end:
                if is_file:
                    container.seek(0)
                    yield ('file',
                           (name, FileStorage(container, filename, name,
                                              headers=headers)))
                else:
                    part_charset = self.get_part_charset(headers)
                    yield ('form',
                           (name, b''.join(container).decode(
                               part_charset, self.errors)))

    def parse(self, file, boundary, content_length):
        formstream, filestream = tee(
            self.parse_parts(file, boundary, content_length), 2)
        form = (p[1] for p in formstream if p[0] == 'form')
        files = (p[1] for p in filestream if p[0] == 'file')
        return FormsDict(form), FilesDict(files)


####
#: ~~~
####
_quoted_string_re = r'"[^"\\]*(?:\\.[^"\\]*)*"'

_option_header_piece_re = re.compile(
    r';\s*(%s|[^\s;=]+)\s*(?:=\s*(%s|[^;]+))?\s*' %
    (_quoted_string_re, _quoted_string_re)
)


def unquote_header_value(value, is_filename=False):
    r"""Unquotes a header value.  (Reversal of :func:`quote_header_value`).
    This does not use the real unquoting but what browsers are actually
    using for quoting.
    .. versionadded:: 0.5
    :param value: the header value to unquote.
    """
    if value and value[0] == value[-1] == '"':
        # this is not the real unquoting, but fixing this so that the
        # RFC is met will result in bugs with internet explorer and
        # probably some other browsers as well.  IE for example is
        # uploading files with "C:\foo\bar.txt" as filename
        value = value[1:-1]

        # if this is a filename and the starting characters look like
        # a UNC path, then just return the value without quotes.  Using the
        # replace sequence below on a UNC path has the effect of turning
        # the leading double slash into a single slash and then
        # _fix_ie_filename() doesn't work correctly.  See #458.
        if not is_filename or value[:2] != '\\\\':
            return value.replace('\\\\', '\\').replace('\\"', '"')
    return value


def parse_options_header(value):
    """Parse a ``Content-Type`` like header into a tuple with the content
    type and the options:
    >>> parse_options_header('text/html; charset=utf8')
    ('text/html', {'charset': 'utf8'})
    This should not be used to parse ``Cache-Control`` like headers that use
    a slightly different format.  For these headers use the
    :func:`parse_dict_header` function.
    .. versionadded:: 0.5
    :param value: the header to parse.
    :return: (str, options)
    """
    def _tokenize(string):
        for match in _option_header_piece_re.finditer(string):
            key, value = match.groups()
            key = unquote_header_value(key)
            if value is not None:
                value = unquote_header_value(value, key == 'filename')
            yield key, value

    if not value:
        return '', {}

    parts = _tokenize(';' + value)
    name = next(parts)[0]
    extra = dict(parts)
    return name, extra


def _make_chunk_iter(stream, limit, buffer_size):
    """Helper for the line and chunk iter functions."""
    if isinstance(stream, (bytes, bytearray, str)):
        raise TypeError('Passed a string or byte object instead of '
                        'true iterator or stream.')
    if not hasattr(stream, 'read'):
        for item in stream:
            if item:
                yield item
        return
    if not isinstance(stream, LimitedStream) and limit is not None:
        stream = LimitedStream(stream, limit)
    _read = stream.read
    while 1:
        item = _read(buffer_size)
        print(item)
        if not item:
            break
        yield item


def make_line_iter(stream, limit=None, buffer_size=10 * 1024):
    """Safely iterates line-based over an input stream.  If the input stream
    is not a :class:`LimitedStream` the `limit` parameter is mandatory.
    This uses the stream's :meth:`~file.read` method internally as opposite
    to the :meth:`~file.readline` method that is unsafe and can only be used
    in violation of the WSGI specification.  The same problem applies to the
    `__iter__` function of the input stream which calls :meth:`~file.readline`
    without arguments.
    If you need line-by-line processing it's strongly recommended to iterate
    over the input stream using this helper function.
    .. versionchanged:: 0.8
       This function now ensures that the limit was reached.
    .. versionadded:: 0.9
       added support for iterators as input stream.
    :param stream: the stream or iterate to iterate over.
    :param limit: the limit in bytes for the stream.  (Usually
                  content length.  Not necessary if the `stream`
                  is a :class:`LimitedStream`.
    :param buffer_size: The optional buffer size.
    """
    _iter = _make_chunk_iter(stream, limit, buffer_size)

    first_item = next(_iter, '')
    if not first_item:
        return

    s = make_literal_wrapper(first_item)
    empty = s('')
    cr = s('\r')
    lf = s('\n')
    crlf = s('\r\n')

    _iter = chain((first_item,), _iter)

    def _iter_basic_lines():
        _join = empty.join
        buffer = []
        while True:
            new_data = next(_iter, '')
            if not new_data:
                break
            new_buf = []
            for item in chain(buffer, new_data.splitlines(True)):
                new_buf.append(item)
                if item and item[-1:] in crlf:
                    yield _join(new_buf)
                    new_buf = []
            buffer = new_buf
        if buffer:
            yield _join(buffer)

    # This hackery is necessary to merge 'foo\r' and '\n' into one item
    # of 'foo\r\n' if we were unlucky and we hit a chunk boundary.
    previous = empty
    for item in _iter_basic_lines():
        if item == lf and previous[-1:] == cr:
            previous += item
            item = empty
        if previous:
            yield previous
        previous = item
    if previous:
        yield previous


class LimitedStream(object):

    """Wraps a stream so that it doesn't read more than a limited bytes. If the
    stream is exhausted and the caller tries to get more bytes from it
    :func:`on_exhausted` is called which by default returns an empty
    string.  The return value of that function is forwarded
    to the reader function.  So if it returns an empty string
    :meth:`read` will return an empty string as well.
    The limit however must never be higher than what the stream can
    output.

    :param stream: the stream to wrap.
    :param limit: the limit for the stream, must not be longer than
                  what the string can provide if the stream does not
                  end with `EOF` (like `wsgi.input`)
    """

    def __init__(self, stream, limit):
        self._read = stream.read
        self._pos = 0
        self.limit = limit

    @property
    def is_exhausted(self):
        """If the stream is exhausted this attribute is `True`."""
        return self._pos >= self.limit

    def on_exhausted(self):
        """This is called when the stream tries to read past the limit.
        The return value of this function is returned from the reading
        function.
        """
        # Read null bytes from the stream so that we get the
        # correct end of stream marker.
        return self._read(0)

    def on_disconnect(self):
        """What should happen if a disconnect is detected?  The return
        value of this function is returned from read functions in case
        the client went away.  By default a
        :exc:`~werkzeug.exceptions.ClientDisconnected` exception is raised.
        """
        # from werkzeug.exceptions import ClientDisconnected
        # raise ClientDisconnected()
        raise Exception('foo')

    def exhaust(self, chunk_size=1024 * 64):
        """Exhaust the stream.  This consumes all the data left until the
        limit is reached.
        :param chunk_size: the size for a chunk.  It will read the chunk
                           until the stream is exhausted and throw away
                           the results.
        """
        to_read = self.limit - self._pos
        chunk = chunk_size
        while to_read > 0:
            chunk = min(to_read, chunk)
            self.read(chunk)
            to_read -= chunk

    def read(self, size=None):
        """Read `size` bytes or if size is not provided everything is read.
        :param size: the number of bytes read.
        """
        if self._pos >= self.limit:
            return self.on_exhausted()
        if size is None or size == -1:  # -1 is for consistence with file
            size = self.limit
        to_read = min(self.limit - self._pos, size)
        try:
            read = self._read(to_read)
        except (IOError, ValueError):
            return self.on_disconnect()
        if to_read and len(read) != to_read:
            return self.on_disconnect()
        self._pos += len(read)
        return read

    def readline(self):
        return NotImplemented

    def readlines(self):
        return NotImplemented

    def tell(self):
        """Returns the position of the stream."""
        return self._pos


def make_literal_wrapper(reference):
        if isinstance(reference, str):
            return lambda x: x
        return lambda x: x.encode('latin1')


def get_input_stream(environ, safe_fallback=True):
    """Returns the input stream from the WSGI environment and wraps it
    in the most sensible way possible. The stream returned is not the
    raw WSGI stream in most cases but one that is safe to read from
    without taking into account the content length.

    :param environ: the WSGI environ to fetch the stream from.
    :param safe_fallback: indicates whether the function should use an empty
                 stream as safe fallback or just return the original
                 WSGI input stream if it can't wrap it safely.  The
                 default is to return an empty string in those cases.
    """
    stream = environ['wsgi.input']
    content_length = environ.get('CONTENT_LENGTH')
    if content_length is not None:
        try:
            content_length = max(0, int(content_length))
        except (ValueError, TypeError):
            pass

    # A wsgi extension that tells us if the input is terminated.  In
    # that case we return the stream unchanged as we know we can safely
    # read it until the end.
    if environ.get('wsgi.input_terminated'):
        return stream

    if content_length is None:
        return safe_fallback and BytesIO() or stream

    return LimitedStream(stream, content_length)


def _url_decode_impl(pair_iter, charset, include_empty, errors):
    for pair in pair_iter:
        if not pair:
            continue
        s = make_literal_wrapper(pair)
        equal = s('=')
        if equal in pair:
            key, value = pair.split(equal, 1)
        else:
            if not include_empty:
                continue
            key = pair
            value = s('')
        yield url_unquote_plus(key), url_unquote_plus(value, charset, errors)


def url_unquote_plus(s, charset='utf-8', errors='replace'):
    """URL decode a single string with the given `charset` and decode "+" to
    whitespace.
    Per default encoding errors are ignored.  If you want a different behavior
    you can set `errors` to ``'replace'`` or ``'strict'``.  In strict mode a
    :exc:`HTTPUnicodeError` is raised.
    :param s: The string to unquote.
    :param charset: the charset of the query string.  If set to `None`
                    no unicode decoding will take place.
    :param errors: The error handling for the `charset` decoding.
    """
    if isinstance(s, str):
        s = s.replace('+', ' ')
    else:
        s = s.replace(b'+', b' ')
    return url_unquote(s, charset, errors)


def url_unquote(string, charset='utf-8', errors='replace', unsafe=''):
    """URL decode a single string with a given encoding.  If the charset
    is set to `None` no unicode decoding is performed and raw bytes
    are returned.
    :param string: the string to unquote.
    :param charset: the charset of the query string.  If set to `None`
                    no unicode decoding will take place.
    :param errors: the error handling for the charset decoding.
    """
    rv = _unquote_to_bytes(string, unsafe)
    if charset is not None:
        rv = rv.decode(charset, errors)
    return rv


def _unquote_to_bytes(string, unsafe=''):
    if isinstance(string, str):
        string = string.encode('utf-8')
    if isinstance(unsafe, str):
        unsafe = unsafe.encode('utf-8')
    unsafe = frozenset(bytearray(unsafe))
    bits = iter(string.split(b'%'))
    result = bytearray(next(bits, b''))
    for item in bits:
        try:
            char = _hextobyte[item[:2]]
            if char in unsafe:
                raise KeyError()
            result.append(char)
            result.extend(item[2:])
        except KeyError:
            result.extend(b'%')
            result.extend(item)
    return bytes(result)

_hexdigits = '0123456789ABCDEFabcdef'

_hextobyte = dict(
    ((a + b).encode(), int(a + b, 16))
    for a in _hexdigits for b in _hexdigits
)
