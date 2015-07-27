import os
from web import Minim, render, send_file

app = Minim()


@app.get('/favicon.ico')
def favicon():
    return ''


@app.get('/')
def index():
    sad = ['苒苒物华休', '杳杳故音绝']
    return render('index.html', sad=sad)

app.run()
