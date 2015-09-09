from web import Minim, render, request, response
from template import MiniTemplate
from models import Person
from io import BytesIO

app = Minim()
greetings = 'The world is my idea~'
MiniTemplate.inject_context('greetings', greetings)


@app.get('/favicon.ico')
def favicon():
    return ''


@app.get('/')
def index():
    request.foo = 'bar'
    persons = Person.select()
    # print(request.foo)
    welcome = 'Keep calm and carry on!'
    motto = ['醒醒我们回家了', '世界是我的表象', '向死而生', '凡人所有的我都有']
    # print('host', request.host)
    # print('host-port', request.host_port)
    # print('path', request.path)
    # print('fullpath', request.full_path)
    # print('script-root', request.script_root)
    # print('url', request.url)
    # print('base-url', request.base_url)
    # print('url-root', request.url_root)
    # print('host-url', request.host_url)
    # print('host', request.host)
    return render('index.html', motto=motto, welcome=welcome, persons=persons)


@app.get('/home')
def home():
    # print(request.foo)
    # print('host-port', request.host_port)
    # print('path', request.path)
    # print('fullpath', request.full_path)
    # print('script-root', request.script_root)
    # print('url', request.url)
    # print('base-url', request.base_url)
    # print('url-root', request.url_root)
    # print('host-url', request.host_url)
    # print('host', request.host)
    return 'do not go gentle into that good night.'


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # ct = request.environ.get('CONTENT_LENGTH')
        # print(ct)
        # print(request.environ['wsgi.input'].read(int(ct)))
        # print('wsgi.input', request.environ['wsgi.input'].read(100))
        print('content-length', request.content_length)
        # bo = request.environ['wsgi.input']
        # print(bo.read(129))
        # print(type(bo))
        # bo.seek(0)
        # print('twice', request.environ['wsgi.input'].read(10))
        # print('twice', request.environ['wsgi.input'].read(10))
        # print(request.POST.to_dict())
        # print(request.POST)
        # print('request.form:', request.form)
        print('request.content_type:', request.content_type)
        # # print(request.params.to_dict())
        # return request.params.hobbits
        # return request.environ['wsgi.input'].read()
        # while True:
        #     cont = request.environ['wsgi.input'].read(300)
        #     if not cont:
        #         break
        #     yield cont
        print('form', request.form)
        print('file', request.files.avatar)
        request.files.avatar.save('/Users/cymoo/Desktop/minim_file')

        return 'haha'

    return render('login.html')

app.run()

