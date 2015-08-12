from web import Minim, render, request, response, g
from template import MiniTemplate

app = Minim()
greetings = 'The world is my idea~'
MiniTemplate.inject_context('greetings', greetings)


@app.get('/favicon.ico')
def favicon():
    return ''


@app.get('/')
def index():
    # request.foo = 'bar'
    # print(request.foo)
    print(request.environ['wsgi.multithread'])
    welcome = 'Keep calm and carry on!'
    motto = ['醒醒我们回家了', '世界是我的表象', '向死而生', '凡人所有的我都有']
    return render('index.html', motto=motto, welcome=welcome)


@app.get('/home')
def home():
    # print(request.foo)
    return 'do not go gentle into that good night.'

app.run()
