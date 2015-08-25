import os
import re
import errno
import tempfile
from hashlib import md5
from time import time
import pickle


class BaseCache:
    """
    Base class for the cache systems.

    :param timeout: the default timeout(in seconds) that is used if no timeout
                    is specified on :meth: 'set'. A timeout of 0 indicates that
                    the cache never expires.
    """

    def __init__(self, timeout=300):
        self.timeout = timeout

    def get(self, key):
        """
        Look up key in the cache and return the value for it.

        :param key: The key to be looked up.
        :return: The value if it exists and is readable, else "None".
        """
        return None

    def delete(self, key):
        """
        Delete 'key' from the cache.

        :param key: The key to delete.
        :return: Whether the key existed and has been deleted.
        """
        return True

    def get_many(self, *keys):
        """
        Return a list of values for the given keys.

        :param keys: The function accepts multiple keys as positional arguments.
        :return: A list.
        """
        return list(map(self.get, keys))

    def get_dict(self, *keys):
        """
        Like :meth: 'get_many' but return a dict.

        :param keys: The function accepts multiple keys as positional arguments.
        :return: A dict.
        """
        return dict(zip(keys, self.get_many(*keys)))

    def set(self, key, value, timeout=None):
        """
        Add a new key/value pair the cache (overwrites value, if key already exists
        in the cache).

        :param key: The key to set.
        :param value: The value for the key.
        :param timeout: The cache timeout for the key (if not specified, it uses the
                        default timeout). A timeout of 0 indicates that the cache never
                        expires.
        :return: "True" if key has been updated, "False" for backend errors. Pickling errors,
                 However, will raise a subclass of "pickle.PickleError".
        """
        return True

    def add(self, key, value, timeout=None):
        """
        Works like :meth: 'Set' but does not overwrite the values of already existing keys.

        :param key: The key to set.
        :param value: The value for the key.
        :param timeout: The cache timeout for the key (if not specified, it uses the
                        default timeout). A timeout of 0 indicates that the cache never
                        expires.
        :return: Same as :meth: 'set', but also "False" for already existing keys.
        """
        return True

    def set_many(self, mapping, timeout=None):
        """
        Sets multiple keys and values from a mapping.

        :param mapping: a mapping with the keys/values to set.
        :param timeout: the cache timeout for the key (if not specified,
                        it uses the default timeout). A timeout of 0
                        indicates tht the cache never expires.
        :return: Whether all given keys have been set.
        :rtype: boolean
        """
        rv = True
        for key, value in mapping:
            if not self.set(key, value, timeout):
                rv = False
        return rv

    def delete_many(self, *keys):
        """
        Deletes multiple keys at once.

        :param keys: The function accepts multiple keys as positional
                     arguments.
        :return: Whether all given keys have been deleted.
        :rtype: boolean
        """
        return all(self.delete(key) for key in keys)

    def has(self, key):
        """
        Checks if a key exists in the cache without returning it. This is a
        cheap operation that bypasses loading the actual data on the backend.
        This method is optional and may not be implemented on all caches.

        :param key: the key to check
        """
        raise NotImplementedError(
            '%s doesn\'t have an efficient implementation of `has`. That '
            'means it is impossible to check whether a key exists without '
            'fully loading the key\'s data. Consider using `self.get` '
            'explicitly if you don\'t care about performance.'
        )

    def clear(self):
        """
        Clears the cache.  Keep in mind that not all caches support
        completely clearing the cache.

        :return: Whether the cache has been cleared.
        :rtype: boolean
        """
        return True

    def inc(self, key, delta=1):
        """
        Increments the value of a key by `delta`.  If the key does
        not yet exist it is initialized with `delta`.
        For supporting caches this is an atomic operation.

        :param key: The key to increment.
        :param delta: The delta to add.
        :return: The new value or ``None`` for backend errors.
        """
        value = (self.get(key) or 0) + delta
        return value if self.set(key, value) else None

    def dec(self, key, delta=1):
        """
        Decrements the value of a key by `delta`.  If the key does
        not yet exist it is initialized with `-delta`.
        For supporting caches this is an atomic operation.

        :param key: The key to increment.
        :param delta: The delta to subtract.
        :returns: The new value or `None` for backend errors.
        """
        value = (self.get(key) or 0) - delta
        return value if self.set(key, value) else None


class MiniCache(BaseCache):
    pass


class FileSystemCache(BaseCache):
    pass


class MemcachedCache(BaseCache):
    pass


class RedisCache(BaseCache):
    pass