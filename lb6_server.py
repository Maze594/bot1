from flask import Flask, request, Response, render_template, make_response
from viberbot import Api
from viberbot.api.bot_configuration import BotConfiguration
from viberbot.api.messages import VideoMessage
from viberbot.api.messages.text_message import TextMessage
from viberbot.api.messages.keyboard_message import KeyboardMessage
import logging

from viberbot.api.viber_requests import ViberConversationStartedRequest
from viberbot.api.viber_requests import ViberFailedRequest
from viberbot.api.viber_requests import ViberMessageRequest
from viberbot.api.viber_requests import ViberSubscribedRequest
from viberbot.api.viber_requests import ViberUnsubscribedRequest

import json
import random
import sqlite3
import sqlalchemy
from sqlalchemy import create_engine

import threading
import time
from apscheduler.schedulers.background import BackgroundScheduler
import requests

class MyDateBase:
    def __init__(self, database_name):
        engine = create_engine(database_name)
        self.connection = engine.connect()

        metadata = sqlalchemy.MetaData()
        self.Users = sqlalchemy.Table('Users', metadata, autoload=True, autoload_with=engine)
        self.Words = sqlalchemy.Table('Words', metadata, autoload=True, autoload_with=engine)
        self.Examples = sqlalchemy.Table('Examples', metadata, autoload=True, autoload_with=engine)
        self.Answers = sqlalchemy.Table('Answers', metadata, autoload=True, autoload_with=engine)
        self.Settings = sqlalchemy.Table('Settings', metadata, autoload=True, autoload_with=engine)

    def close(self):
        self.connection.close()

    def add_user(self, user_name, viber_id):
        query = sqlalchemy.insert(self.Users).values(full_name=user_name, viber_id=viber_id, time_last_answer=sqlalchemy.func.current_timestamp())
        self.connection.execute(query)

        dict = {"Words": [], "OtherWords": [], "Count": 0, "Points": 0, "Length": 0, "NowInTest": False}
        self.set_user_dict(viber_id, dict)


    def check_user(self, viber_id):
        query = sqlalchemy.select([self.Users]).where(self.Users.columns.viber_id == viber_id)
        ResultProxy = self.connection.execute(query)
        if ResultProxy.fetchone() == None:
            return False
        else:
            return True

    def get_user_id(self, viber_id):
        query = sqlalchemy.select([self.Users.columns.user_id]).where(self.Users.columns.viber_id == viber_id)
        ResultProxy = self.connection.execute(query)
        return ResultProxy.fetchone()[0]

    def get_user_name(self, viber_id):
        query = sqlalchemy.select([self.Users.columns.full_name]).where(self.Users.columns.viber_id == viber_id)
        ResultProxy = self.connection.execute(query)
        return ResultProxy.fetchone()[0]

    def get_user_dict(self, viber_id):
        query = sqlalchemy.select([self.Users.columns.dict]).where(self.Users.columns.viber_id == viber_id)
        ResultProxy = self.connection.execute(query)
        res = ResultProxy.fetchone()[0]
        if res==None:
            return None;
        return json.loads(res)

    def set_user_dict(self, viber_id, dict):
        query = sqlalchemy.update(self.Users).values(dict=json.dumps(dict)).where(self.Users.columns.viber_id == viber_id)
        self.connection.execute(query)

    def add_word(self, word, translate):
        query = sqlalchemy.insert(self.Words).values(word=word, translate=translate)
        self.connection.execute(query)

    def get_word_id(self, word):
        query = sqlalchemy.select([self.Words.columns.word_id]).where(self.Words.columns.word == word)
        ResultProxy = self.connection.execute(query)
        return ResultProxy.fetchone()[0]

    def count_studied_word_by_user(self, user):
        user_id = self.get_user_id(user)
        query = sqlalchemy.select([sqlalchemy.func.count()]).where(sqlalchemy.and_(self.Answers.columns.user_id == user_id, self.Answers.columns.count_right >= 5))
        ResultProxy = self.connection.execute(query)
        return ResultProxy.fetchone()[0]

    def count_education_word_by_user(self, user):
        user_id = self.get_user_id(user)
        query = sqlalchemy.select([sqlalchemy.func.count()]).where(sqlalchemy.and_(self.Answers.columns.user_id == user_id, self.Answers.columns.count_right != None))
        ResultProxy = self.connection.execute(query)
        return ResultProxy.fetchone()[0]

    def example_for_word(self, word):
        query = sqlalchemy.select([self.Examples.columns.example])
        query = query.select_from(self.Examples.join(self.Words, self.Examples.columns.word_id == self.Words.columns.word_id))
        query = query.where(self.Words.columns.word == word)
        query = query.order_by(sqlalchemy.sql.func.random()).limit(5)
        ResultProxy = self.connection.execute(query)
        return ResultProxy.fetchone()[0]


    def get_time_last_answer_user(self, user):
        query = sqlalchemy.select([self.Users.columns.time_last_answer]).where(self.Users.columns.viber_id == user)
        ResultProxy = self.connection.execute(query)
        return ResultProxy.fetchone()[0]

    def get_random_words_for_user(self, user):
        user_id = self.get_user_id(user)
        correct_count = db.get_setting('correct_count')
        test_size = db.get_setting('test_size')

        queryPod = sqlalchemy.select([self.Answers]).where(self.Answers.columns.user_id == user_id)
        podQuery = queryPod.cte()
        query = sqlalchemy.select([self.Words.columns.word, self.Words.columns.translate])
        query = query.select_from(self.Words.outerjoin(podQuery, self.Words.columns.word_id == podQuery.columns.word_id))
        query = query.where(sqlalchemy.or_(podQuery.columns.count_right < correct_count, podQuery.columns.count_right == None))
        query = query.order_by(sqlalchemy.sql.func.random()).limit(test_size)
        ResultProxy = self.connection.execute(query)
        rez = []
        for word in ResultProxy.fetchall():
            rez.append({"Word": word[0], "Translate": word[1]})

        print(rez)
        return rez



    def get_random_3_words_without(self, without):
        query = sqlalchemy.select([self.Words.columns.translate]).where(self.Words.columns.word != without)
        query = query.order_by(sqlalchemy.sql.func.random()).limit(3)
        ResultProxy = self.connection.execute(query)
        rez= [ResultProxy.fetchone()[0], ResultProxy.fetchone()[0], ResultProxy.fetchone()[0]];
        print(rez)
        return rez

    def change_right_word_for_user(self, word, user):
        self.check_answer_user_word_and_add(word, user)
        word_id = self.get_word_id(word)
        user_id = self.get_user_id(user)

        query = sqlalchemy.select([self.Answers.columns.count_right]).where(sqlalchemy.sql.and_(self.Answers.columns.word_id == word_id,self.Answers.columns.user_id==user_id))
        ResultProxy = self.connection.execute(query)
        count = ResultProxy.fetchone()[0]

        query = sqlalchemy.update(self.Answers).values(count_right=count+1, time_last_answer=sqlalchemy.func.current_timestamp())
        query = query.where(sqlalchemy.sql.and_(self.Answers.columns.word_id == word_id, self.Answers.columns.user_id == user_id))
        self.connection.execute(query)

        self.update_user_lasttime(user_id)

    def change_wrong_word_for_user(self, word, user):
        self.check_answer_user_word_and_add(word, user)
        word_id = self.get_word_id(word)
        user_id = self.get_user_id(user)

        query = sqlalchemy.update(self.Answers).values(time_last_answer=sqlalchemy.func.current_timestamp())
        query = query.where(sqlalchemy.sql.and_(self.Answers.columns.word_id == word_id, self.Answers.columns.user_id == user_id))
        self.connection.execute(query)

        self.update_user_lasttime(user_id)

    # Обновить время последнего ответа
    def update_user_lasttime(self, user_id):
        query = sqlalchemy.update(self.Users).values(time_last_answer=sqlalchemy.func.current_timestamp())
        query = query.where(self.Users.columns.user_id == user_id)
        self.connection.execute(query)

    def check_answer_user_word_and_add(self, word, user):
        word_id = self.get_word_id(word)
        user_id = self.get_user_id(user)

        query = sqlalchemy.select([self.Answers]).where(sqlalchemy.sql.and_(self.Answers.columns.word_id == word_id, self.Answers.columns.user_id == user_id))
        ResultProxy = self.connection.execute(query)
        if ResultProxy.fetchone() != None:
            return
        else:
            query = sqlalchemy.insert(self.Answers).values(word_id=word_id, user_id=user_id, count_right=0)
            self.connection.execute(query)

    def update_user_last_data(self, user_id):
        query = sqlalchemy.update(self.Users).values(time_last_answer=sqlalchemy.func.current_timestamp())
        query = query.where(self.Users.columns.user_id == user_id)
        self.connection.execute(query)

    def get_setting(self, name):
        query = sqlalchemy.select([self.Settings.columns.value]).where(self.Settings.columns.name == name)
        ResultProxy = self.connection.execute(query)
        return ResultProxy.fetchone()[0]

    def set_setting(self, name, value):
        query = sqlalchemy.update(self.Settings).values(value=value)
        query = query.where(self.Settings.columns.name == name)
        self.connection.execute(query)

class ListMessages:
    def __init__(self):
        self.list = []

    def check(self, value):
        b = False
        for var in self.list:
            if var == value:
                b = True
                break
        if not b:
            self.list.append(value)
        if len(self.list) > 30:
            self.list.pop(0)
        return b

#import os
#DATABASE_URL = os.environ['DATABASE_URL']
#db = MyDateBase(DATABASE_URL)
db = MyDateBase('postgres://fwiiintzvcymtf:c62fe38b37799152e85fd946f0158758bd9a6e8b5b552c99fefbda3d3a87e41a@ec2-46-137-177-160.eu-west-1.compute.amazonaws.com:5432/d1a7h29bcmn0an')
#db = MyDateBase('sqlite:///bot.db?check_same_thread=false')

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

app = Flask(__name__)

bot_configuration = BotConfiguration(
    name='mazebot1',
    avatar='http://viber.com/avatar.jpg',
    auth_token='4b07babaf1e7d25d-2ecd93e1da1f003f-224f396a51d4c5aa'
)
viber = Api(bot_configuration)



KeysTask = json.load(open('keyboardTask.txt', encoding='utf-8'))
KeysStart = json.load(open('keyboardStart.txt', encoding='utf-8'))
KeysStartWithNotification = json.load(open('keyboardStartWIthNotification.txt', encoding='utf-8'))

sched = BackgroundScheduler()
sched.start()

list_messages = ListMessages()


@app.route('/incoming', methods=['POST'])
def incoming():
    logger.debug("received request. post data: {0}".format(request.get_data()))

    if not viber.verify_signature(request.get_data(), request.headers.get('X-Viber-Content-Signature')):
        return Response(status=200)

    viber_request = viber.parse_request(request.get_data())


    if isinstance(viber_request, ViberMessageRequest):
        # Если сообщение уже приходило
        if list_messages.check(viber_request.message_token):
            return Response(status=200)

        message = viber_request.message.text.split()
        print(message)
        viber_id = viber_request.sender.id

        CheckUser(viber_request.sender.name, viber_id)
        
        dict = db.get_user_dict(viber_id)
        #if viber_id not in DictUserFind:
        #    dict = {"Words": [], "OtherWords": [], "Count": 0, "Points": 0, "Length": 0, "NowInTest": False}

        #try:
        if 1==1:
            if  dict['NowInTest']==False and message[0] == '/start':

                if sched.get_job(viber_id) != None:
                    sched.remove_job(viber_id)

                dict = {"Words": [], "OtherWords": [], "Count": 0, "Points": 0, "Length": 0, "NowInTest": True}
                dict["Words"] = db.get_random_words_for_user(viber_id)
                #print(dict["Words"])
                dict["Length"] = len(dict["Words"])


                GenNewTask(viber_id, dict)
                SetKeysTask(viber_id, dict)
                viber.send_messages(viber_id, [
                    TextMessage(text="Как переводится с английского слово '"+dict['Words'][dict['Count']]['Word']+"'?"),
                    KeyboardMessage(keyboard=KeysTask)
                ])
            elif message[0] == '/example':
                SetKeysTask(viber_id, dict)

                viber.send_messages(viber_id, [
                    TextMessage(text=db.example_for_word(dict['Words'][dict['Count']]['Word'])),
                    KeyboardMessage(keyboard=KeysTask)
                ])

            elif message[0] == '/addnotification':
                addNotificationForUser(viber_id)
                viber.send_messages(viber_id, [TextMessage(text="Напоминание отложено"),
                                               KeyboardMessage(keyboard=KeysStartWithNotification)])

            elif dict['NowInTest']==True and message[0] == str(dict['Count']):
                # Ответ верный
                if message[1] == dict['Words'][dict['Count']]['Translate']:
                    CheckAndNextTask(viber_id, dict, True)

                # Ответ неверный
                else:
                    CheckAndNextTask(viber_id, dict, False)

            elif dict['NowInTest']==False:
                CheckUserAndStartMessage(viber_request.sender.name, viber_request.sender.id)
                addNotificationForUser(viber_id)

        print (db.get_user_dict(viber_id))
        db.set_user_dict(viber_id, dict)


        #except:
        #    CheckUserAndStartMessage(viber_request.sender.name, viber_request.sender.id)
            
            #info = {"id": viber_id}
            #thread = threading.Thread(target=worker, args=(info,))
            #thread.start()



    elif isinstance(viber_request, ViberSubscribedRequest):
        viber.send_messages(viber_request.user.id, [
            TextMessage(text="Добро пожаловать! Спасибо за подписку!")
        ])
        #CheckUserAndStartMessage(viber_request.user.name, viber_request.user.id)

    elif isinstance(viber_request, ViberConversationStartedRequest):
        CheckUserAndStartMessage(viber_request.user.name, viber_request.user.id)



    elif isinstance(viber_request, ViberUnsubscribedRequest):
        print("User ", viber_request.user_id, " unsubscribed")

    return Response(status=200)


# Генерация нового задания
def GenNewTask(viber_id, dict):
    dict['OtherWords'] = db.get_random_3_words_without(dict['Words'][dict['Count']]['Word'])

# Проверка на выполнение и выдача следующего задания
def CheckAndNextTask(id, dict, isCorrect):
    dict['Count'] += 1
    MessIsCorr = ""

    if isCorrect:
        dict['Points'] += 1
        MessIsCorr = "Верный ответ\n"
        db.change_right_word_for_user(dict['Words'][dict['Count']-1]['Word'], id)
    else:
        MessIsCorr = "Неверный ответ\n"
        db.change_wrong_word_for_user(dict['Words'][dict['Count']-1]['Word'], id)

    if dict['Count'] < dict['Length']:
        GenNewTask(id, dict)
        SetKeysTask(id, dict)
        viber.send_messages(id, [
            TextMessage(text=MessIsCorr + "Как переводится с английского слово '" + dict['Words'][dict['Count']]['Word'] + "'?"),
            KeyboardMessage(keyboard=KeysTask)
        ])
    elif dict['Count'] == dict['Length']:
        print("END!")
        dict['NowInTest'] = False
        addNotificationForUser(id)
        viber.send_messages(id, [
            TextMessage(text=MessIsCorr + "Вы набрали " + str(dict['Points']) + " из " + str(dict['Length']) + " баллов!"),
            KeyboardMessage(keyboard=KeysStart)
        ])
    else:
        StartMessage(id)

# Формирование кнопок
def SetKeysTask(id, dict):
    nwordinkey = random.randint(0, 3)
    otherN = 0
    random.shuffle(dict['OtherWords'])
    nword = dict['Count']
    for i in range(4):
        if (i == nwordinkey):
            KeysTask['Buttons'][i]['Text'] = dict['Words'][nword]['Translate']
            KeysTask['Buttons'][i]['ActionBody'] = str(nword) + ' ' + dict['Words'][nword]['Translate']
        else:
            KeysTask['Buttons'][i]['Text'] = dict['OtherWords'][otherN]
            KeysTask['Buttons'][i]['ActionBody'] = str(nword) + ' ' + dict['OtherWords'][otherN]
            otherN += 1

# Стартовое сообщение с описанием
def StartMessage(id):
    user_name = db.get_user_name(id)
    viber.send_messages(id, [
        TextMessage(text="Привет, " + user_name + "!\n" +
                         "Изучали: " + str(db.count_education_word_by_user(id)) + " слов\n" +
                         "Выучено: " + str(db.count_studied_word_by_user(id)) + " слов\n" +
                         "Последний раз отвечали: " + str(db.get_time_last_answer_user(id)) + "\n" +
                         "Бот создан для заучивания английских слов. Для начала теста нажмите на кнопку внизу или введите /start"),
        KeyboardMessage(keyboard=KeysStart)
    ])

# Добавление нового пользователя и вывод стартового сообщения
def CheckUserAndStartMessage(name, id):
    if db.check_user(id)==False:
        db.add_user(name,id)
    StartMessage(id)

# Добавление пользователя
def CheckUser(name, id):
    if db.check_user(id)==False:
        db.add_user(name,id)

def funcNotification(viber_id):
    viber.send_messages(viber_id, [TextMessage(text="Напоминалка! Вы давно не повторяли слова!"), KeyboardMessage(keyboard=KeysStartWithNotification)])
    sched.remove_job(viber_id)

def addNotificationForUser(viber_id):
    if sched.get_job(viber_id) != None:
        sched.remove_job(viber_id)
    sched.add_job(funcNotification, 'interval', minutes=db.get_setting('notification_time'), id=viber_id, args=[viber_id])

@app.route('/', methods=['POST', 'GET'])
def main_page():
    return render_template('main.html')

@app.route('/settings', methods=['POST', 'GET'])
def settings():
    if request.method == 'POST':
        notification_time = request.form['notification_time']
        test_size = request.form['test_size']
        correct_count = request.form['correct_count']
        db.set_setting('notification_time', notification_time)
        db.set_setting('test_size', test_size)
        db.set_setting('correct_count', correct_count)
        resp = make_response(render_template('settings.html', notification_time=notification_time, test_size=test_size, correct_count=correct_count))
        return resp
    else:
        notification_time = db.get_setting('notification_time')
        test_size = db.get_setting('test_size')
        correct_count = db.get_setting('correct_count')
        return render_template('settings.html', notification_time=notification_time, test_size=test_size, correct_count=correct_count)

"""
from sqlalchemy import Table, Column, Integer, String, MetaData, DateTime, ForeignKey
engine = create_engine('postgres://cpgvvrlzfdmwpj:03597e30364ff5577227a014846af922b6ea88d83595fd8ccb4e6599486abbb4@ec2-34-206-252-187.compute-1.amazonaws.com:5432/dfjlf46qvkm9gs?sslmode=require')
connection = engine.connect()
metadata = sqlalchemy.MetaData()

Settings = Table(
    'Settings', metadata,
    Column('setting_id', Integer, primary_key = True),
    Column('name', String),
    Column('value', Integer)
)
metadata.create_all(engine)

Settings = sqlalchemy.Table('Settings', metadata, autoload=True, autoload_with=engine)
query = sqlalchemy.insert(Settings).values(name='notification_time', value=30)
ResultProxy = connection.execute(query)
query = sqlalchemy.insert(Settings).values(name='test_size', value=3)
ResultProxy = connection.execute(query)
query = sqlalchemy.insert(Settings).values(name='correct_count', value=5)
ResultProxy = connection.execute(query)
"""

def dont_sleep():
    print (requests.get('https://bot12213.herokuapp.com/'))

sched.add_job(dont_sleep, 'interval', minutes=25, id='dont_sleep')


#app.run(host='0.0.0.0', port=5000, debug=False)

