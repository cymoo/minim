"""
minim.structures
~~~~~~~~~~~~~~~~

This module provides main data structures that power Minim.
"""

import os
import json
from threading import RLock
from configparser import ConfigParser
from copy import deepcopy
from io import BytesIO
from utils import import_from_string


__all__ = [
    'DictProperty',
    'cached_property',
    'lazy_attribute',
    'MultiDict',
    'FormsDict',
    'HeadersDict',
    'ConfigDict',
]


class DictProperty:
    """Property that maps to a key in a local dict-like attribute."""
    def __init__(self, attr, key=None, read_only=True):
        self.attr, self.key, self.read_only = attr, key, read_only
        # needs thread safe?
        self.lock = RLock()

    def __call__(self, func):
        # functools.update_wrapper(self, func, updated=[])
        self.__doc__ = func.__doc__
        self.__module = func.__module__
        self.__name__ = func.__name__
        self.func, self.key = func, self.key or func.__name__
        return self

    def __get__(self, obj, cls):
        if obj is None:
            return self
        key, storage = self.key, getattr(obj, self.attr)
        if key not in storage:
            storage[key] = self.func(obj)
        return storage[key]

    def __set__(self, obj, value):
        if self.read_only:
            raise AttributeError('Read-Only property.')
        getattr(obj, self.attr)[self.key] = value

    def __delete__(self, obj):
        if self.read_only:
            raise AttributeError('Read-Only property.')
        del getattr(obj, self.attr)[self.key]


class environ_property(DictProperty):
    """A subclass of :class:'DictProperty'"""


class cached_property:
    """
    A decorator that converts a function into a lazy property.
    The function is wrapped is called the first time to retrieve
    the result and then that calculated result is used the next time
    you access the value.
    The class has to have a '__dict__' in order for this property to work.

    It has a lock for thread safety.
    """
    def __init__(self, func, name=None, doc=None):
        self.__name__ = name or func.__name__
        self.__module__ = func.__module__
        self.__doc__ = doc or func.__doc__
        self.func = func
        self.lock = RLock()

    def __get__(self, obj, cls):
        if obj is None:
            return self
        with self.lock:
            value = obj.__dict__.get(self.__name__, None)
            if value is None:
                value = self.func(obj)
                obj.__dict__[self.__name__] = value
            return value

    def __set__(self, obj, value):
        obj.__dict__[self.__name__] = value


class lazy_attribute:
    """A property that caches itself to the class object."""
    def __init__(self, func, name=None, doc=None):
        # functools.update_wrapper(self, func, updated=[])
        self.__name__ = name or func.__name__
        self.__module__ = func.__module__
        self.__doc__ = doc or func.__doc__
        self.func = func

    def __get__(self, obj, cls):
        value = self.func(cls)
        setattr(cls, self.__name__, value)
        return value


class MultiDict(dict):
    """
    This dict stores multiple values per key, but behaves exactly like a normal
    dict in that it returns only the newest value for any given key. There are
    special methods available to access the full list of value.
    """
    def __init__(self, mapping=None):
        if isinstance(mapping, MultiDict):
            super().__init__((k, l[:])for k, l in mapping.lists())
        elif isinstance(mapping, dict):
            tmp = {}
            for key, value in mapping.items():
                if isinstance(value, (tuple, list)):
                    value = list(value)
                else:
                    value = [value]
                tmp[key] = value
            super().__init__(tmp)
        else:
            tmp = {}
            for key, value in mapping or ():
                tmp.setdefault(key, []).append(value)
            super().__init__(tmp)

    def __getstate__(self):
        return dict(self.lists())

    def __setstate__(self, value):
        dict.clear(self)
        super().update(value)

    def __getitem__(self, key):
        """
        Return the first data value for this key;
        raises KeyError if not found.
        """
        if key in self:
            return super().__getitem__(key)[0]
        raise KeyError('key: %s does not exists.' % key)

    def __setitem__(self, key, value):
        """
        Like :meth:'add' but removes an existing key first.
        """
        super().__setitem__(key, [value])

    def get(self, key, default=None, type=None):
        """
        Return the default value if the requested data does not exist.
        If 'type' is provided and is a callable it should convert the value.
        Return it or raise a :exc:'ValueError' if that is not possible.
        In this case the function will return the default as if the value was
        not found.

        :param key:
        :param default:
        :param type: A callable that is used to cast the value in the :class:
        'MultiDict'. if a :exc: 'ValueError' is raised by this callable the
        default value is returned.
        """
        try:
            value = self[key]
            if type is not None:
                value = type(value)
        except (KeyError, ValueError):
            value = default
        return value

    def add(self, key, value):
        """
        Adds a new value for the key.
        """
        super().setdefault(key, []).append(value)

    def getlist(self, key, type=None):
        """
        Return the list of items for a given key. If that key does not exist,
        the return value will be an empty list. Just as 'get', 'getlist' accepts
        a 'type' parameter. All items will be converted with the callable defined here.

        :param key:
        :param type: A callable that is used to cast the value in the :class:
                    'MultiDict'. If a :exec: 'ValueError' is raised, the value
                    will be removed from the list.
        :return: a :class: 'list' of all the values for the key.
        """
        try:
            values = super().__getitem__(key)
        except KeyError:
            return []
        if type is None:
            return list(values)
        result = []
        for item in values:
            try:
                result.append(type(item))
            except ValueError:
                pass
            return result

    def setlist(self, key, new_list):
        """
        Remove the old values for a key and add new ones. Note that the list you
        pass the values in will be shallow-copied before it is inserted in the dict.

        :param key:
        :param new_list: An iterable with the new values for the key. Old values are
                        removed first.
        """
        super().__setitem__(key, list(new_list))

    def setdefault(self, key, default=None):
        """
        Returns the values for the key if it is in the dict, otherwise it returns
        'default' and sets the value for 'key'.

        :param key:
        :param default: The default value to be returned if the key is not in the dict.
                        If not further specified it is 'None'
        """

        if key not in self:
            self[key] = default
        else:
            default = self[key]
        return default

    def setlistdefault(self, key, default_list=None):
        """
        Like 'setdefault' but sets multiple values. The list returned is not a copy,
        but the list that is actually used internally. This means that you can put
        new values into the dict by appending items to the list.

        :param key:
        :param default_list: An iterable of default values. It is either copied
                             (in case it was a list) or converted into a list
                             before returned.
        :return: a :class:'list'
        """
        if key not in self:
            default_list = list(default_list or ())
            super().__setitem__(key, default_list)
        else:
            default_list = super().__getitem__(key)
        return default_list

    def items(self, multi=True):
        """
        Return an iterator of "(key, values)" pairs.

        :param multi: If set to 'True' the iterator returned will have a pair
                      for each value of each key. Otherwise it will only contains
                      pairs for the first value of each key.
        """
        for key, values in super().items():
            if multi:
                for value in values:
                    yield key, value
            else:
                yield key, values[0]

    def lists(self):
        """
        Return a list of "(key, values)" pairs where values is the list of all
        values associated with the key.
        """
        for key, values in super().items():
            yield key, list(values)

    def keys(self):
        return super().keys()

    __iter__ = keys

    def values(self):
        """Returns an iterator for the first value on every key's value list."""
        for values in super().values():
            yield values[0]

    def listvalues(self):
        """
        Return an iterator of all values associated with a key.
        """
        return super().values()

    def copy(self):
        """Return a shallow copy of this object."""
        return self.__class__(self)

    def deepcopy(self, memo=None):
        """Return a deep copy of this object."""
        return self.__class__(deepcopy(self.to_dict(flat=False), memo))

    def to_dict(self, flat=False):
        """
        Return the contents as regular dict. If 'flat' is 'True' the returned
        dict will only have the first present, if 'flat' is 'False' all values
        will be returned as lists.

        :param flat: If set to 'False' the dict returned will have lists with
                    all values in it. otherwise it will only contain the first
                    value for each key.
        :return: a :class:'dict'.
        """

        if flat:
            return dict(self.items())
        return dict(self.lists())

    @staticmethod
    def _iter_multi_items(mapping):
        """
        Iterates over the items of a mapping yielding keys and values
        without dropping any from more complex structures.

        :param mapping:
        :return:
        """
        if isinstance(mapping, MultiDict):
            for item in mapping.items(multi=True):
                yield item
        elif isinstance(mapping, dict):
            for key, value in mapping.items():
                if isinstance(value, (tuple, list)):
                    for v in value:
                        yield key, v
                else:
                    yield key, value
        else:
            for item in mapping:
                yield item

    def update(self, other_dict):
        """
        Update() extends rather than replaces existing key list.
        """
        for key, value in self._iter_multi_items(other_dict):
            self.add(key, value)

    def pop(self, key, default=None):
        """
        Pop the first item for a list on the dict. Afterwards the key is removed
        from the dict, so additional values are discarded.

        :param key:
        :param default: If provided the value to return if the key was not in the dict.
        """

        try:
            return super().pop(key)[0]
        except KeyError:
            if default is not None:
                return default
            raise KeyError('key: %s does not exist.' % key)

    def popitem(self):
        """
        Pop an item from the dict.
        """
        try:
            item = super().popitem()
            return item[0], item[1][0]
        except KeyError:
            raise KeyError('The dict is empty.')

    def poplist(self, key):
        """
        Pop the list for a key from the dict. If the key is not in the dict
        an empty list is returned.
        """
        return super().pop(key, [])

    def popitemlist(self):
        """
        Pop a "(key, list)" tuple from the dict.
        """
        try:
            return super().popitem()
        except KeyError:
            raise KeyError('The dict is empty.')

    def __copy__(self):
        return self.copy()

    def __deepcopy(self, memo=None):
        return self.deepcopy(memo=memo)

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, list(self.items(multi=True)))


class FormsDict(MultiDict):
    """
    A class is used to store request form data.
    Additional to the normal dict-like item access methods which return
    unmodified data as native strings, this container also supports
    attribute-like access to its values.
    """

    def __getattr__(self, name):
        value = self.getlist(name)
        return value if len(value) > 1 else value[0]


class HeadersDict:
    """
    An object that stores some headers.  It has a dict-like interface
    but is ordered and can store the same keys multiple times.
    This data structure is useful if you want a nicer way to handle WSGI
    headers which are stored as tuples in a list.

    To create a new :class:`HeadersDict` object pass it a list or dict of headers
    which are used as default values. This does not reuse the list passed
    to the constructor for internal usage.

    :param defaults: The list of default values for the :class:`HeadersDict`.
    """

    def __init__(self, defaults=None):
        self._list = []
        if defaults is not None:
            if isinstance(defaults, (list, HeadersDict)):
                self._list.extend(defaults)
            else:
                self.extend(defaults)

    def __getitem__(self, key):
        if not isinstance(key, str):
            raise KeyError('key: %s should be str.' % key)
        ikey = key.lower()
        for k, v in self._list:
            if k.lower() == ikey:
                return v
        raise KeyError('key: %s does not exists.' % key)

    def __eq__(self, other):
        return other.__class__ is self.__class__ and \
            set(other._list) == set(self._list)

    def __ne__(self, other):
        return not self.__eq__(other)

    def get(self, key, default=None, type=None):
        """
        Return the default value if the requested data doesn't exist.
        If `type` is provided and is a callable it should convert the value,
        return it or raise a :exc:`ValueError` if that is not possible.  In
        this case the function will return the default as if the value was not
        found:

        :param key: The key to be looked up.
        :param default: The default value to be returned if the key can't
                        be looked up.  If not further specified `None` is
                        returned.
        :param type: A callable that is used to cast the value.
                     If a :exc:`ValueError` is raised by this callable
                     the default value is returned.
        """
        try:
            rv = self.__getitem__(key)
        except KeyError:
            return default
        if type is None:
            return rv
        try:
            return type(rv)
        except ValueError:
            return default

    def getlist(self, key, type=None):
        """
        Return the list of items for a given key. If that key is not in the
        class, the return value will be an empty list.  Just as :meth:`get`
        :meth:`getlist` accepts a `type` parameter.  All items will
        be converted with the callable defined there.

        :param key: The key to be looked up.
        :param type: A callable that is used to cast the value in the
                     :class:`HeadersDict`.  If a :exc:`ValueError` is raised
                     by this callable the value will be removed from the list.
        :return: a :class:`list` of all the values for the key.
        """
        ikey = key.lower()
        result = []
        for k, v in self:
            if k.lower() == ikey:
                if type is not None:
                    try:
                        v = type(v)
                    except ValueError:
                        continue
                result.append(v)
        return result

    def get_all(self, name):
        """
        Return a list of all the values for the named field.
        This method is compatible with the :mod:`wsgiref`
        :meth:`~wsgiref.headers.Headers.get_all` method.
        """
        return self.getlist(name)

    def items(self, lower=True):
        for key, value in self:
            if lower:
                key = key.lower()
            yield key, value

    def keys(self, lower=True):
        for key, _ in self.items():
            if lower:
                key = key.lower()
            yield key

    def values(self):
        for _, value in self.items():
            yield value

    def extend(self, iterable):
        """
        Extend the headers with a dict or an iterable yielding keys and
        values.
        """
        if isinstance(iterable, dict):
            for key, value in iterable.items():
                if isinstance(value, (tuple, list)):
                    for v in value:
                        self.add(key, v)
                else:
                    self.add(key, value)
        else:
            for key, value in iterable:
                self.add(key, value)

    def __delitem__(self, key, index_operation=True):
        if index_operation and isinstance(key, (int, slice)):
            del self._list[key]
            return
        key = key.lower()
        new = []
        for k, v in self._list:
            if k.lower() != key:
                new.append((k, v))
        self._list[:] = new

    def remove(self, key):
        """
        Remove a key.

        :param key: The key to be removed.
        """
        return self.__delitem__(key, index_operation=False)

    def pop(self, key=None, default=None):
        """
        Removes and returns a key or index.

        :param key: The key to be popped.  If this is an integer the item at
                    that position is removed, if it's a string the value for
                    that key is.  If the key is omitted or `None` the last
                    item is removed.
        :return: an item.
        """
        if key is None:
            return self._list.pop()
        if isinstance(key, int):
            return self._list.pop(key)
        try:
            value = self[key]
            self.remove(key)
        except KeyError:
            if default is not None:
                return default
            raise KeyError('key: %s does not exists.' % key)
        return value

    # An alias for :meth:`pop`.
    popitem = pop

    def __contains__(self, key):
        """Check if a key is present."""
        try:
            self.__getitem__(key)
        except KeyError:
            return False
        return True

    has_key = __contains__

    def __iter__(self):
        """Yield ``(key, value)`` tuples."""
        return iter(self._list)

    def __len__(self):
        return len(self._list)

    @staticmethod
    def _options_header_vkw(header, options):
        """
        :param header: the header to dump
        :param options: a dict of options to append.
        """
        # Replace '_' in key to '-'
        options = dict((k.replace('_', '-'), v) for k, v in options.items())

        segments = []
        if header is not None:
            segments.append(header)
        for key, value in options.items():
            if value is None:
                segments.append(key)
            else:
                segments.append('%s=%s' % (key, value))
        return '; '.join(segments)

    def add(self, _key, _value, **kw):
        """Add a new header tuple to the list.

        Keyword arguments can specify additional parameters for the header
        value, with underscores converted to dashes.
        """
        if kw:
            _value = self._options_header_vkw(_value, kw)
        self._validate_value(_value)
        self._list.append((_key.title(), _value))

    @staticmethod
    def _validate_value(value):
        if not isinstance(value, str):
            raise TypeError('Value should be str.')
        if '\n' in value or '\r' in value:
            raise ValueError('Detected newline in header value. This is '
                             'a potential security problem')

    # An alias for :meth:`add` for compatibility with the :mod:`wsgiref`
    # :meth:`~wsgiref.headers.Headers.add_header` method.
    add_header = add

    def clear(self):
        """Clears all headers."""
        del self._list[:]

    def set(self, _key, _value, **kw):
        """Remove all header tuples for `key` and add a new one.  The newly
        added key either appears at the end of the list if there was no
        entry or replaces the first one.
        Keyword arguments can specify additional parameters for the header
        value, with underscores converted to dashes.
        :meth:`set` accepts the same arguments as :meth:`add`.

        :param key: The key to be inserted.
        :param value: The value to be inserted.
        """
        if kw:
            _value = self._options_header_vkw(_value, kw)
        self._validate_value(_value)
        if not self._list:
            self._list.append((_key.title(), _value))
            return
        list_iter = iter(self._list)
        ikey = _key.lower()
        for idx, (old_key, old_value) in enumerate(list_iter):
            if old_key.lower() == ikey:
                # replace first appearance
                self._list[idx] = (_key.title(), _value)
                break
        else:
            self._list.append((_key.title(), _value))
            return
        self._list[idx + 1:] = [t for t in list_iter if t[0].lower() != ikey]

    def setdefault(self, key, default):
        """Returns the value for the key if it is in the dict, otherwise it
        returns `default` and sets that value for `key`.

        :param key: The key to be looked up.
        :param default: The default value to be returned if the key is not
                        in the dict.  If not further specified it's `None`.
        """
        if key in self:
            return self[key]
        self.set(key, default)
        return default

    def __setitem__(self, key, value):
        """Like :meth:`set` but also supports index/slice based setting."""
        if isinstance(key, (slice, int)):
            if isinstance(key, int):
                value = [value]
            value = [(k, v) for (k, v) in value]
            [self._validate_value(v) for (k, v) in value]
            if isinstance(key, int):
                self._list[key] = value[0]
            else:
                self._list[key] = value
        else:
            self.set(key, value)

    def to_wsgi_list(self):
        """Convert the headers into a list suitable for WSGI.
        The values are unicode strings in Python 3 for the WSGI server to encode.

        :return: list
        """
        return list(self)

    def copy(self):
        return self.__class__(self._list)

    def __copy__(self):
        return self.copy()

    def __str__(self):
        """Returns formatted headers suitable for HTTP transmission."""
        string = []
        for key, value in self.to_wsgi_list():
            string.append('%s: %s' % (key, value))
        string.append('\r\n')
        return '\r\n'.join(string)

    def __repr__(self):
        return '%s(%r)' % (
            self.__class__.__name__,
            list(self)
        )


class ConfigDict(dict):

    def __init__(self, root_path, defaults=None):
        super().__init__(defaults or {})
        self.root_path = root_path

    def load_from_dict(self, source, namespace=''):
        """Load values from a dict. Nesting can be used to represent namespaces."""
        for key, value in source.items():
            if isinstance(key, str):
                nskey = (namespace + '.' + key).strip('.')
                if isinstance(value, dict):
                    self.load_from_dict(value, namespace=nskey)
                else:
                    self[nskey] = value
            else:
                raise TypeError("<class 'str'> expected, but type of %s is %s." % (key, type(key)))
        return self

    def load_from_json(self, filename):
        """
        Load values from a json file.
        This function behaves as if the json object was a dictionary and
        passed to the "load_from_dict" function.
        """
        filename = os.path.join(self.root_path, filename)
        try:
            with open(filename) as json_file:
                obj = json.loads(json_file.read())
        except IOError:
            raise IOError("Unable to load JSON file (%s)." % filename)
        return self.load_from_dict(obj)

    def load_from_ini(self, filename):
        """
        Load values from an "*.ini" config file.
        If the config files contains sections, their names are used as namespaces for
        the values within. The two special sections "DEFAULT" and "minim" refer to
        the root namespace (no prefix)
        """
        conf = ConfigParser()
        filename = os.path.join(self.root_path, filename)
        conf.read(filename)
        for section in conf.sections():
            for key, value in conf.items(section):
                if section not in ('DEFAULT', 'minim'):
                    key = section + '.' + key
                section[key] = value
        return self

    def load_from_class(self, obj):
        """
        Load values from a class or an instance.
        An object can be of one of the following two types:
          1. a string: in this case the object with that name will be imported
          2. an actual object reference: that object is used directed
        Objects are usually either modules or classes.
        Just the uppercase variables in that object are stored in that config.
        """
        if isinstance(obj, str):
            obj = import_from_string(obj)
        for key in dir(obj):
            if key.isupper():
                self[key] = getattr(obj, key)


class FileStorage:
    """
    The :class: 'FileStorage' class is a thin wrapper over incoming files.
    It is used by the request object to represent uploaded files. All the
    attributes of the wrapper stream are proxied by the file storage so it's
    possible to do "storage.read()" instead of the long form "storage.stream.read()".
    """
    def __init__(self, stream=None, filename=None, name=None,
                 content_type=None, content_length=None,
                 headers=None):
        self.name = name
        self.stream = stream or BytesIO()

        # If no filename is provided, we can attempt to get the filename from the
        # stream object passed. There we have to be careful to skip things like
        # <fdopen>, <stderr> etc. Python marks these special filenames with angular
        # brackets.

        if filename is None:
            filename = getattr(stream, 'name', None)
            s = self._make_literal_wrapper(filename)
            if filename and filename[0] == s('<') and filename[-1] == s('>'):
                filename = None

        # On Python3, we want to make sure the filename is always unicode.
        # This might not be if the name attribute is bytes due to the file
        # being opened from the bytes API.
            if isinstance(filename, bytes):
                filename = filename.decode('utf-8', 'replace')

        self.filename = filename
        if headers is None:
            headers = HeadersDict()
        self.headers = headers

        if content_type is not None:
            headers['Content-Type'] = content_type

        if content_length is not None:
            # ?
            headers['Content-Length'] = str(content_length)

    @staticmethod
    def _make_literal_wrapper(ref):
        if isinstance(ref, str):
            return lambda x: x
        return lambda x: x.encode('latin1')

    def _parse_content_type(self):
        if not hasattr(self, '_parsed_content_type'):
            self._parsed_content_type = None  # ...

    @property
    def content_type(self):
        """The content-type sent in the header. Usually not available"""
        return self.headers.get('content-type')

    @property
    def content_length(self):
        """The content-length sent in the header. Usually not available"""
        return int(self.headers.get('content-length') or 0)

    @property
    def mimetype(self):
        """
        Like :attr: 'content_type', but without parameters (eg, without charset,
        type etc.) and always lowercase. For example if the content type is 'text/html;
        charset=utf-8' the mimetype would be 'text/html'.
        """
        self._parse_content_type()
        return self._parsed_content_type[0].lower()

    @property
    def mimetype_params(self):
        """
        The mimetype parameters as dict. For example if the content type is
        "text/html; charset=utf-8" the params would be "{'charset': 'utf-8'}".
        """
        self._parse_content_type()
        return self._parsed_content_type[1]

    def save(self, dst, buffer_size=16384):
        """
        Save the file to a destination path or file object.
        If the destination is a file object you have to close it yourself
        after the call. The buffer size is the number of bytes held in memory
        during the copy process. It defaults to 16KB.

        For secure file saving also have a look at: func: 'secure_filename'.

        :param dst: a filename or open file object the uploaded file is saved to
        :param buffer_size: the size of the buffer. This works the same as the
                            'length' parameter of :func: 'shutil.copyfileobj'
        """
        from shutil import copyfileobj
        close_dst = False
        if isinstance(dst, str):
            dst = open(dst, 'wb')
            close_dst = True
        try:
            copyfileobj(self.stream, dst, buffer_size)
        finally:
            if close_dst:
                dst.close()

    def close(self):
        """Close the underlying file if possible."""
        try:
            self.stream.close()
        except Exception:
            pass

    def __nonzero__(self):
        return bool(self.filename)

    __bool__ = __nonzero__

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def __iter__(self):
        return iter(self.readline, '')

    def __repr__(self):
        return '<%s: %r (%r)>' % (
            self.__class__.__name__,
            self.filename,
            self.content_type
        )
if __name__ == '__main__':
    # h = HeadersDict({'CONTENT-TYPE': 'text/html; charset=UTF-8', 'CONNECTION': 'keep-alive'})
    # d = {'CONTENT-TYPE': 'text/html; charset=UTF-8', 'CONNECTION': 'keep-alive'}
    # l1 = [('CONTENT-TYPE', 'text/html; charset=UTF-8'), ('CONNECTION', 'keep-alive')]
    # h1 = HeadersDict(d)
    # h2 = HeadersDict(l1)
    # # print(h1.to_wsgi_list())
    # print(h2.to_wsgi_list())
    # h2.add_header('powered-by', 'minim', haha='yaya')
    # print(h2.to_wsgi_list())
    # h2.set('powered-by', 'cymoo')
    # print(h2.to_wsgi_list())
    # h2['cache'] = 'forever'
    # print(h2.to_wsgi_list())
    # h2.add_header('powered-by', 'colleen')
    # print(h2.to_wsgi_list())





    pairs = {'uname': ['sexmaker'], 'hobbits': ['girl', 'game', 'book'], 'sex': ['female'], 'motto': ['世界是我的表象']}
    m = MultiDict(pairs)
    # m = FormsDict(pairs)
    print(m)

    mm = MultiDict(m)
    print(mm.to_dict())
    #
    # print(m.getlist('hobbits'))
    # print(m.hobbits)
    # value = 'abc'
    # print(quote_header_value(value))