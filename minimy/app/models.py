
from orm import *

db = SqliteDatabase('people.db')


class Person(Model):
    name = CharField()
    motto = TextField()

    class Meta:
        database = db
