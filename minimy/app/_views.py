from web import Minim, request

app = Minim()


class Index:
    def get(self):
        return 'Hello Minim'


app.add_route({
    r'/': Index
})

app.run()
