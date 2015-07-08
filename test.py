from web import get

@get('/index')
def index():
    pass
print(index.__web_route__)






