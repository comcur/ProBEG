	# -*- coding: utf-8 -*-
from django.core.urlresolvers import reverse

from menu import Menu, MenuItem

def is_admin(request):
	return request.user.groups.filter(name='admins').exists()

def is_not_admin(request):
	return not request.user.groups.filter(name='admins').exists()

def is_only_editor(request):
	return request.user.groups.filter(name='editors').exists() and not request.user.groups.filter(name='admins').exists()

def is_authenticated(request):
	return request.user.is_authenticated()

def is_not_authenticated(request):
	return not request.user.is_authenticated()

Menu.add_item('user', MenuItem(u'Вход', reverse('probeg_auth:login'), check=is_not_authenticated))

Menu.add_item('main', MenuItem(u'Новости', reverse('results:main_page')))
Menu.add_item('main', MenuItem(u'Мои результаты', reverse('results:home'), check=is_authenticated))
Menu.add_item('main', MenuItem(u'Календарь забегов', reverse('results:races')))
Menu.add_item('main', MenuItem(u'Участники забегов', reverse('results:runners')))

admin_children = (
	MenuItem(u'Памятка администратору', reverse('editor:memo_admin')),
	MenuItem(u'Памятка редактору', reverse('editor:memo_editor')),
	MenuItem(u'Шаблоны для писем', reverse('editor:memo_templates')),
	MenuItem(u'Рекомендации по текстам', reverse('editor:memo_spelling')),
	MenuItem(u'Города', reverse('editor:cities'), separator=True),
	MenuItem(u'Добавить город', reverse('editor:city_create')),
	MenuItem(u'Регионы', reverse('editor:regions')),
	MenuItem(u'Дистанции', reverse('editor:distances')),
	MenuItem(u'Добавить дистанцию', reverse('editor:distance_create')),
	MenuItem(u'Серии пробегов', reverse('editor:seria')),
	MenuItem(u'Добавить серию пробегов', reverse('editor:series_create')),
	MenuItem(u'Добавить новость', reverse('editor:news_create')),
	MenuItem(u'Действия для одобрения', reverse('editor:action_history'), separator=True),
	MenuItem(u'Статус КЛБМатча и протоколы для загрузки', reverse('editor:klb_status')),
	MenuItem(u'Все забеги, учтённые в КЛБМатче', reverse('editor:events_in_klb')),
	MenuItem(u'Кто сколько чего сделал', reverse('editor:admin_work_stat')),
	MenuItem(u'Пользователи сайта', reverse('editor:users'), separator=True),
	MenuItem(u'Страницы в соцсетях', reverse('editor:social_pages')),
	MenuItem(u'Имена бегунов', reverse('editor:runner_names')),
	MenuItem(u'Популярные имена в результатах', reverse('editor:popular_names_in_free_results')),
	MenuItem(u'Платежи через сайт', reverse('editor:all_payments')),
	MenuItem(u'Разные мелкие штуки', reverse('editor:util')),
	MenuItem(u'Администрирование Django', reverse('admin:index'), separator=True),
	MenuItem(u'Отправить письмо', '#', attr={'class': 'send_from_info_page'}),
)
Menu.add_item('user', MenuItem(u'Администратору',
							'#',
							# separator=True,
							check=is_admin,
							children=admin_children))

editor_children = (
	MenuItem(u'Памятка', reverse('editor:memo_editor')),
	MenuItem(u'Рекомендации по текстам', reverse('editor:memo_spelling')),
	MenuItem(u'Города', reverse('editor:cities'), separator=True),
	MenuItem(u'Добавить город', reverse('editor:city_create')),
	MenuItem(u'Регионы', reverse('editor:regions')),
	MenuItem(u'Дистанции', reverse('editor:distances')),
	MenuItem(u'Добавить дистанцию', reverse('editor:distance_create')),
)
Menu.add_item('user', MenuItem(u'Редактору',
							'#',
							# separator=True,
							check=is_only_editor,
							children=editor_children))

user_children = (
	MenuItem(u'Моя страница', reverse('results:home')),
	MenuItem(u'Поискать результаты', reverse('results:find_results')),
	MenuItem(u'Проставить ссылки на Страву', reverse('results:my_strava_links')),
	MenuItem(u'Личные данные',  reverse('results:my_details'), separator=True),
	MenuItem(u'Все ваши платежи', reverse('results:my_payments')),
	MenuItem(u'Сменить пароль', reverse('probeg_auth:password_change')),
	MenuItem(u'Выход',          reverse('probeg_auth:logout'), separator=True),
)

Menu.add_item('user', MenuItem(lambda request: request.user.first_name + ' ' + request.user.last_name,
							'#',
							check=is_authenticated,
							children=user_children))

other_children = (
	MenuItem(u'Добавить новый забег в календарь', reverse('results:add_new_event')),
	MenuItem(u'Организаторы', reverse('results:organizers'), check=is_admin),
	MenuItem(u'Клубы любителей бега', reverse('results:clubs'), separator=True),
	MenuItem(u'Новые возможности для клубов', reverse('results:about_club_membership')),
	MenuItem(u'Рейтинг забегов', reverse('results:rating'), separator=True),
	MenuItem(u'Все результаты', reverse('results:results'), check=is_admin),
	MenuItem(u'Все новости', reverse('results:all_news')),
	MenuItem(u'Рекорды России в возрастных группах', reverse('results:age_group_records'), separator=True),
	MenuItem(u'Рекорды Беларуси в возрастных группах', reverse('results:age_group_records', kwargs={'country_id': 'BY'}), check=is_admin),
	MenuItem(u'Статистика по паркранам России', reverse('results:parkrun_stat')),
	MenuItem(u'Отчёты: Бег в России — 2019', reverse('results:russia_report', kwargs={'year': '2019'}), separator=True),
	MenuItem(u'Бег в России — 2018', reverse('results:russia_report', kwargs={'year': '2018'})),
	MenuItem(u'Бег в России — 2017', reverse('results:russia_report', kwargs={'year': '2017'})),
	MenuItem(u'Бег в России — 2016', reverse('results:russia_report', kwargs={'year': '2016'})),
	MenuItem(u'Бег в Беларуси — 2019', reverse('results:belarus_report', kwargs={'year': '2019'})),
	MenuItem(u'Бег в Беларуси — 2018', reverse('results:belarus_report', kwargs={'year': '2018'})),
	MenuItem(u'Сертификация трасс', reverse('measurement_about'), separator=True),
	MenuItem(u'Разрядные нормативы в беге', reverse('sport_classes'), separator=True),
	MenuItem(u'Стандарт протокола', reverse('protocol')),
	MenuItem(u'О сайте', reverse('about'), separator=True),
	MenuItem(u'Новые возможности сайта', reverse('about_new_site')),
	MenuItem(u'Как вы можете помочь сайту', reverse('how_to_help')),
	MenuItem(u'Контактная информация', reverse('contacts'), separator=True),
	MenuItem(u'Написать нам письмо', '#', attr={'id': 'send_to_info_page'}),
	MenuItem(u'Мы в соцсетях', reverse('social_links')),
)

klb_children = (
	# MenuItem(u'Заказ памятных медалей участника матча–2018', reverse('results:medal_payment')),
	MenuItem(u'КЛБМатч–2020: Приглашение', reverse('results:about_match', kwargs={'year': '2020'})),
	MenuItem(u'Индивидуальная заявка', reverse('results:klb_application', kwargs={'year': '2020'})),
	MenuItem(u'Текущее положение', reverse('results:klb_match_summary', kwargs={'year': '2020'})),
	MenuItem(u'Забеги, не учитывающиеся в КЛБМатче', reverse('results:events_not_in_match', kwargs={'year': '2020'})),
	MenuItem(u'Слепки', reverse('results:klb_reports')),
	MenuItem(u'КЛБМатч–2019: итоговое положение', reverse('results:klb_match_summary', kwargs={'year': '2019'}), separator=True),
	MenuItem(u'КЛБМатч–2018: итоговое положение', reverse('results:klb_match_summary', kwargs={'year': '2018'})),
	MenuItem(u'КЛБМатч–2017: итоговое положение', reverse('results:klb_match_summary', kwargs={'year': '2017'})),
	MenuItem(u'КЛБМатч–2016: итоговое положение', reverse('results:klb_match_summary', kwargs={'year': '2016'})),
	MenuItem(u'Расчёт очков', reverse('results:calculator')),
)

Menu.add_item('main', MenuItem(u'КЛБМатч', '#', children=klb_children))
Menu.add_item('main', MenuItem(u'Ещё', '#', children=other_children))
Menu.add_item('main', MenuItem(u'Изготовление медалей', 'https://probeg.org/medal/'))
