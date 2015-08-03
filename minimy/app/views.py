import os
from web import Minim, render, send_file

app = Minim()


@app.get('/favicon.ico')
def favicon():
    return ''


@app.get('/')
def index():
    motto = ['醒醒我们回家了', '世界是我的表象', '向死而生', '凡人所有的我都有']
    name = 'cymoo'
    return render('index.html', motto=motto, name=name)

app.run()
