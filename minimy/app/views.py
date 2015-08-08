from web import Minim, render
from template import MiniTemplate

app = Minim()
greetings = 'The world is my idea~'
MiniTemplate.inject_context('greetings', greetings)


@app.get('/favicon.ico')
def favicon():
    return ''


@app.get('/')
def index():
    welcome = 'Keep calm and carry on!'
    motto = ['醒醒我们回家了', '世界是我的表象', '向死而生', '凡人所有的我都有']
    return render('index.html', motto=motto, welcome=welcome, name='colleen')


@app.get('/home')
def home():
    welcome = 'will my will'
    motto = ['醒醒我们回家了', '世界是我的表象', '向死而生', '凡人所有的我都有']
    return render('home.html', motto=motto, welcome=welcome)

app.run()
