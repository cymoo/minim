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

from web import Minim, response, request, redirect, send_file
import time
import os

app = Minim()


# @app.before_request
# def defore_request():
#     print('before request')
#
#
# @app.after_request
# def after_request():
#     print(response.headers)


@app.get('/favicon.ico')
def favicon():
    basedir = os.path.abspath(os.path.dirname(__file__))
    directory = os.path.join(basedir, 'test')
    foo = send_file(directory, 'favicon.ico')
    print(response.headers)
    return foo


@app.get('/avatar')
def avatar():
    basedir = os.path.abspath(os.path.dirname(__file__))
    directory = os.path.join(basedir, 'test')
    foo = send_file(directory, 'infinite.jpg')
    print(response.headers)
    return foo


@app.get('/')
def index():
    # for k, v in request.environ.items():
    #     print(k, v)
    # print(request.environ.get('QUERY_STRING'))
    # print(request.GET.get('a'))
    if request.GET.get('a') == '13':
        print(request.GET.get('a', None))
        redirect('http://127.0.0.1:9000/cymoo')
    else:
        print('no redirect')
    print(response.status)
    # time.sleep(10)
    # print(time.time())
    return '<h1 style="text-align: center;">Hello Minim</h1>'


# @app.post('/')
# def index():
#     print(request.query_string)
#     return 'hello minim'

@app.get('/cymoo')
def cymoo():
    for k, v in request.environ.items():
        print(k, v)
    # response.status = 200
    # print(request.environ.get('QUERY_STRING', 'none'))
    # print(response.status)
    # print('cymoo')
    return 'void'


@app.route('/gt', methods=['GET', 'POST'])
def gt():
    if request.method == 'GET':
        return 'GET method'
    elif request.method == 'POST':
        return 'POST method'
    else:
        print('else')


@app.get('/<float:bar>')
def blog(bar):
    print(type(bar))
    print(bar)
    return str(bar)


app.run()
