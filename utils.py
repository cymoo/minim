"""
minim.utils
~~~~~~~~~~~

...

"""
import sys
import os
import re
import threading
from unicodedata import normalize


__all__ = [
    'make_list',
    'DictProperty',
    'cached_property',
    'lazy_attribute',
    'secure_filename',
    'safe_bytes',
    'safe_str',
    'send_mail',
    'FileStorage',
    'Profile',
    'limit_time',
    'find_key',
    'prettify_date',
    '_EmailMessage'
]


def make_list(data):
    if isinstance(data, (tuple, list, set)):
        return list(data)
    elif data:
        return [data]
    else:
        return []


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


def safe_str(obj, encoding='utf-8'):
    """
    Converts any given object to unicode string.

    :param obj:
    :param encoding:
    :return:
    """
    t = type(obj)
    if t is str:
        return obj
    elif t is bytes:
        return obj.decode(encoding)
    elif t in [int, float, bool]:
        return str(obj)
    # elif hasattr(obj, '__unicode__') or isinstance(obj, unicode):
    #     return unicode(obj)
    else:
        raise TypeError('cannot do safe_str to %s', obj)


def safe_bytes(obj, encoding='utf-8'):
    """
    Converts any given object to utf-8 encoded string.

    :param obj:
    :param encoding:
    :return:
    """
    if isinstance(obj, str):
        return obj.encode(encoding)
    elif isinstance(obj, bytes):
        return obj
    elif hasattr(obj, '__next__'):  # iterator
        return map(safe_bytes, obj)
    # consider convert list, tuple, dict to bytes?
    else:
        raise TypeError('cannot do safe_bytes to %s', obj)


def find_key(mapping, element):
    """

    :param dictionary:
    :param value:
    :return:
    """
    keys = []
    for (key, value) in mapping.items():
        if element is value:
            keys.append(key)
    return keys


def prettify_date(then, now=None, lan='en'):
    """
    Converts a (UTC) datetime object to a nice string representation.
    Should be moved to template module as a filter?
    """
    pass


def limit_time(timeout):
    """
    A decorator to limit a function to 'timeout' seconds, raising 'TimeoutError"
    if it takes longer.

    Note: The function is not stopped after 'timeout' seconds but continues
    executing in a separate thread. (There seems to be no way to kill a thread.)
    """
    def _dec(function):
        def _wrapper(*args, **kw):
            class Dispatch(threading.Thread):
                def __init__(self):
                    threading.Thread.__init__(self)
                    self.result = None
                    self.error = None

                    self.setDaemon(True)
                    self.start()

                def run(self):
                    try:
                        self.result = function(*args, **kw)
                    except:
                        self.error = sys.exc_info()

            c = Dispatch()
            c.join(timeout)
            if c.isAlive():
                raise TimeoutError('took too long')
            if c.error:
                raise (c.error[0], c.error[1])
            return c.result
        return _wrapper
    return _dec


class Profile:
    """
    Profiles 'func' and returns a tuple containing its output and a string
    with human-readable profiling information.

    from webpy.utils
    """
    pass


def send_mail(from_address, to_address, subject, message, headers=None, **kw):
    pass


class _EmailMessage:
    pass
