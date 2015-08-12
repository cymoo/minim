import os
import threading
import time
import re
import datetime
import random
import base64
from copy import deepcopy
import pickle
from hashlib import sha1

from web import HttpError, Dict, request, response


__all__ = [
    'Session', 'SessionExpired',
    'Store', 'DiskStore', 'DBStore'
]

### config related ####

# session_parameters = Dict({
#     'cookie_name': 'session_id',
#     'cookie_domain': None,
#     'cookie_path': None,
#     'timeout': 24*60*60,
#     'ignore_expiry': True,
#     'ignore_change_ip': True,
#     'secret_key': 'do not go gentle into that good night.',
#     'expired_message': 'Session expired',
#     'httponly': True,
#     'secure': False
# })


class SessionExpired(HttpError):
    def __init__(self, msg):
        super().__init__(200, msg=msg)


class Session(threading.local):
    cookie_name = 'session_id'
    cookie_domain = None
    cookie_path = None
    timeout = 24*60*60
    secret_key = 'do not go gentle into that good night.'
    expired_message = 'Session expired'
    httponly = True
    secure = False

    def __init__(self, app, store, initializer=None):
        super().__init__()
        self.store = store
        self._initializer = initializer
        self._last_clean_time = 0
        self._data = Dict()

        # what is for?
        if app:
            app.add_processor(self._processor)

    def __contains__(self, name):
        return name in self._data

    def __getattr__(self, name):
        return getattr(self._data, name)

    def __setattr__(self, name, value):
        setattr(self._data, name, value)

    def __delattr__(self, name):
        delattr(self._data, name)

    def _processor(self, handler):
        self._cleanup()
        self._load()

        try:
            return handler()
        finally:
            self._save()

    def _load(self):
        cookie_name = self.cookie_name
        cookie_domain = self.cookie_domain
        cookie_path = self.cookie_path
        httponly = self.httponly
        self.session_id = request.cookies[cookie_name]

        # protection against session_id tampering
        if self.session_id and not self._valid_session_id(self.session_id):
            self.session_id = None

        self._check_expiry()

        if self.session_id:
            d = self.store[self.session_id]
            self.update(d)
            self._validate_ip()

        if not self.session_id:
            self.session_id = self._generate_session_id()

            if self._initializer:
                if isinstance(self._initializer, dict):
                    self.update(deepcopy(self._initializer))
                elif hasattr(self._initializer, '__call__'):
                    self._initializer()

        self.ip = request.remote_addr

    def _check_expiry(self):
        if self.session_id and self.session_id not in self.store:
            return self.expired()

    def _validate_ip(self):
        if self.session_id and self.get('ip', None) != request.remote_addr:
            return self.expired()

    def _save(self):
        if not self.get('_killed'):
            self._set_cookie(self.session_id)
            self.store[self.session_id] = dict(self._data)
        else:
            self._set_cookie(self.session_id, expires=-1)

    def _set_cookie(self, session_id, expires=None, **kw):
        cookie_name = self.cookie_name
        cookie_domain = self.cookie_domain
        cookie_path = self.cookie_path
        httponly = self.httponly
        secure = self.secure
        response.set_cookie(cookie_name, session_id, expires=expires, domain=cookie_domain,
                            httponly=httponly, secure=secure, path=cookie_path)

    def _generate_session_id(self):
        while True:
            rand = os.urandom(16)
            now = time.time()
            secret = self.secret_key
            session_id = sha1('%s%s%s%s' % (rand, now, request.remote_addr, secret))
            session_id = session_id.hexdigest()

            if session_id not in session_id.store:
                break

            return session_id

    @staticmethod
    def _valid_session_id(session_id):
        reg = re.compile(r'^[0-9a-fA-F]+$')
        return reg.match(session_id)

    def _cleanup(self):
        """Cleanup the stored sessions"""
        current_time = time.time()
        timeout = self.timeout

        if current_time - self._last_clean_time > timeout:
            self.store.cleanup(timeout)
            self._last_clean_time = current_time

    def expired(self):
        """Called when an expired session is atime"""
        self._killed = True
        self._save()
        raise SessionExpired(self.expired_message)

    def kill(self):
        """Kill the session, make it no longer available"""
        del self.store[self.session_id]
        self._killed = True


class Store:
    """Base class for session stores"""
    def __contains__(self, key):
        raise NotImplementedError()

    def __getitem__(self, key):
        raise NotImplementedError()

    def __setitem__(self, key, value):
        raise NotImplementedError()

    def cleanup(self, timeout):
        """Removes all the expired sessions"""
        raise NotImplementedError()

    @staticmethod
    def encode(session_dict):
        """Encodes session dict as a string"""
        pickled = pickle.dumps(session_dict)
        return base64.encodebytes(pickled)

    @staticmethod
    def decode(session_data):
        pickled = base64.decodebytes(session_data)
        return pickle.loads(pickled)


class DiskStore(Store):
    def __init__(self, root):
        if not os.path.exists(root):
            os.makedirs(os.path.abspath(root))
        self.root = root

    def _get_path(self, key):
        if os.path.sep in key:
            raise ValueError('Bad key: %s' % str(key))
        return os.path.join(self.root, key)

    def __contains__(self, key):
        path = self._get_path(key)
        return os.path.exists(path)

    def __getitem__(self, key):
        path = self._get_path(key)
        if os.path.exists(path):
            pickled = open(path).read()
            return self.decode(pickled)
        else:
            raise KeyError(key)

    def __setitem__(self, key, value):
        path = self._get_path(key)
        pickled = self.encode(value)
        try:
            with open(path, 'w') as f:
                f.write(pickled)
        except IOError:
            pass

    def __delitem__(self, key):
        path = self._get_path(key)
        if os.path.exists(path):
            os.remove(path)

    def cleanup(self, timeout):
        now = time.time()
        for f in os.listdir(self.root):
            path = self._get_path(f)
            atime = os.stat(path).st_atime
            if now - atime > timeout:
                os.remove(path)


class DBStore(Store):
    """
    Store for saving a session in database.
    Needs a table with the following columns:
    session_id CHAR(128) UNIQUE NOT NULL,
    atime DATATIME NOT NULL DEFAULT current_timestamp,
    data TEXT
    """
    def __init__(self, db, table_name):
        self.db = db
        self.table = table_name

    def __contains__(self, key):
        data = self.db.select(self.table, where='session_id=$key', vars=locals())
        return bool(list(data))

    def __getitem__(self, key):
        now = datetime.datetime.now()
        try:
            s = self.db.select(self.table, where='session_id=$key', vars=locals())[0]
            self.db.update(self.table, where='session_id=$key', atime=now, vars=locals())
        except IndexError:
            raise KeyError(key)
        else:
            return self.decode(s.data)

    def __setitem__(self, key, value):
        pickled = self.encode(value)
        now = datetime.datetime.now()
        if key in self:
            self.db.update(self.table, where="session_id=$key", data=pickled, vars=locals())
        else:
            self.db.insert(self.table, False, session_id=key, data=pickled)

    def __delitem__(self, key):
        self.db.delete(self.table, where="session_id=$key", vars=locals())

    def cleanup(self, timeout):
        timeout = datetime.timedelta(timeout/(24.0*60*60))
        last_allowed_time = datetime.datetime.now() - timeout
        self.db.delete(self.table, where="$last_allowed_time > atime", vars=locals())

