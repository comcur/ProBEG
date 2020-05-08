# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
import datetime

from results import models
from editor.views.views_stat import update_events_count, update_results_count, update_users_stat, make_connections, generate_default_calendar
from editor.views.views_stat import generate_events_in_seria_by_year2, try_call_function
from editor.views.views_klb_stat import update_match
from editor.views.views_user import send_messages_with_results
from editor.views.views_age_group_record import generate_better_age_group_results
from editor.views.views_mail import send_function_calls_letter

class Command(BaseCommand):
	help = 'Updates values in Statistics table and places in KLBMatch, connects results with birthdat to runners, creates new runners,' \
		+ ' send results with recently attached results'

	def handle(self, *args, **options):

		try_call_function(u'Обновление календаря забегов на ближайший месяц', generate_default_calendar)
		try_call_function(u'Обновление числа забегов в прошлом и будущем', update_events_count)
		try_call_function(u'Обновление числа результатов в базе', update_results_count)

		if datetime.date.today().weekday() == 6:
			try_call_function(u'Обновление статистики всех пользователей сайта по воскресеньям', update_users_stat)

		try_call_function(u'Обновление статистики КЛБМатча-{}'.format(models.CUR_KLB_YEAR), update_match, year=models.CUR_KLB_YEAR, debug=True)
		if models.NEXT_KLB_YEAR and models.NEXT_KLB_YEAR_AVAILABLE_FOR_ALL:
			try_call_function(u'Обновление статистики КЛБМатча-{}'.format(models.NEXT_KLB_YEAR), update_match,
				year=models.NEXT_KLB_YEAR, debug=True)

		try_call_function(u'Присоединение результатов, создание бегунов, письмо от Робота Присоединителя', make_connections)
		try_call_function(u'Отправка писем пользователям о присоединенных результатах и включении в команды', send_messages_with_results)

		try_call_function(u'Генерация страницы со всеми забегами всех серий в России за последние годы', generate_events_in_seria_by_year2)

		if datetime.date.today().weekday() == 3:
			try_call_function(u'Поиск новых рекордов России в возрастных группах по четвергам', generate_better_age_group_results,
				country_id='RU', debug=True)
			try_call_function(u'Поиск новых рекордов Беларуси в возрастных группах по четвергам', generate_better_age_group_results,
				country_id='BY', debug=True)

		send_function_calls_letter()