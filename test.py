import threading

# @get('/index/:var')
# def index():
#     print('hi')
# print(index.__web_route__)
#
# route = Route(index)
# route()


# def _static_file_generator(fpath):
#     block_size = 8192
#     with open(fpath, 'rb') as f:
#         block = f.read(block_size)
#         while block:
#             yield block
#             block = f.read(block_size)
#
#
# for i in _static_file_generator('test/foo.txt'):
#     print(i)

# ctx = threading.local()
# print(ctx.application.document_root)
# import mimetypes
#
# mimetypes.init()
# print(mimetypes.knownfiles)

from web import Request
from io import StringIO, BytesIO

# r = Request({'REQUEST_METHOD': 'GET', 'QUERY_STRING': 'a=1&c=2&c=2'})
# print(r.GET)

# r = Request({'REQUEST_METHOD': 'POST', 'wsgi.input': BytesIO('a=1&b=M%20M&c=ABC&c=XYZ&e='.encode('utf-8'))})
#
# print(r.POST)

# r = Request({'HTTP_COOKIE': 'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
# print(r.cookies)
# from web import response_header_dict
# print(response_header_dict)
# import re
# from web import build_re
# pattern = re.compile(build_re('/blog/:list/item/:dd/hi'))
# result = pattern.match('/blog/a1/item/a2/hi')
#
# def foo():
#     pass
# # for name in dir(test):
# #     print(type(name))
# foo.haha = 'abc'
# import os
# import copy
# g = copy.copy(globals())
#
# for v in g.values():
#     if callable(v) and hasattr(v, 'haha'):
#         print(v)

from web import Minim, response_header_dict, Route, Router
#
# app = Minim()
#
# @app.get('/')
# def index():
#     return 'hello minim!'
#
# @app.get('/:name')
# def uname(name):
#     return 'hello %s' % name
#
# @app.get('/blog')
# def blog():
#     return 'i will writing something simple but beautiful~'
#
#
# app.run()

# print(response_header_dict)

from web import Minim, response, request

app = Minim()


@app.get('/')
def index():
    print(request.query_string)
    return 'hello minim'


# @app.post('/')
# def index():
#     print(request.query_string)
#     return 'hello minim'

@app.get('/blog/<int:bar>/<foo>')
def blog(bar, foo):
    print(bar)
    print(foo)
    # response.set_header('cymoo', 'keep calm and carry on')
    # response.set_cookie('logged', 'yes')
    return str(bar)

app.run()









