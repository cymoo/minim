# Common Utilities
import sys
import os
import re
import json
from collections.abc import MutableMapping
from threading import RLock
import functools
from configparser import ConfigParser
from unicodedata import normalize

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
        :param cast_to: If defined, this callable is used to cast the value into a
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

    def load_from_config(self, filename):
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

    def load_from_object(self, obj):
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


def secure_filename(filename):
    """
    Pass it a filename and it will return a secure version of it.
    This filename can then safely be stored on a regular file system
    and passed to :func: "os.path.join".
    """
    if not isinstance(filename, str):
        filename = filename.decode('utf8')
    filename = normalize('NFKD', filename)
    # filename = filename.encode('ASCII', 'ignore').decode('ASCII')
    filename = os.path.basename(filename.replace('\\', os.path.sep))
    filename = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5_.\s]', '', filename).strip()
    filename = re.sub(r'[-\s]', '_', filename).strip('._')
    return filename


def import_from_string(import_name):
    """
    Imports an object based on a string. This is useful if you want
    to use import paths as endpoints or something similar. An import
    path can be specified either in dotted notation("collections.abc.MutableMapping")
    or with a colon as object delimiter("collections.abc:MutableMapping")

    :param import_name: the dotted name for the object to import.
    :return: imported object
    """

    import_name = str(import_name).replace(':', '.')
    try:
        try:
            __import__(import_name)
        except ImportError:
            if '.' not in import_name:
                raise
        else:
            return sys.modules[import_name]

        module_name, obj_name = import_name.rsplit('.', 1)
        try:
            module = __import__(module_name, None, None, [obj_name])
        except ImportError:
            # support importing modules not yet set up by the parent module
            # (or package for that matter)
            module = import_from_string(module_name)

        try:
            return getattr(module, obj_name)
        except AttributeError as e:
            raise ImportError(e)

    except ImportError:
        raise ImportError("cannot import module from %s." % import_name)


if __name__ == '__main__':

    class Foo:

        def __init__(self, environ):
            self.environ = environ
            self.config = ConfigDict(None)

        @DictProperty('environ', 'minim.app', read_only=False)
        def cookie(self):
            """test"""
            return 'fight'

        @lazy_attribute
        def bar(self):
            """bar"""
            return 'calm down'

        @cached_property
        def bar1(self):
            print('haha')
            return 'bar1'

    mypath = '哈哈.jpg'
    print(secure_filename(mypath))




