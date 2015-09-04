from web import Minim, render, request, response
from template import MiniTemplate
from models import Person

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
    print('host', request.host)
    print('host-port', request.host_port)
    print('path', request.path)
    print('fullpath', request.full_path)
    print('script-root', request.script_root)
    print('url', request.url)
    print('base-url', request.base_url)
    print('url-root', request.url_root)
    print('host-url', request.host_url)
    print('host', request.host)
    return render('index.html', motto=motto, welcome=welcome, persons=persons)


@app.get('/home')
def home():
    # print(request.foo)
    print('host-port', request.host_port)
    print('path', request.path)
    print('fullpath', request.full_path)
    print('script-root', request.script_root)
    print('url', request.url)
    print('base-url', request.base_url)
    print('url-root', request.url_root)
    print('host-url', request.host_url)
    print('host', request.host)
    return 'do not go gentle into that good night.'


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # print(request.POST.to_dict())
        # print(request.POST)
        print(request.forms.to_dict())
        # print(request.params.to_dict())
        return request.params.hobbits
    return render('login.html')

app.run()
