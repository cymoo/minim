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
    print(response.headers)
    return render('index.html', motto=motto, welcome=welcome, persons=persons)


@app.get('/home')
def home():
    # print(request.foo)
    return 'do not go gentle into that good night.'


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        print(request.POST.to_dict())
        print(request.forms.to_dict())
        print(request.params.to_dict())
        return request.params.hobbits
    return render('login.html')

app.run()
