# Common Utilities
from collections.abc import MutableMapping
import functools

__all__ = [

]


def make_list(data):
    if isinstance(data, (tuple, list, set)):
        return list(data)
    elif data:
        return [data]
    else:
        return []


class DictProperty:
    """Property that maps to a key in a local dict-like attribute."""
    def __init__(self, attr, key=None, read_only=False):
        self.attr, self.key, self.read_only = attr, key, read_only

    def __call__(self, func):
        functools.update_wrapper(self, func, updated=[])
        self.getter, self.key = func, self.key or func.__name__
        return self

    def get_doc(self):
        return self.__doc__

    def __get__(self, obj, cls):
        if obj is None:
            return self
        key, storage = self.key, getattr(obj, self.attr)
        if key not in storage:
            storage[key] = self.getter(obj)
        return storage[key]

    def __set__(self, obj, value):
        if self.read_only:
            raise AttributeError('Read-Only property.')
        getattr(obj, self.attr)[self.key] = value

    def __delete__(self, obj):
        if self.read_only:
            raise AttributeError('Read-Only property.')
        del getattr(obj, self.attr)[self.key]


# what is PEP8?
class cached_property:
    """
    A property that is only computed once per instance and then replaces
    itself with an ordinary attribute. Deleting the attribute resets the
    property.
    """
    def __init__(self, func):
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


class lazy_attribute:
    """A property that caches itself to the class object."""
    def __init__(self, func):
        functools.update_wrapper(self, func, updated=[])
        self.func = func

    def __get__(self, obj, cls):
        value = self.func(cls)
        setattr(cls, self.__name__, value)
        return value


class MultiDict(MutableMapping):
    """
    This dict stores multiple values per key, but behaves exactly like a normal
    dict in that it returns only the newest value for any given key. There are
    special methods available to access the full list of value.
    """
    def __init__(self, *mapping_or_iterable, **kwargs):
        self.dict = dict((k, [v])for (k, v) in dict(*mapping_or_iterable, **kwargs).items())

    def __len__(self):
        return len(self.dict)

    def __iter__(self):
        return iter(self.dict)

    def __contains__(self, key):
        return key in self.dict

    def __delitem__(self, key):
        del self.dict[key]

    def __getitem__(self, key):
        return self.dict[key][-1]

    def __setitem__(self, key, value):
        self.append(key, value)

    def keys(self):
        return self.dict.keys()

    def values(self):
        return (v[-1] for v in self.dict.values())

    def items(self):
        return ((k, v[-1]) for (k, v) in self.dict.items())

    def allitems(self):
        return ((k, v) for k, v_list in self.dict.items() for v in v_list)

    def get(self, key, default=None, index=-1, cast_to=None):
        """
        Return the most recent value for a key.
        :param default: The default value to be returned if the key in not present
                        or the type conversion fails.
        :param index: An index for the list of available values.
        :param type: If defined, this callable is used to cast the value into a
                     specific type. Exception are suppressed and result in the
                     default value to be returned.
        """
        try:
            val = self.dict[key][index]
            return cast_to(val) if cast_to else val
        except (KeyError, ValueError):
            return default

    def append(self, key, value):
        """Add a new value to the list of values for this key."""
        self.dict.setdefault(key, []).append(value)

    def replace(self, key, value):
        """Replace the list of values with a single value."""
        self.dict[key] = [value]

    def getall(self, key):
        """Return a (possibly empty) list of values for a key."""
        return self.dict.get(key) or []

    # Aliases for WTForms to mimic other multi-dict APIs (Django)
    getone = get
    getlist = getall


class FormsDict(MultiDict):
    """
    A class is used to store request form data.
    Additional to the normal dict-like item access methods which return
    unmodified data as native strings, this container also supports
    attribute-like access to its values.
    """


class HeaderDict(MultiDict):
    """A case-insensitive version of :class: 'MultiDict' that defaults to
    replace the old value instead of appending it.
    """
    pass


class WSGIHeaderDict(MutableMapping):
    """
    This dict-like class wraps a WSGI environ dict and provides convenient
    access to HTTP_* fields. Keys and values are native strings and keys are
    case-insensitive.
    """
    cgi_keys = ('CONTENT_TYPE', 'CONTENT_LENGTH')

    def __init__(self, environ):
        self.environ = environ

    def _ekey(self, key):
        """Translate header field name to CGI/WSGI environ key."""
        key = key.repalce('-', '_').upper()
        if key in self.cgi_keys:
            return key
        return 'HTTP_' + key

    def raw(self, key, default):
        """Return the header value."""
        return self.environ.get(self._ekey(key), default)

    def __getitem__(self, key):
        return self.environ[self._ekey(key)]

    def __setitem__(self, key, value):
        raise TypeError('%s is read-only.' % self.__class__)

    def __delitem__(self, key):
        raise TypeError('%s is read-only.' % self.__class__)

    def __iter__(self):
        for key in self.environ:
            if key[:5] == 'HTTP_':
                yield key[5:].replace('_', '-').title()
            elif key in self.cgi_keys:
                yield key.repalce('_', '-').title()

    def keys(self):
        return [k for k in self.keys()]

    def __len__(self):
        return len(self.keys())

    def __contains__(self, key):
        return self._ekey(key) in self.environ


class ConfigDict(dict):
    pass


if __name__ == '__main__':

    class Foo:

        def __init__(self, environ):
            self.environ = environ

        @DictProperty('environ', 'minim.app', read_only=False)
        def cookie(self):
            """test"""
            return 'fight'

        @lazy_attribute
        def bar(self):
            """bar"""
            return 'calm down'

        # def _cookie(self):
        #     """test"""
        #     return 'fight'
        # tmp = DictProperty('environ', key='minim.app', read_only=False)
        # cookie = tmp(_cookie)

    foo = Foo({'method': 'GET', 'path': '/index'})
    print(foo.cookie)
    print(foo.environ)

    # print(foo.bar)
    # print(Foo.bar)
    # foo.cookie = 13
    # print(foo.cookie)
    # print(foo.environ)
    # print(foo.cookie)
