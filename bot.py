import vk_api
import datetime
import json
import os
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.longpoll import VkEventType, VkLongPoll
from config import user_token, group_token, host, dbname, user, password, port
from vk_api.utils import get_random_id
from database import Database


class VKinderBot:
    def __init__(self):
        self.group_auth = vk_api.VkApi(token=group_token)
        self.user_auth = vk_api.VkApi(token=user_token)
        self.longpoll = VkLongPoll(self.group_auth)
        self.keyboard = VkKeyboard(one_time=True)
        self.keyboard.add_button('Найти', color=VkKeyboardColor.POSITIVE)
        self.keyboard.add_button('Поиск по параметрам', color=VkKeyboardColor.PRIMARY)
        self.keyboard.add_line()
        self.keyboard.add_button('Ещё кандидаты', color=VkKeyboardColor.SECONDARY)
        self.keyboard.add_button('Далее', color=VkKeyboardColor.SECONDARY)
        self.keyboard.add_line()
        self.keyboard.add_button('Завершить просмотр', color=VkKeyboardColor.NEGATIVE)
        self.database = Database(dbname=dbname, user=user, password=password, host=host, port=port)
        self.search_offset = -1
        self.last_search_params = None
        self.last_candidate_search_offset = None

    def run(self):
        self.database.create_table()
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me and event.text:
                res_msg = event.text.lower()
                sender = event.user_id
                if res_msg == 'привет':
                    self.write_message(sender,
                                       f'Здравствуйте. Я бот знакомств VKinder. Сейчас я помогу найти пару в '
                                       f'соответствии с возрастом, полом, городом и семейным положением. Если '
                                       f'необходимо найти кандидата на основании Ваших параметров, то нажмите '
                                       f'"Найти", а для просмотра следующих кандидатов - "Ещё кандидаты". Если Вам '
                                       f'необходимо изменить возраст, пол или город кандидата нажмите "Поиск по '
                                       f'параметрам", а для просмотра следующего кандидата по параметрам нажмите '
                                       f'"Далее"', self.keyboard)
                elif res_msg == 'найти':
                    self.search_offset = 0
                    self.search_users(sender)
                elif res_msg == 'ещё кандидаты':
                    if self.search_offset < 0:
                        self.write_message(sender, 'Сначала выполните команду "Найти", чтобы начать поиск кандидатов',
                                           self.keyboard)
                    else:
                        self.search_users(sender)
                elif res_msg == 'поиск по параметрам':
                    self.ask_params(sender)
                elif res_msg == 'далее':
                    if not self.last_search_params or self.last_candidate_search_offset == -1:
                        self.write_message(sender,
                                           'Сначала выполните команду "Поиск по параметрам", чтобы начать поиск '
                                           'кандидатов',
                                           self.keyboard)
                    else:
                        age_from, age_to, sex, city = self.last_search_params
                        if self.last_candidate_search_offset is None:
                            self.last_candidate_search_offset = 0
                        self.search_users_params(sender, age_from, age_to, sex, city,
                                                 self.last_candidate_search_offset + 10)
                        self.last_candidate_search_offset += 10
                elif res_msg == 'завершить просмотр':
                    self.write_message(sender, 'Спасибо за использование VKinder! Ждем вас снова')
                    self.del_table()
                    self.database.create_table()
                    os.system('python ' + os.path.realpath(__file__))
                elif hasattr(event, 'payload') and event.payload:
                    payload = json.loads(event.payload)
                    if 'vk_id' in payload:
                        vk_id = payload['vk_id']
                        vk_url = payload['vk_url']
                        if not self.database.check_candidate(vk_id):
                            self.database.save_candidate(vk_id, vk_url)
                            self.write_message(event.user_id, f'Кандидат {vk_url} сохранен')
                        else:
                            self.write_message(event.user_id, f'Кандидат {vk_url} уже сохранен')
                else:
                    self.write_message(sender, 'Для начала введите "Привет", чтобы узнать для чего я, ' +
                                       '"Найти" или "Поиск по параметрам"- для поиска партнера, ' +
                                       ' "Завершить просмотр" - для завершения работы программы', self.keyboard)

    def write_message(self, sender, message, keyboard=None):
        try:
            keyboard_data = keyboard.get_keyboard()
        except AttributeError:
            keyboard_data = None
        self.group_auth.method('messages.send',
                               {'user_id': sender, 'message': message, 'random_id': get_random_id(),
                                'keyboard': keyboard_data})

    def search_users(self, sender):
        try:
            user_info = self.user_auth.method('users.get', {'user_ids': sender, 'fields': 'bdate, sex, city'})[0]
            user_age = self.calculate_age(user_info['bdate'])
            user_sex = user_info['sex']
            user_city = user_info['city']['id']
            search_response = self.user_auth.method('users.search',
                                                    {'count': 1,
                                                     'city': user_city,
                                                     'sex': 1 if user_sex == 2 else 2,
                                                     'status': 0,
                                                     'status_list': [1, 6],
                                                     'age_from': user_age,
                                                     'age_to': user_age,
                                                     'has_photo': 1,
                                                     'fields': 'photo_max_orig, screen_name',
                                                     'offset': self.search_offset})
            for user in search_response['items']:
                vk_id = user['id']
                vk_url = f'https://vk.com/{user["screen_name"]}'
                user_info = self.user_auth.method('users.get', {'user_ids': vk_id, 'fields': 'is_closed, first_name, '
                                                                                             'last_name'})
                if user_info and not user_info[0]['is_closed']:
                    if not self.database.check_candidate(vk_id):
                        photos = self.get_top_photos(user)
                        message = f'{user_info[0]["first_name"]} {user_info[0]["last_name"]}\nСтраница: {vk_url}\n\n'
                        message += '\n'.join(photos)
                        self.write_message(sender, message, self.keyboard)
                        self.database.save_candidate(vk_id, vk_url)
                    else:
                        self.write_message(sender, f'{user_info[0]["first_name"]} {user_info[0]["last_name"]}\n'
                                                   f'Страница: {vk_url}\nКандидат уже сохранен.', self.keyboard)
                else:
                    self.write_message(sender, f'Профиль пользователя {vk_id} закрыт настройками приватности.',
                                       self.keyboard)
            if not search_response['items']:
                self.write_message(sender,
                                   'Подходящие пользователи не найдены. Нажмите "поиск по параметрам", чтобы изменить '
                                   'параметры поиска', self.keyboard)
            self.search_offset += 1
        except vk_api.exceptions.ApiError as e:
            self.write_message(sender, f'Произошла ошибка при поиске пользователей: {e}', self.keyboard)

    def calculate_age(self, bdate):
        if bdate:
            bdate = datetime.datetime.strptime(bdate, '%d.%m.%Y')
            age = datetime.datetime.now().year - bdate.year
            if datetime.datetime.now().month < bdate.month or (
                    datetime.datetime.now().month == bdate.month
                    and datetime.datetime.now().day < bdate.day):
                age -= 1
            return age

    def get_top_photos(self, user):
        photos_response = self.user_auth.method('photos.get',
                                                {'owner_id': user['id'], 'album_id': 'profile', 'rev': 1, 'count': 3,
                                                 'extended': 1, 'photo_sizes': 1})
        photos_data = []
        for photo in photos_response['items']:
            sizes = photo['sizes']
            likes = photo['likes']['count']
            comments = photo['comments']['count']
            photo_data = {'sizes': sizes, 'likes': likes, 'comments': comments}
            photos_data.append(photo_data)
        photos_data = sorted(photos_data, key=lambda x: (x['likes'], x['comments']), reverse=True)[:3]
        photos = []
        for photo_data in photos_data:
            photo_url = photo_data['sizes'][-1]['url']
            photos.append(photo_url)
        return photos

    def ask_params(self, sender):
        self.write_message(sender,
                           'Введите параметры поиска в формате: "возраст от-до, пол (м/ж), город". Например: 20-30, '
                           'м, Москва')
        self.last_candidate_search_offset = 0
        self.last_search_params = None
        age_from = None
        age_to = None
        sex = None
        city = None
        search_num = 0
        for event in self.longpoll.listen():
            if event.type == VkEventType.MESSAGE_NEW and event.to_me and event.text:
                res_msg = event.text.lower()
                if ',' in res_msg and len(res_msg.split(',')) == 3:
                    try:
                        age_range, sex, city = res_msg.split(',')
                        age_from, age_to = age_range.split('-')
                        age_from = int(age_from.strip())
                        age_to = int(age_to.strip())
                        sex = 1 if sex.strip().lower() == 'ж' else 2
                        city_response = self.user_auth.method('database.getCities', {'country_id': 1, 'q': city})
                        if city_response['count'] > 0:
                            city_id = city_response['items'][0]['id']
                            self.search_users_params(sender, age_from, age_to, sex, city_id)
                        else:
                            self.write_message(sender, f'Город "{city}" не найден. Попробуйте ввести другой город.')
                        break
                    except ValueError:
                        self.write_message(sender,
                                           'Некорректный формат параметров. Попробуйте ввести данные в формате: '
                                           'возраст от-до, пол, город(20-30, женский, Москва)')
                else:
                    self.write_message(sender,
                                       'Некорректный формат параметров. Попробуйте ввести данные в формате: возраст '
                                       'от-до, пол, город(20-30, женский, Москва)')

    def search_users_params(self, sender, age_from, age_to, sex, city, search_offset=0):
        try:
            if search_offset == 0:
                self.last_candidate_search_offset = -1

            search_response = self.user_auth.method('users.search',
                                                    {'count': 1,
                                                     'offset': search_offset,
                                                     'city': city,
                                                     'sex': sex,
                                                     'status': 0,
                                                     'status_list': [1, 6],
                                                     'age_from': age_from,
                                                     'age_to': age_to,
                                                     'has_photo': 1,
                                                     'fields': 'photo_max_orig, screen_name'})
            for user in search_response['items']:
                vk_id = user['id']
                vk_url = f'https://vk.com/{user["screen_name"]}'
                user_info = self.user_auth.method('users.get',
                                                  {'user_ids': vk_id, 'fields': 'is_closed, first_name, last_name'})
                if user_info and not user_info[0]['is_closed']:
                    if not self.database.check_candidate(vk_id):
                        photos = self.get_top_photos(user)
                        message = f'{user_info[0]["first_name"]} {user_info[0]["last_name"]}\nСтраница: {vk_url}\n\n'
                        message += '\n'.join(photos)
                        self.write_message(sender, message, self.keyboard)
                        self.database.save_candidate(vk_id, vk_url)
                        search_offset += 1
                        self.last_candidate_search_offset = search_offset
                    else:
                        self.write_message(sender, f'{user_info[0]["first_name"]} {user_info[0]["last_name"]}\n'
                                                   f'Страница: {vk_url}\nКандидат уже сохранен.', self.keyboard)
                else:
                    self.write_message(sender, f'Профиль пользователя {vk_id} закрыт настройками приватности.',
                                       self.keyboard)
                    return
            if not search_response['items']:
                self.write_message(sender, 'Подходящие пользователи не найдены. Попробуйте изменить параметры поиска.',
                                   self.keyboard)
            else:
                self.last_search_params = (age_from, age_to, sex, city)
        except Exception as error:
            self.write_message(sender, 'Произошла ошибка при поиске пользователей. Попробуйте позже.', self.keyboard)
            print(error)

        except vk_api.exceptions.ApiError as e:
            self.write_message(sender, f'Произошла ошибка при поиске пользователей: {e}', self.keyboard)

    def del_table(self):
        self.database.delete_table()
        self.database.disconnect()


bot = VKinderBot()
bot.__init__()
bot.run()
