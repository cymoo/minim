# coding=utf-8

from http.cookies import SimpleCookie
import time
from datetime import timedelta, date, datetime
from structures import HeadersDict
from httputil import RESPONSE_STATUSES


class Response:
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

