# coding=utf-8
"""
minim.local
~~~~~~~~~~~

This module implements context-local objects.

"""
from request import Request
from response import Response
from threading import local
from threading import get_ident


class _Local(local):
    """An interface for registering request and response objects.

    Rather than have a separate "thread local" object for tht request and the response,
    this class works as a single thread local container for both objects (and any others
    which you wish to define). In this way, we can easily dump those objects when we stop
    /start a new HTTP conversation, yet still refer to them as module-level globals in a
    thread-safe way.
    """
    #: The request and response object for the current thread. In the main thread, and any threads which
    #: are not receiving HTTP requests, this is None.
    request = Request()
    response = Response()

    def load(self, req, res):
        self.request = req
        self.response = res

    def clear(self):
        """Remove all attributes of self."""
        self.__dict__.clear()

_local = _Local()


class _ThreadLocalProxy:

    __slots__ = ['__attrname__', '__dict__']

    def __init__(self, attrname):
        self.__attrname__ = attrname

    def __getattr__(self, name):
        child = getattr(_local, self.__attrname__)
        return getattr(child, name)

    def __setattr__(self, name, value):
        if name in ("__attrname__", ):
            object.__setattr__(self, name, value)
        else:
            child = getattr(_local, self.__attrname__)
            setattr(child, name, value)

    def __delattr__(self, name):
        child = getattr(_local, self.__attrname__)
        delattr(child, name)

    def _get_dict(self):
        child = getattr(_local, self.__attrname__)
        d = child.__class__.__dict__.copy()
        d.update(child.__dict__)
        return d
    __dict__ = property(_get_dict)

    def __getitem__(self, key):
        child = getattr(_local, self.__attrname__)
        return child[key]

    def __setitem__(self, key, value):
        child = getattr(_local, self.__attrname__)
        child[key] = value

    def __delitem__(self, key):
        child = getattr(_local, self.__attrname__)
        del child[key]

    def __contains__(self, key):
        child = getattr(_local, self.__attrname__)
        return key in child

    def __len__(self):
        child = getattr(_local, self.__attrname__)
        return len(child)

    def __nonzero__(self):
        child = getattr(_local, self.__attrname__)
        return bool(child)

    __bool__ = __nonzero__


request = _ThreadLocalProxy('request')
response = _ThreadLocalProxy('response')
