# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.db.models.query import Prefetch
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.contrib import messages
from collections import OrderedDict
import datetime
import xlrd
import math
import os
import re

from results import models
from .views_common import check_rights, group_required
from .views_result import split_name, get_first_name_position, fill_places, fill_race_headers, reset_race_headers
from .views_stat import generate_last_loaded_protocols

def log_warning(request, message):
	if request:
		messages.warning(request, message)
	else:
		print "Warning: " + message
def log_success(request, message):
	if request:
		messages.success(request, message)
	else:
		print "Success: " + message

OLD_RESULTS_DELETE_ALL = 1
OLD_RESULTS_DELETE_MEN = 2
OLD_RESULTS_DELETE_WOMEN = 3
OLD_RESULTS_LEAVE_ALL = 4

CELL_DATA_PASS = 0
CELL_DATA_PLACE = 1
CELL_DATA_BIB = 2
CELL_DATA_LNAME = 3
CELL_DATA_FNAME = 4
CELL_DATA_MIDNAME = 5
CELL_DATA_NAME = 6
CELL_DATA_BIRTHDAY = 7
CELL_DATA_AGE = 8
CELL_DATA_CITY = 9
CELL_DATA_REGION = 10
CELL_DATA_COUNTRY = 11
CELL_DATA_CLUB = 12
CELL_DATA_GENDER = 13
CELL_DATA_PLACE_GENDER = 14
CELL_DATA_CATEGORY = 15
CELL_DATA_PLACE_CATEGORY = 16
CELL_DATA_COMMENT = 17
CELL_DATA_RESULT = 18
CELL_DATA_GUN_RESULT = 19
CELL_DATA_SPLIT = 20
CELL_DATA_STATUS = 21

CELL_DATA_CHOICES = OrderedDict([
	(CELL_DATA_PASS, u'не загружаем'),
	(CELL_DATA_SPLIT, u'сплит'),
	(CELL_DATA_PLACE, u'место в абсолюте'),
	(CELL_DATA_BIB, u'стартовый номер'),
	(CELL_DATA_LNAME, u'фамилия'),
	(CELL_DATA_FNAME, u'имя'),
	(CELL_DATA_MIDNAME, u'отчество'),
	(CELL_DATA_NAME, u'имя целиком'),
	(CELL_DATA_BIRTHDAY, u'дата или год рождения'),
	(CELL_DATA_AGE, u'возраст'),
	(CELL_DATA_CITY, u'город'),
	(CELL_DATA_REGION, u'регион'),
	(CELL_DATA_COUNTRY, u'страна'),
	(CELL_DATA_CLUB, u'клуб'),
	(CELL_DATA_GENDER, u'пол'),
	(CELL_DATA_PLACE_GENDER, u'место среди пола'),
	(CELL_DATA_CATEGORY, u'группа'),
	(CELL_DATA_PLACE_CATEGORY, u'место в группе'),
	(CELL_DATA_COMMENT, u'комментарий'),
	(CELL_DATA_RESULT, u'результат'),
	(CELL_DATA_GUN_RESULT, u'грязное время'),
	(CELL_DATA_STATUS, u'статус результата'),
])

CATEGORY_PREFIX_NONE = 0
CATEGORY_PREFIX_RUS_SOME = 1
CATEGORY_PREFIX_RUS_ALL = 2
CATEGORY_PREFIX_ENG_SOME = 3
CATEGORY_PREFIX_ENG_ALL = 4
CATEGORY_PREFIXES = (
	(CATEGORY_PREFIX_NONE, u'ничего'),
	(CATEGORY_PREFIX_RUS_SOME, u'русские М и Ж, если группа начинается не с них'),
	(CATEGORY_PREFIX_RUS_ALL, u'русские М и Ж всем'),
	(CATEGORY_PREFIX_ENG_SOME, u'латинские M и F, если группа начинается не с них'),
	(CATEGORY_PREFIX_ENG_ALL, u'латинские M и F всем'),
)

MAX_N_COLS = 100

def anyin(s, templates):
	return any(x in s for x in templates)

def default_data_types(request, data, header_row, distance, column_data_types, column_split_values):
	if len(data) == 0:
		return [], []
	ncols = len(data[0])
	column_data_types = [CELL_DATA_PASS] * ncols
	column_split_values = [0] * ncols
	header = data[header_row]
	for col_index in range(ncols):
		if header[col_index]['type'] == xlrd.XL_CELL_TEXT:
			col_name = header[col_index]['value'].lower()
			if col_name in [u'старт', u'тип рез.', u'result_time', u'result_distance', u'выполненный разряд']:
				column_data_types[col_index] = CELL_DATA_PASS
			elif anyin(col_name, [u'результат с учетом возраст']):
				column_data_types[col_index] = CELL_DATA_PASS
			elif anyin(col_name, [u'м/ж', u'м./ж.', u'среди пола', u'gender pl', u'rank_gender', u'genderposition', u'gender position', u'gender pos']):
				column_data_types[col_index] = CELL_DATA_PLACE_GENDER
			elif anyin(col_name, [u'место абс', u'место в абс', u'overall', u'rank_abs', u'м (абс)', u'абсолютное ме', u'absoluteposition']):
				column_data_types[col_index] = CELL_DATA_PLACE
			elif anyin(col_name, [u'имя, фамилия', u'фамилия, имя', u'имя фамилия', u'имя и фам', u'фамилия и', u'фио', u'фи ', u'ф.и', u'ф. и'
					u'спортсмен', u'пiб', u'full name', u'имя целиком']):
				column_data_types[col_index] = CELL_DATA_NAME
			elif anyin(col_name, [u'фамилия', u'last name', u'last_name', u'name_last', u'lastname', u'прізвище', u'uzvārds']):
				column_data_types[col_index] = CELL_DATA_LNAME
			elif anyin(col_name, [u'имя', u'first name', u'first_name', u'name_first', u'firstname', u'iм\'я', u'vārds']):
				column_data_types[col_index] = CELL_DATA_FNAME
			elif u'отчество' in col_name:
				column_data_types[col_index] = CELL_DATA_MIDNAME
			elif anyin(col_name, [u'город', u'місто', u'территор', u'населенный пункт', u'city', u'pilsēta']):
				column_data_types[col_index] = CELL_DATA_CITY
			elif anyin(col_name, [u'регион', u'регіон', u'область', u'субъект']):
				column_data_types[col_index] = CELL_DATA_REGION
			elif anyin(col_name, [u'клуб', u'организация', u'команда', u'коллектив', u'ведомство', u'club', u'клб', u'кфк', u'team']):
				column_data_types[col_index] = CELL_DATA_CLUB
			elif anyin(col_name, [u'gun time', u'guntime', u'грязное время', u'абсолютный результат']):
				column_data_types[col_index] = CELL_DATA_GUN_RESULT
			elif anyin(col_name, [u'рез', u'итоговое', u'время', u'р-тат', u'result', u'chip time', u'chiptime', u'finišs']): # , u'финиш'
				column_data_types[col_index] = CELL_DATA_RESULT
			elif anyin(col_name, [u'в гр', u'в в.гр', u'в категории', u'место по возр', u'место кат', u'место в кат', u'в возр', u'м.в.гр', u'м.гр',
					u'age pl', u'division', u'rank_category', u'м (в.г.)', u'место груп', u'category position', u'categ pos']):
				column_data_types[col_index] = CELL_DATA_PLACE_CATEGORY
			elif anyin(col_name, [u'группа', u'катего', u'возрастн', u'в.гр', u'возр. гр', u'кат.', u'гр.', u'group', u'category', u'grupa']):
				column_data_types[col_index] = CELL_DATA_CATEGORY
			elif anyin(col_name, [u'возр', u'полн.', u'age']):
				column_data_types[col_index] = CELL_DATA_AGE
			elif anyin(col_name, [u'пол', u'gender', u'm/f']):
				column_data_types[col_index] = CELL_DATA_GENDER
			elif anyin(col_name, [u'№ участ', u'ст. №', u'стартовый №', u'ст.№', u'№ ст', u'bib', u'start #', u'number', u'стар но', u'race no']):
				column_data_types[col_index] = CELL_DATA_BIB
			elif anyin(col_name, [u'дата рож', u'рожд', u'родж', u'год', u'д.р', u'г.р', u'date of birth', u'birthday', u'birth_year']) \
					or (col_name == u'гр'):
				column_data_types[col_index] = CELL_DATA_BIRTHDAY
			elif anyin(col_name, [u'номер', u'старт.', u'старт ', u'нагр', u'ст.№']):
				column_data_types[col_index] = CELL_DATA_BIB
			elif anyin(col_name, [u'стр', u'країна', u'country', u'ctz', u'valsts']):
				column_data_types[col_index] = CELL_DATA_COUNTRY
			elif anyin(col_name, [u'status', u'статус']):
				column_data_types[col_index] = CELL_DATA_STATUS
			elif anyin(col_name, [u'отм.', u'комментари', u'примечани']):
				column_data_types[col_index] = CELL_DATA_COMMENT
			elif distance.distance_type == models.TYPE_METERS:
				length, split_distance = models.Distance.try_parse_distance(col_name, distance_type=models.TYPE_METERS)
				if length and (split_distance is None): # We recognized some number but no such distances exist. Then we create new one
					split_distance = models.Distance.objects.filter(length=length, distance_type=models.TYPE_METERS).first()
					if (split_distance is None) and col_name.endswith((u' м', u'км', u' m', u'km', u'km::start')):
						split_distance = models.Distance(length=length, distance_type=models.TYPE_METERS)
						if length <= 9999:
							split_distance.distance_raw = length
							split_distance.race_type_raw = u'м'
						elif length <= 9999999:
							split_distance.distance_raw = length / 1000.
							split_distance.race_type_raw = u'км'
						split_distance.name = split_distance.nameFromType()
						split_distance.created_by = request.user if request else models.USER_ROBOT_CONNECTOR
						split_distance.save()
						log_success(request, u'Мы создали дистанцию {}'.format(split_distance.name))
				if split_distance:
					column_data_types[col_index] = CELL_DATA_SPLIT
					column_split_values[col_index] = split_distance.id
		elif header[col_index]['type'] == xlrd.XL_CELL_NUMBER:
			length = models.int_safe(header[col_index]['value'])
			if length and (distance.distance_type == models.TYPE_METERS):
				split_distance = models.Distance.objects.filter(length=length, distance_type=models.TYPE_METERS).first()
				if split_distance:
					column_data_types[col_index] = CELL_DATA_SPLIT
					column_split_values[col_index] = split_distance.id
	return column_data_types, column_split_values

def xlrd_type2str(cell_type):
	if cell_type == xlrd.XL_CELL_EMPTY:
		return "XL_CELL_EMPTY"
	elif cell_type == xlrd.XL_CELL_BLANK:
		return "XL_CELL_BLANK"
	elif cell_type == xlrd.XL_CELL_NUMBER:
		return "XL_CELL_NUMBER"
	elif cell_type == xlrd.XL_CELL_TEXT:
		return "XL_CELL_TEXT"
	elif cell_type == xlrd.XL_CELL_DATE:
		return "XL_CELL_DATE"
	elif cell_type == xlrd.XL_CELL_BOOLEAN:
		return "XL_CELL_BOOLEAN"
	elif cell_type == xlrd.XL_CELL_ERROR:
		return "XL_CELL_ERROR"
	else:
		return "UNKNOWN"

def tuple2date_or_time(t):
	if all(t[:3]) and not any(t[3:]):
		return datetime.date(*t[:3]).strftime('%d.%m.%Y')
	if not any(t[:3]):
		if (len(t) > 6) and t[6]:
			return datetime.time(*t[3:]).strftime('%H:%M:%S.%f')[:-4]
		else:
			return datetime.time(*t[3:]).strftime('%H:%M:%S')
	return datetime.datetime(*t).isoformat(' ')

def xlrd_date_value2tuple(value, datemode):
	dt = xlrd.xldate.xldate_as_datetime(value, datemode)
	return ((0, 0, 0) if (dt.year <= 1899) else (dt.year, dt.month, dt.day)) + (dt.hour, dt.minute, dt.second, dt.microsecond)

def xlrd_cell2pair(cell, datemode):
	cell_type = cell.ctype
	cell_value = cell.value
	cell_datetime = cell_error = None
	if cell_type == xlrd.XL_CELL_NUMBER:
		if cell_value.is_integer():
			cell_value = int(cell_value)
	elif cell_type == xlrd.XL_CELL_DATE:
		try:
			# cell_datetime = xlrd.xldate_as_tuple(cell_value, datemode) # Doesn't work with centiseconds
			cell_datetime = xlrd_date_value2tuple(cell_value, datemode)
			cell_value = tuple2date_or_time(cell_datetime)
		except Exception, e:
			cell_error = 'Некорректные дата/время: {}'.format(str(e))
	elif cell_type == xlrd.XL_CELL_TEXT:
		cell_value = cell_value.strip()
		if cell_value == '':
			cell_type = xlrd.XL_CELL_EMPTY
		# if any(cell_value[:3]):
		# 	cell_value = datetime.date(*cell_value[:3])
		# else:
		# 	cell_value = datetime.time(*cell_value[3:])
	res = {'value': cell_value, 'type': cell_type}
	if cell_datetime:
		res['datetime'] = cell_datetime
	if cell_error:
		res['error'] = cell_error
	return res

def tuple2centiseconds(time, length=None):
	res = (((time[0] * 60) + time[1]) * 60 + time[2]) * 100
	if len(time) > 3 and time[3]:
		res += int(math.ceil(time[3] / 10000.))
	if length and models.result_is_too_large(length, res): # So the fields are shifted in Excel
		return res // 60
	return res

def timetuple2str(time):
	res = ''
	if time[0] > 23:
		days = time[0] // 24
		time = (time[0] % 24,) + time[1:]
		res = '{}days'.format(days)
	if (len(time) > 3) and time[3]:
		return res + datetime.time(*time).strftime('%Hh%Mm%Ss%fms')
	else:
		return res + datetime.time(*time).strftime('%Hh%Mm%Ss')

def centiseconds2str(value):
	hundredths = value % 100
	value //= 100
	seconds = value % 60
	value //= 60
	minutes = value % 60
	value //= 60
	hours = value
	return timetuple2str((hours, minutes, seconds, hundredths * 10000))

def xlrd_parse_nonempty_cell(cell): # Return cell_to_display
	if cell['type'] in [xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK]:
		# cell['error'] = u'Эта ячейка не может быть пустой'
		cell['warning'] = u'Пустая фамилия'
	return cell

def xlrd_parse_full_name(cell, first_name_position):
	if cell['type'] == xlrd.XL_CELL_TEXT:
		# name = cell['value'].split('\n')[-1] # It is needed for old "White nights" protocols
		name = cell['value']
		cell['lname'], cell['fname'], cell['midname'] = split_name(name, first_name_position)
		if cell['lname']:
			cell['comment'] = u'Ф:"' + cell['lname'] + '"'
			if cell['fname']:
				cell['comment'] += u', И:"' + cell['fname'] + '"'
			if cell['midname']:
				cell['comment'] += u', О:"' + cell['midname'] + '"'
		else:
			cell['error'] = u'Фамилия не может быть пустой'
	elif cell['type'] == xlrd.XL_CELL_NUMBER:
		cell['lname'] = unicode(cell['value'])
		cell['fname'] = ''
		cell['midname'] = ''
		cell['warning'] = u'Считаем число {} фамилией'.format(cell['lname'])
	elif cell['type'] == xlrd.XL_CELL_EMPTY:
		cell['lname'] = ''
		cell['fname'] = ''
		cell['midname'] = ''
		cell['warning'] = u'Пустое имя'
	else:
		cell['error'] = u'Неподходящий тип ячейки: {}'.format(xlrd_type2str(cell['type']))
	return cell

def xlrd_parse_int_or_none_cell(cell, datemode): # Return cell_to_display
	cell['number'] = None
	if (cell['type'] == xlrd.XL_CELL_NUMBER) and isinstance(cell['value'], (int, long)):
		cell['number'] = cell['value']
	elif cell['type'] == xlrd.XL_CELL_TEXT and (models.int_safe(cell['value']) > 0):
		cell['number'] = models.int_safe(cell['value'])
	elif cell['type'] == xlrd.XL_CELL_TEXT and cell['value'].endswith('.') and (models.int_safe(cell['value'][:-1]) > 0):
		cell['number'] = models.int_safe(cell['value'][:-1])
	elif cell['type'] == xlrd.XL_CELL_TEXT:
		res = cell['value'].upper()
		if res == 'I':
			cell['number'] = 1
			cell['warning'] = u'Римская 1'
		elif res == 'II':
			cell['number'] = 2
			cell['warning'] = u'Римская 2'
		elif res == 'III':
			cell['number'] = 3
			cell['warning'] = u'Римская 3'
		elif res == 'IV':
			cell['number'] = 4
			cell['warning'] = u'Римская 4'
		elif res == 'V':
			cell['number'] = 5
			cell['warning'] = u'Римская 5'
		else:
			cell['warning'] = u'Не целое число. Считаем пустым'
	else:
		cell['warning'] = u'Не целое число. Считаем пустым'
	return cell

def xlrd_parse_gender(cell): # Return cell_to_display
	gender = models.GENDER_UNKNOWN
	if cell['type'] in [xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK]:
		cell['error'] = u'Пол не указан'
	elif cell['type'] == xlrd.XL_CELL_TEXT:
		gender = models.string2gender(cell['value'])
		if gender == models.GENDER_UNKNOWN:
			cell['error'] = u'Невозможное значение пола'
	else:
		cell['error'] = u'Невозможное значение пола'
	if 'error' not in cell:
		cell['gender'] = gender
		cell['comment'] = u'Пол: {}'.format(models.GENDER_CHOICES[gender][1])
	return cell

def xlrd_parse_status(cell):
	if cell['type'] in [xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK]:
		status = models.STATUS_UNKNOWN
		cell['warning'] = u'Статус не указан. Определяем его по столбцу с результатом'
	elif cell['type'] == xlrd.XL_CELL_TEXT:
		status = models.string2status(cell['value'])
		if status == models.STATUS_UNKNOWN:
			cell['error'] = u'Невозможное значение статуса'
	else:
		cell['error'] = u'Невозможное значение статуса'
	if 'error' not in cell:
		cell['status'] = status
		cell['comment'] = u'Статус: {}'.format(models.RESULT_STATUSES[status][1])
	return cell

def parse_string_to_meters(s, distance):
	res = re.match(ur'^(\d+)$', s) # 99999
	if res:
		return True, int(res.group(1))
	res = re.match(ur'^(\d+)\s*м$', s) # 99999 м
	if res:
		return True, int(res.group(1))
	res = re.match(ur'^(\d+)\s*км$', s) # 999 км
	if res:
		return True, int(res.group(1)) * 1000
	res = re.match(ur'^(\d+)[\.,](\d{3})\s*км$', s) # 99[.,]999 км
	if res:
		return True, int(res.group(1)) * 1000 + int(res.group(2))
	res = re.match(ur'^(\d+)[\.,](\d{2})\s*км$', s) # 99[.,]99 км
	if res:
		return True, int(res.group(1)) * 1000 + int(res.group(2)) * 10
	res = re.match(ur'^(\d+)[\.,](\d{1})\s*км$', s) # 99[.,]9 км
	if res:
		return True, int(res.group(1)) * 1000 + int(res.group(2)) * 100
	res = re.match(ur'^(\d+)\s*км\s*(\d{1,3})\s*м$', s) # 99 км 999 м
	if res:
		return True, int(res.group(1)) * 1000 + int(res.group(2))
	res = re.match(ur'^(\d+)[\.,](\d{3})$', s) # 99[.,]999
	if res:
		return True, int(res.group(1)) * 1000 + int(res.group(2))
	res = re.match(ur'^(\d+)[\.,](\d{2})$', s) # 99[.,]99
	if res:
		return True, int(res.group(1)) * 1000 + int(res.group(2)) * 10
	return False, None

def parse_string_to_time(s, distance):
	res = re.match(r'^(\d{1,4})[h.:;](\d{1,2})[m:;](\d{1,2})$', s) # Hours[h.:;]minutes[m:;]seconds
	if res:
		return True, (int(res.group(1)), int(res.group(2)), int(res.group(3)))
	res = re.match(r'^(\d{1,2})[h.,:](\d{1,2})[.,:](\d{1,2})[.,:](\d{2})$', s) # Hours[h.,:]minutes[.,:]seconds[.,:]centiseconds
	if res:
		return True, (int(res.group(1)), int(res.group(2)), int(res.group(3)), int(res.group(4)) * 10000)
	res = re.match(r'^(\d{1,2})[h.,:](\d{1,2})[.,:](\d{1,2})[.,:](\d{1})$', s) # Hours[h.,:]minutes[.,:]seconds[.,:]deciseconds
	if res:
		return True, (int(res.group(1)), int(res.group(2)), int(res.group(3)), int(res.group(4)) * 100000)
	res = re.match(r'^(\d{2,3})[.,:](\d{2})\.{0,1}$', s) # Minutes[.,:]seconds
	if res:
		minutes = int(res.group(1))
		hours = minutes // 60
		minutes %= 60
		return True, (hours, minutes, int(res.group(2)))
	res = re.match(r'^(\d{1})[\.,:](\d{2})\.{0,1}$', s) # Minutes[.,:]seconds or seconds[.,:]centiseconds
	if res:
		if distance.distance_type == models.TYPE_METERS and distance.length <= 100: # seconds[.,:]centiseconds
			return True, (0, 0, int(res.group(1)), int(res.group(2)) * 10000)
		else: # Minutes[.,]seconds
			seconds = int(res.group(2))
			if seconds <= 59:
				return True, (0, int(res.group(1)), seconds)
	res = re.match(r'^(\d{2})[\.,](\d{1})$', s) # Seconds[.,:]deciseconds
	if res:
		if distance.distance_type == models.TYPE_METERS and distance.length <= 600:
			return True, (0, 0, int(res.group(1)), int(res.group(2)) * 100000)
	res = re.match(r'^(\d{2,3})[\.:](\d{2})[\.,](\d{1})$', s) # Minutes[.:]seconds[.,]deciseconds
	if res:
		minutes = int(res.group(1))
		hours = minutes // 60
		minutes %= 60
		return True, (hours, minutes, int(res.group(2)), int(res.group(3)) * 100000)
	res = re.match(r'^(\d{1})[\.,:](\d{2})[\.,](\d{1})$', s) # Minutes[.,:]seconds[.,]deciseconds again
	if res and distance.distance_type == models.TYPE_METERS and distance.length <= 3000:
		minutes = int(res.group(1))
		return True, (0, minutes, int(res.group(2)), int(res.group(3)) * 100000)
	res = re.match(r'^0{0,1}(\d{1}):(\d{2})[\.,](\d{2})$', s) # Hours:minutes.seconds
	if res and distance.distance_type == models.TYPE_METERS and distance.length > 3000:
		return True, (int(res.group(1)), int(res.group(2)), int(res.group(3)))
	res = re.match(r'^0{0,1}(\d{1}):(\d{2})[\.,]0$', s) # Hours:minutes.seconds again
	if res and distance.distance_type == models.TYPE_METERS and distance.length > 3000:
		return True, (int(res.group(1)), int(res.group(2)), 0)
	res = re.match(r'^0{0,1}(\d{1})[\.,](\d{1,2})[\.,](\d{2})\.{0,1}$', s)
	if res: # Hours[.,]minutes[.,]seconds or minutes[.,]seconds[.,]centiseconds
		if distance.distance_type == models.TYPE_METERS and distance.length <= 3000: # minutes[.,]seconds[.,]centiseconds
			return True, (0, int(res.group(1)), int(res.group(2)), int(res.group(3)) * 10000)
		else: # Hours[.,]minutes[.,]seconds
			return True, (int(res.group(1)), int(res.group(2)), int(res.group(3)))
	res = re.match(r'^(\d{1})[\.,](\d{1,2})[\.,](\d{1})$', s)
	if res: # Hours[.,]minutes[.,]seconds or minutes[.,]seconds[.,]deciseconds
		if distance.distance_type == models.TYPE_METERS and distance.length <= 3000: # minutes[.,]seconds[.,]deciseconds
			return True, (0, int(res.group(1)), int(res.group(2)), int(res.group(3)) * 100000)
		else: # Hours[.,]minutes[.,]seconds
			return True, (int(res.group(1)), int(res.group(2)), int(res.group(3)) * 10)
	res = re.match(r'^(\d{1,3})[:\.](\d{2})[\.,](\d{2})$', s) # Minutes:seconds.centiseconds
	if res and distance.distance_type == models.TYPE_METERS and distance.length <= 21100:
		minutes = int(res.group(1))
		hours = minutes // 60
		minutes %= 60
		return True, (hours, minutes, int(res.group(2)), int(res.group(3)) * 10000)
	res = re.match(r'^(\d{1,2}):(\d{1,2}):(\d{1,2})[:\.,](\d{3})$', s) # Hours:minutes:seconds:thousandths
	if res:
		hours = int(res.group(1))
		minutes = int(res.group(2))
		seconds = int(res.group(3))
		thousandths = int(res.group(4))
		hundredths = thousandths // 10
		if thousandths % 10:
			if hundredths < 99:
				hundredths += 1
			elif seconds < 59:
				hundredths = 0
				seconds += 1
			elif minutes < 59:
				hundredths = 0
				seconds = 0
				minutes += 1
			else:
				hundredths = 0
				seconds = 0
				minutes = 0
				hours += 1
		return True, (hours, minutes, seconds, hundredths * 10000)
	res = re.match(r'^(\d{1,2}):(\d{1,2}).(\d{3})$', s) # minutes:seconds.thousandths
	if res:
		hours = 0
		minutes = int(res.group(1))
		seconds = int(res.group(2))
		thousandths = int(res.group(3))
		hundredths = thousandths // 10
		if thousandths % 10:
			if hundredths < 99:
				hundredths += 1
			elif seconds < 59:
				hundredths = 0
				seconds += 1
			elif minutes < 59:
				hundredths = 0
				seconds = 0
				minutes += 1
			else:
				hundredths = 0
				seconds = 0
				minutes = 0
				hours += 1
		return True, (hours, minutes, seconds, hundredths * 10000)
	res = re.match(ur'^(\d{1,2})ч[ ]*(\d{1,2})м[ ]*(\d{1,2})[cс]$', s) # Hours[.:;]minutes[:;]seconds
	if res:
		return True, (int(res.group(1)), int(res.group(2)), int(res.group(3)))
	res = re.match(ur'^(\d{1,2})м[ ]*(\d{1,2})[cс]$', s) # Hours[.:;]minutes[:;]seconds
	if res:
		return True, (0, int(res.group(1)), int(res.group(2)))
	return False, None

def parse_number_to_time(value, distance): # Maybe it is minutes.seconds?
	if isinstance(value, (int, long)):
		return False, 'error 1'
	value *= 100
	if abs(value - round(value)) > 1e-10:
		return False, 'error 2:{}'.format(value - int(value))
	value = int(round(value))
	minutes = value // 100
	seconds = value % 100
	if seconds >= 60:
		return False, 'error 3'
	# return False, (value, minutes, seconds)
	return True, (minutes * 60 + seconds) * 100

def xlrd_parse_result(cell, datemode, distance, is_split=False, empty_means_DNS=False):
	status = None
	result = None
	distance_type = distance.distance_type
	result_is_empty = False
	if cell['type'] == xlrd.XL_CELL_DATE:
		if 'error' not in cell:
			if distance_type == models.TYPE_MINUTES:
				cell['error'] = u'Неподходящее значение: {}'.format(cell['datetime'])
			else:
				if any(cell['datetime'][3:]) and not any(cell['datetime'][:3]):
					status = models.STATUS_FINISHED
					result = tuple2centiseconds(cell['datetime'][3:], length=distance.length)
					cell['comment'] = u'Время: {}'.format(centiseconds2str(result))
				else:
					cell['error'] = u'Время с плохими полями: {}'.format(cell['datetime'])
	elif cell['type'] in [xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK]:
		if is_split:
			cell['comment'] = u'Сплит не указан'
		else:
			result_is_empty = True
			cell['warning'] = u'Пусто'
	elif cell['type'] == xlrd.XL_CELL_TEXT:
		if distance_type == models.TYPE_MINUTES:
			parsed, length = parse_string_to_meters(cell['value'], distance)
			if parsed:
				if length == 0:
					result_is_empty = True
					cell['warning'] = u'Нулевой результат'
		else:
			parsed, time = parse_string_to_time(cell['value'], distance)
			if parsed:
				if (time[1] > 59) or ((time[2] > 59)):
					parsed = False
				elif not any(time):
					result_is_empty = True
					cell['warning'] = u'Нулевое время'
		if parsed:
			if not result_is_empty:
				if distance_type == models.TYPE_MINUTES:
					status = models.STATUS_FINISHED
					result = length
					cell['comment'] = u'Текст: {} м'.format(result)
				else:
					status = models.STATUS_FINISHED
					result = tuple2centiseconds(time)
					cell['comment'] = u'Текст: {}'.format(centiseconds2str(result))
		else:
			if is_split:
				res = cell['value'].upper()
				if (res in [u'-', u'–', u'—']) or res.startswith(('DNS', 'DNF', 'DSQ', 'DQ', u'ЗАВЕРШИЛ', u'СОШ', u'НЕ ФИН', u'НЕ СТАРТ', u'Н.СТАРТ', u'НЕТ ИНФО')):
					cell['comment'] = u'Сплит не указан'
				else:
					cell['error'] = u'Нераспознанный сплит: {}'.format(res)
			else:
				res = cell['value'].upper()
				if res.startswith(('DNF', u'СОШ', u'НФ', u'Н/Ф', u'CОШ', u'НЕ ФИ', u'ЗАВЕРШИЛ', u'1 КРУГ', u'2 КРУГА', u'НЕТ. РЕГ. СТ.',
						u'СН.КОНТ', u'НЕ ЗАК', u'НЕТ ФИНИШ', u'Б/В', u'СХОД', u'ПРЕВ КВ', u'ОТСУТ.')):
					status = models.STATUS_DNF
					cell['comment'] = u'DNF'
				elif res.startswith(('DSQ', 'DNQ', 'DQ', u'ДИСКВ', u'ДСКВ', u'СНЯТ', u'CНЯТ')) or res.endswith(u'АННУЛ.'):
					status = models.STATUS_DSQ
					cell['comment'] = u'DSQ'
				elif res.startswith(('DNS', u'НЕ СТА', u'НЕ СТ', u'Н/Я', u'Н\Я', u'НЯ', u'Н/Д', u'Н\Д', u'Н/С', u'Н\С',
						u'Б/Р', u'НЕЯВКА', u'НЕ ЯВ', u'-', u'–', u'—')) \
						or (res == u'НС'):
					status = models.STATUS_DNS
					cell['comment'] = u'DNS'
				else:
					cell['error'] = u'Нераспознанный результат'
	elif cell['type'] == xlrd.XL_CELL_NUMBER:
		if distance_type == models.TYPE_MINUTES:
			status = models.STATUS_FINISHED
			result = cell['value']
			if not isinstance(result, (int, long)):
				if result > 1000: # These are meters
					result = int(math.floor(result))
				else: # These are kilometers
					result = int(round(result * 1000))
			cell['comment'] = u'Число: {} м'.format(result)
		else:
			parsed, centiseconds = parse_number_to_time(cell['value'], distance)
			if parsed:
				status = models.STATUS_FINISHED
				result = centiseconds
				cell['comment'] = u'Число: {}'.format(centiseconds2str(centiseconds))
			else:
				cell['error'] = u'Неподходящее числовое значение: {}'.format(cell['value'])
	else:
		cell['error'] = u'Неподходящий тип ячейки: {}'.format(xlrd_type2str(cell['type']))
	if result_is_empty:
		if is_split:
			cell['warning'] += u'. Считаем, что сплит не указан'
		elif empty_means_DNS:
			status = models.STATUS_DNS
			cell['warning'] += u'. Считаем, что DNS'
		else:
			status = models.STATUS_DNF
			cell['warning'] += u'. Считаем, что DNF'
	if status != models.STATUS_FINISHED:
		result = 0
	if not ('error' in cell):
		cell['status'] = status
		cell['result'] = result
	return cell

# short_birth_year=10, event_year=2019 -> 2010-01-01
# short_birth_year=10, event_year=2005 -> 1910-01-01
def two_digit_year_to_birthday(short_birth_year, event_year):
	event_year_first_digits, event_year_last_digits = divmod(event_year, 100)
	if short_birth_year <= event_year_last_digits:
		birth_year = short_birth_year + event_year_first_digits * 100
	else:
		birth_year = short_birth_year + (event_year_first_digits - 1) * 100
	return datetime.date(birth_year, 1, 1)

def parse_string_to_birthday(s, event_date): # Returns <is parsed?>, birthday, birthday_known
	s = s.lower().strip('.')
	if (s == "") or (s == u'н/д'):
		return True, None, False
	res = re.match(r'^(\d{1,2})[\.,/](\d{1,2})[\.,/](\d{4})\.{0,1}$', s)
	if res:
		try:
			if int(res.group(3)) >= 1900:
				return True, datetime.date(int(res.group(3)), int(res.group(2)), int(res.group(1))), True
		except:
			return False, None, False
	res = re.match(r'^(\d{1,2})[\./](\d{1,2})[\./](\d{2})$', s)
	if res:
		try:
			year = int(res.group(3))
			if year >= 15:
				year += 1900
			else:
				year += 2000
			return True, datetime.date(year, int(res.group(2)), int(res.group(1))), True
		except:
			return False, None, False
	res = re.match(r'^\.{0,1}(\d{4})$', s)
	if res:	
		try:
			if int(res.group(1)) >= 1900:
				return True, datetime.date(int(res.group(1)), 1, 1), False
		except:
			return False, None, False
	res = re.match(r'^(\d{4})[\.-](\d{2})[\.-](\d{2})$', s)
	if res:
		try:
			if int(res.group(1)) >= 1900:
				return True, datetime.date(int(res.group(1)), int(res.group(2)), int(res.group(3))), True
		except:
			return False, None, False
	res = re.match(r'^(\d{2})$', s)
	if res:
		return True, two_digit_year_to_birthday(int(res.group(1)), event_date.year), False
	if s.startswith((u'в/к', u'в\к', u'вне к')):
		return True, None, False
	return False, None, False

def xlrd_parse_birthday(cell, datemode, event_date): # Return tuple: cell_display, birthday, birthday_known
	birthday = None
	birthday_known = False
	if cell['type'] == xlrd.XL_CELL_DATE:
		if all(cell['datetime'][:3]) and not any(cell['datetime'][3:]):
			birthday = datetime.date(*(cell['datetime'][:3]))
			birthday_known = True
			cell['comment'] = u'Дата рождения: {}'.format(birthday.strftime('%d.%m.%Y'))
		else:
			cell['error'] = u'Дата с плохими полями: {}'.format(cell['datetime'])
	elif cell['type'] == xlrd.XL_CELL_NUMBER:
		birthyear = cell['value']
		if not isinstance(birthyear, (int, long)):
			if birthyear.is_integer():
				birthyear = int(round(cell['value']))
			else:
				cell['error'] = u'Неподходящий год рождения: {}'.format(birthyear)
		if 'error' not in cell:
			if 1900 <= birthyear <= event_date.year:
				birthday = datetime.date(birthyear, 1, 1)
				cell['comment'] = u'Год рождения: {}'.format(birthyear)
			elif 10 <= birthyear <= 99:
				birthday = two_digit_year_to_birthday(birthyear, event_date.year)
				cell['warning'] = u'Вероятно, год: {}'.format(birthday.year)
			elif 1800 <= birthyear <= 1899: # Hack for results.zone protocols
				cell['warning'] = u'Неподходящий год рождения. Считаем пустым'
			else:
				cell['error'] = u'Неподходящий год рождения: {}'.format(birthyear)
	elif cell['type'] in [xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK]:
		cell['warning'] = u'Пустая ячейка'
	elif cell['type'] == xlrd.XL_CELL_TEXT:
		parsed, birthday, birthday_known = parse_string_to_birthday(cell['value'], event_date)
		if parsed:
			if birthday_known:
				cell['comment'] = u'Дата рождения: {}'.format(birthday.strftime('%d.%m.%Y'))
			elif birthday:
				cell['comment'] = u'Год рождения: {}'.format(birthday.year)
			elif cell['value']:
				cell['warning'] = u'Считаем пустым'
			else:
				cell['warning'] = u'Пустая ячейка'
		else:
			cell['error'] = u'Это не дата рождения: {}'.format(cell['value'])
	else:
		cell['error'] = u'Неподходящий тип ячейки: {}'.format(xlrd_type2str(cell['type']))
	if birthday and ('error' not in cell) and (birthday >= datetime.date.today()):
		cell['error'] = u'Дата рождения — в будущем. Так нельзя!'
	if 'error' not in cell:
		cell['birthday'] = birthday
		cell['birthday_known'] = birthday_known
	return cell

def process_column_types(request, race, column_data_types, column_split_values):
	ncols = len(column_data_types)
	type2col = [None] * len(CELL_DATA_CHOICES)
	split2col = {}
	ok_to_load = True
	is_by_skoblina = race.event.series.is_by_skoblina()

	for i in range(ncols): # First, we load all column types to backward dictionary
		field_type = column_data_types[i]
		if field_type == CELL_DATA_PASS:
			continue
		if field_type == CELL_DATA_SPLIT:
			if column_split_values[i] == 0:
				log_warning(request, u'В колонке {} не указана дистанция для предварительного результата. Так нельзя.'.format(i))
				ok_to_load = False
				continue
			if column_split_values[i] in split2col:
				log_warning(request, u'Колонки {} и {} содержат сплит на одну и ту же дистанцию. Так нельзя.'.format(
					split2col[column_split_values[i]], i))
				ok_to_load = False
				continue
			if column_split_values[i] == race.distance.id:
				if is_by_skoblina: # Hack for Skoblina protocols
					column_data_types[i] = CELL_DATA_PASS
				else:
					log_warning(request, u'Сплит в колонке {} совпадает с длиной всей дистанции. Так нельзя.'.format(i))
					ok_to_load = False
					continue
			if race.distance_real and (column_split_values[i] == race.distance_real.id):
				log_warning(request, u'Сплит в колонке {} совпадает с фактической длиной всей дистанции. Так нельзя.'.format(i))
				ok_to_load = False
				continue
			split2col[column_split_values[i]] = i
		else:
			if type2col[field_type]:
				if is_by_skoblina and (field_type == CELL_DATA_PLACE_GENDER): # Hack for Skoblina protocols
					column_data_types[i] = CELL_DATA_PASS
				else:
					log_warning(request, u'Колонки {} и {} имеют один и тот же тип «{}». Так нельзя.'.format(
						type2col[field_type], i, CELL_DATA_CHOICES[field_type]))
					ok_to_load = False
					continue
			type2col[field_type] = i
	# Now let's check that all important columns exist
	if (type2col[CELL_DATA_NAME] is None) and ( (type2col[CELL_DATA_FNAME] is None) or (type2col[CELL_DATA_LNAME] is None) ):
		log_warning(request, u'Должна быть либо колонка «имя целиком», либо отдельные колонки «имя» и «фамилия».')
		ok_to_load = False
	if (type2col[CELL_DATA_NAME] is not None) and (
			(type2col[CELL_DATA_FNAME] is not None)
			or (type2col[CELL_DATA_LNAME] is not None)
			or (type2col[CELL_DATA_MIDNAME] is not None)
		):
		log_warning(request, u'Раз есть колонка «имя целиком», не должно быть отдельных колонок для фамилии, имени или отчества.')
		ok_to_load = False
	if type2col[CELL_DATA_RESULT] is None:
		log_warning(request, u'Вы не указали колонку с результатом. Так нельзя.')
		ok_to_load = False
	return type2col, split2col, ok_to_load

def process_cell_values(race, rows_with_results, datemode, data, column_data_types, column_numbers, type2col, settings):
	n_parse_errors = n_parse_warnings = 0
	settings['has_empty_results'] = False
	settings['has_categories_for_both_genders'] = False
	if type2col[CELL_DATA_NAME] is not None:
		# [:-1] is a hack for old "White Nights" protocols with multi-line cells with names
		first_name_position = get_first_name_position(
			[ unicode(data[i][type2col[CELL_DATA_NAME]]['value']).split('\n')[-1]
				for i in range(len(data)) if rows_with_results[i] ]
		)
	for row_index in range(len(data)):
		if rows_with_results[row_index]:
			for col_index in range(len(data[row_index])):
				cell = data[row_index][col_index]
				if column_data_types[col_index] == CELL_DATA_BIRTHDAY:
					cell = xlrd_parse_birthday(cell, datemode, race.event.start_date)
				elif column_data_types[col_index] == CELL_DATA_RESULT:
					cell = xlrd_parse_result(cell, datemode, race.distance, empty_means_DNS=settings['empty_means_DNS'])
					if cell['type'] in [xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK]:
						settings['has_empty_results'] = True
				elif column_data_types[col_index] == CELL_DATA_GUN_RESULT:
					cell = xlrd_parse_result(cell, datemode, race.distance, is_split=True)
				elif column_data_types[col_index] == CELL_DATA_SPLIT:
					cell = xlrd_parse_result(cell, datemode, race.distance, is_split=True)
				elif column_data_types[col_index] == CELL_DATA_NAME:
					cell = xlrd_parse_full_name(cell, first_name_position)
				elif column_data_types[col_index] == CELL_DATA_LNAME:
					cell = xlrd_parse_nonempty_cell(cell)
				elif column_data_types[col_index] == CELL_DATA_GENDER:
					cell = xlrd_parse_gender(cell)
				elif column_data_types[col_index] == CELL_DATA_STATUS:
					cell = xlrd_parse_status(cell)
				elif column_data_types[col_index] in [CELL_DATA_PLACE, CELL_DATA_PLACE_GENDER,
						CELL_DATA_PLACE_CATEGORY, CELL_DATA_AGE]:
					cell = xlrd_parse_int_or_none_cell(cell, datemode)
					if column_data_types[col_index] == CELL_DATA_AGE and cell['number'] \
							and not (models.MIN_RUNNER_AGE <= cell['number'] <= models.MAX_RUNNER_AGE):
						cell['error'] = u'Недопустимый возраст'
				if 'error' in cell:
					n_parse_errors += 1
					column_numbers[col_index]['errors'] = column_numbers[col_index].get('errors', 0) + 1
				if 'warning' in cell:
					n_parse_warnings += 1
					column_numbers[col_index]['warnings'] = column_numbers[col_index].get('warnings', 0) + 1
				data[row_index][col_index] = cell
	if n_parse_errors == 0:
		male_categories = set()
		female_categories = set()
		if ( (type2col[CELL_DATA_CATEGORY] is not None) or any(settings['categories']) ) \
			and ( (type2col[CELL_DATA_GENDER] is not None) or settings['show_gender_column'] ):
			for row_index in range(len(data)):
				if rows_with_results[row_index]:
					if type2col[CELL_DATA_CATEGORY] is not None:
						category = data[row_index][type2col[CELL_DATA_CATEGORY]]['value']
					else:
						category = settings['categories'][row_index]
					if category:
						if type2col[CELL_DATA_GENDER] is not None:
							gender = data[row_index][type2col[CELL_DATA_GENDER]]['gender']
						else:
							gender = models.GENDER_FEMALE if settings['genders'][row_index] else models.GENDER_MALE
						if gender == models.GENDER_MALE:
							male_categories.add(category)
						elif gender == models.GENDER_FEMALE:
							female_categories.add(category)
			settings['has_categories_for_both_genders'] = len(male_categories & female_categories) > 0

	return data, n_parse_errors, n_parse_warnings, column_numbers, settings

# Ok, loading results
def load_protocol(request, race, protocol, data, rows_with_results, column_data_types, column_split_values, type2col, settings):
	user = request.user if request else User.objects.get(pk=1)
	results_for_deletion = models.Result.objects.none()
	n_deleted_links = 0
	n_recovered_links = 0
	if settings['save_old_results'] == OLD_RESULTS_DELETE_ALL:
		results_for_deletion = race.result_set.filter(source=models.RESULT_SOURCE_DEFAULT)
	elif settings['save_old_results'] == OLD_RESULTS_DELETE_MEN:
		results_for_deletion = race.result_set.filter(source=models.RESULT_SOURCE_DEFAULT, gender=models.GENDER_MALE)
	elif settings['save_old_results'] == OLD_RESULTS_DELETE_WOMEN:
		results_for_deletion = race.result_set.filter(source=models.RESULT_SOURCE_DEFAULT, gender=models.GENDER_FEMALE)

	n_results_for_deletion = results_for_deletion.count()
	if n_results_for_deletion: # We try to save links to runners and KLB results
		for result in results_for_deletion.select_related('result_on_strava'):
			# If result has klb_result then it won't be lost
			if (result.runner or result.user) and not hasattr(result, 'klb_result'):
				models.Lost_result.objects.create(
					user_id=result.user_id,
					runner_id=result.runner_id,
					race=race,
					result=result.result,
					status=result.status,
					lname=result.lname,
					fname=result.fname,
					midname=result.midname,
					strava_link=result.result_on_strava.link if hasattr(result, 'result_on_strava') else 0,
					loaded_by=user,
				)
				n_deleted_links += 1
		log_warning(request, u'Удаляем {} старых результатов'.format(n_results_for_deletion))
		res = results_for_deletion.delete()
		log_warning(request, u'Удалено результатов, включая промежуточные: {}'.format(res[0]))
	
	nrows = len(data)
	ncols = len(column_data_types)
	n_results_loaded = n_splits_loaded = 0

	# we save pairs (category name, <category_size object>)
	category_sizes = {category_size.name: category_size for category_size in race.category_size_set.all()}
	category_lower_to_orig = {name.lower(): name for name in category_sizes}

	column_split_distances = [None] * ncols
	for i in range(ncols):
		if column_split_values[i]:
			column_split_distances[i] = models.Distance.objects.get(pk=column_split_values[i])
	for i in range(nrows):
		if not rows_with_results[i]:
			continue
		row = data[i]
		result = models.Result(race=race, loaded_by=user, loaded_from=protocol.upload.name)
		if type2col[CELL_DATA_NAME] is not None:
			cell = row[type2col[CELL_DATA_NAME]]
			result.name_raw = cell['value']
			result.lname, result.fname, result.midname = cell['lname'].title(), cell['fname'].title(), cell['midname'].title()
		else:
			if type2col[CELL_DATA_LNAME] is not None:
				result.lname_raw = row[type2col[CELL_DATA_LNAME]]['value']
				result.lname = unicode(result.lname_raw).title()
			if type2col[CELL_DATA_FNAME] is not None:
				result.fname_raw = row[type2col[CELL_DATA_FNAME]]['value']
				result.fname = unicode(result.fname_raw).title()
			if type2col[CELL_DATA_MIDNAME] is not None:
				result.midname_raw = row[type2col[CELL_DATA_MIDNAME]]['value']
				result.midname = unicode(result.midname_raw).title()
		if type2col[CELL_DATA_BIRTHDAY] is not None:
			# result.birthday_raw = row[type2col[CELL_DATA_BIRTHDAY]]['value']
			result.birthday = row[type2col[CELL_DATA_BIRTHDAY]]['birthday']
			result.birthday_known = row[type2col[CELL_DATA_BIRTHDAY]]['birthday_known']
			if result.birthday_known:
				result.birthday_raw = result.birthday
			elif result.birthday:
				result.birthyear_raw = result.birthday.year
		if type2col[CELL_DATA_AGE] is not None:
			result.age_raw = row[type2col[CELL_DATA_AGE]]['number']
			result.age = result.age_raw
		if type2col[CELL_DATA_COUNTRY] is not None:
			result.country_raw = row[type2col[CELL_DATA_COUNTRY]]['value']
			result.country_name = result.country_raw
		if type2col[CELL_DATA_REGION] is not None:
			result.region_raw = row[type2col[CELL_DATA_REGION]]['value']
		if type2col[CELL_DATA_CITY] is not None:
			result.city_raw = row[type2col[CELL_DATA_CITY]]['value']
			result.city_name = result.city_raw
		if type2col[CELL_DATA_CLUB] is not None:
			result.club_raw = row[type2col[CELL_DATA_CLUB]]['value']
			result.club_name = result.club_raw
		if type2col[CELL_DATA_PLACE] is not None:
			result.place_raw = row[type2col[CELL_DATA_PLACE]]['number']
			if settings['use_places_from_protocol']:
				result.place = result.place_raw
		if type2col[CELL_DATA_BIB] is not None:
			result.bib = row[type2col[CELL_DATA_BIB]]['value']
			result.bib_raw = result.bib
		if (type2col[CELL_DATA_STATUS] is None) or (row[type2col[CELL_DATA_STATUS]]['status'] == models.STATUS_UNKNOWN):
			result.result = row[type2col[CELL_DATA_RESULT]]['result']
			result.status = row[type2col[CELL_DATA_RESULT]]['status']
		else:
			result.status = row[type2col[CELL_DATA_STATUS]]['status']
			if result.status == models.STATUS_FINISHED:
				result.result = row[type2col[CELL_DATA_RESULT]]['result']
			else:
				result.result = 0
		result.status_raw = result.status
		result.time_raw = row[type2col[CELL_DATA_RESULT]]['value']
		if type2col[CELL_DATA_GUN_RESULT] is not None:
			result.gun_result = row[type2col[CELL_DATA_GUN_RESULT]]['result']
			result.gun_time_raw = row[type2col[CELL_DATA_GUN_RESULT]]['value']
		if type2col[CELL_DATA_GENDER] is not None:
			result.gender = row[type2col[CELL_DATA_GENDER]]['gender']
			result.gender_raw = row[type2col[CELL_DATA_GENDER]]['value']
		else:
			result.gender = models.GENDER_FEMALE if settings['genders'][i] else models.GENDER_MALE
		if type2col[CELL_DATA_PLACE_GENDER] is not None:
			result.place_gender_raw = row[type2col[CELL_DATA_PLACE_GENDER]]['number']
			if settings['use_places_from_protocol']:
				result.place_gender = result.place_gender_raw

		category = ''
		if type2col[CELL_DATA_CATEGORY] is not None:
			result.category_raw = unicode(row[type2col[CELL_DATA_CATEGORY]]['value'])
			category = result.category_raw
		else:
			category = settings['categories'][i]
		if category and (settings['category_prefix'] != CATEGORY_PREFIX_NONE):
			gender_from_category = models.string2gender(category)
			if ( (settings['category_prefix'] == CATEGORY_PREFIX_RUS_SOME) and (gender_from_category == models.GENDER_UNKNOWN) ) \
					or (settings['category_prefix'] == CATEGORY_PREFIX_RUS_ALL):
				category = (u'Ж' if (result.gender == models.GENDER_FEMALE) else u'М') + unicode(category)
			elif ( (settings['category_prefix'] == CATEGORY_PREFIX_ENG_SOME) and (gender_from_category == models.GENDER_UNKNOWN) ) \
					or (settings['category_prefix'] == CATEGORY_PREFIX_ENG_ALL):
				category = (u'F' if (result.gender == models.GENDER_FEMALE) else u'M') + unicode(category)
		if category:
			category_lower = category.lower()
			if category_lower not in category_lower_to_orig:
				category_sizes[category] = models.Category_size.objects.create(race=race, name=category)
				category_lower_to_orig[category_lower] = category
			result.category_size = category_sizes[category_lower_to_orig[category_lower]]
			# result.category = category

		if type2col[CELL_DATA_PLACE_CATEGORY] is not None:
			result.place_category_raw = row[type2col[CELL_DATA_PLACE_CATEGORY]]['number']
			if settings['use_places_from_protocol']:
				result.place_category = result.place_category_raw
		if type2col[CELL_DATA_COMMENT] is not None:
			result.comment = unicode(row[type2col[CELL_DATA_COMMENT]]['value'])[:models.MAX_RESULT_COMMENT_LENGTH]
		result.save()
		n_results_loaded += 1
		result.refresh_from_db()
		cur_split_sum = 0
		for col_index in range(ncols):
			if column_data_types[col_index] == CELL_DATA_SPLIT and row[col_index]['result']:
				if settings['cumulative_splits']:
					cur_split_sum += row[col_index]['result']
					split_value = cur_split_sum
				else:
					split_value = row[col_index]['result']
				split = models.Split.objects.create(result=result, distance=column_split_distances[col_index], 
					value=split_value)
				n_splits_loaded += 1
		# if deleted_links: # Now we try to recover killed links
		# 	result_tuple = (result.lname.lower(), result.fname.lower(), result.status, result.result)
		# 	deleted_link = deleted_links.pop(result_tuple, None)
		# 	if deleted_link:
		# 		if 'runner' in deleted_link:
		# 			result.runner = deleted_link['runner']
		# 		if 'user' in deleted_link:
		# 			result.user = deleted_link['user']
		# 		if 'klb_result' in deleted_link:
		# 			deleted_link['klb_result'].result = result
		# 			deleted_link['klb_result'].save()
		# 		result.save()
		# 		n_recovered_links += 1
		if n_deleted_links: # Now we try to recover killed links
			lost_result = race.lost_result_set.filter(
				lname=result.lname, fname=result.fname, status=result.status, result=result.result).first()
			if lost_result:
				result.runner = lost_result.runner
				result.user = lost_result.user
				result.save()
				n_recovered_links += 1
				lost_result.delete()
	race.loaded = models.RESULTS_SOME_OFFICIAL if settings['use_places_from_protocol'] else models.RESULTS_LOADED
	race.loaded_from = protocol.upload.name
	race.was_checked_for_klb = False
	race.save()
	models.Result.objects.filter(race=race, source=models.RESULT_SOURCE_KLB).delete()

	if settings['use_places_from_protocol']:
		race.category_size_set.all().update(size=None)
		reset_race_headers(race)
	else:
		fill_places(race)
		fill_race_headers(race)
	models.Table_update.objects.create(model_name=race.event.__class__.__name__, row_id=race.event.id, child_id=race.id,
		action_type=models.ACTION_RESULTS_LOAD, user=user, is_verified=models.is_admin(user)
	)
	generate_last_loaded_protocols()
	log_success(request, u'Загрузка завершена! Загружено результатов: {}{}{}.'.format(
		n_results_loaded, u', промежуточных результатов: ' if n_splits_loaded else u'', n_splits_loaded if n_splits_loaded else ''))
	if n_deleted_links:
		log_success(request, u'Восстановлено {} привязок результатов из {}.'.format(n_recovered_links, n_deleted_links))

def get_race(POST, races):
	race = None
	if 'new_race_id' in POST:
		race = races.filter(pk=POST['new_race_id']).first()
	elif 'race_id' in POST:
		race = races.filter(pk=POST['race_id']).first()
	if race is None:
		race = races.order_by('distance__distance_type', '-distance__length', 'precise_name').first()
	return race

def get_sheet_index(sheet_id, POST):
	if sheet_id:
		return models.int_safe(sheet_id)
	if 'new_sheet_index' in POST:
		return models.int_safe(POST['new_sheet_index'])
	elif 'sheet_index' in POST:
		return models.int_safe(POST['sheet_index'])
	return 0

@group_required('editors', 'admins')
def protocol_details(request, event_id=None, race_id=None, protocol_id=None, sheet_id=None):
	if event_id:
		event = get_object_or_404(models.Event, pk=event_id)
		race = None
	else:
		race = get_object_or_404(models.Race, pk=race_id)
		event = race.event
	context, has_rights, target = check_rights(request, event=event)
	context['allow_places_from_protocol'] = context['is_admin'] or (request.user.id in [395, ])
	if not has_rights:
		return target
	
	races = event.race_set
	if race is None:
		race = get_race(request.POST, races)
	if race is None:
		messages.warning(request, u'У выбранного забега нет ни одной дистанции. Сначала добавьте их.')
		return redirect(event)
	context['race'] = race
	context['event'] = event
	context['races'] = races.select_related('distance').order_by('distance__distance_type', '-distance__length', 'precise_name')
	wb_xls = None
	column_numbers = None
	n_splits = 0

	settings = {}
	settings['save_old_results'] = OLD_RESULTS_LEAVE_ALL
	settings['cumulative_splits'] = False
	settings['use_places_from_protocol'] = False
	settings['empty_means_DNS'] = False
	settings['category_prefix'] = CATEGORY_PREFIX_NONE

	protocols = event.get_xls_protocols()
	if protocol_id:
		protocol = get_object_or_404(protocols, pk=protocol_id)
	else:
		protocol = protocols.first()

	if not protocol:
		messages.warning(request, u'У выбранного забега нет ни одного подходящего протокола.')
		return redirect(event)
	context['protocols'] = protocols
	context['protocol'] = protocol

	path = protocol.upload.path
	extension = path.split(".")[-1].lower()
	if extension in ["xls", "xlsx", "xlsm"]:
		try:
			wb_xls = xlrd.open_workbook(path)
		except:
			messages.warning(request, u'Не получилось открыть файл {}: ошибка xlrd.'.format(path))
	else:
		messages.warning(request, u'Не получилось открыть файл {}: неизвестное расширение.'.format(path))

	if wb_xls:
		context['sheetnames'] = wb_xls.sheet_names()
		sheet_index = get_sheet_index(sheet_id, request.POST)
		context['sheet_index'] = sheet_index
		sheet = wb_xls.sheet_by_index(sheet_index)
		ncols = sheet.ncols
		if ncols > MAX_N_COLS:
			messages.warning(request, u'В протоколе целых {} столбцов! Это слишком много. Работаем с первыми {}'.format(ncols, MAX_N_COLS))
			ncols = MAX_N_COLS

		data = []
		max_nonempty_cells_number = 0
		max_nonempty_cells_index = 0
		for row_index in range(sheet.nrows):
			row = []
			nonempty_cells_number = 0
			for col_index in range(ncols):
				row.append(xlrd_cell2pair(sheet.cell(row_index,col_index), wb_xls.datemode))
				if sheet.cell_type(row_index,col_index) not in [xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK]:
					nonempty_cells_number += 1
			# row[0] = str(row_index) # + "(" + str(nonempty_cells_number) + ")"
			data.append(row)
			if nonempty_cells_number > max_nonempty_cells_number + 3:
				max_nonempty_cells_number = nonempty_cells_number
				max_nonempty_cells_index = row_index
		header_row = max_nonempty_cells_index
		column_data_types = [CELL_DATA_PASS] * ncols
		column_split_values = [0] * ncols
		column_numbers = [{'number': i} for i in range(ncols)]
		rows_with_results = [0] * sheet.nrows

		settings['show_gender_column'] = False
		settings['genders'] = [False] * sheet.nrows
		settings['show_category_column'] = False
		settings['categories'] = [''] * sheet.nrows
		settings['has_empty_results'] = False
		settings['show_category_prefix_choices'] = False

		to_update_rows = ('frmProtocol_update' in request.POST) or ('frmProtocol_submit' in request.POST)
		to_submit = ('frmProtocol_submit' in request.POST)
		if to_update_rows or 'new_race_id' in request.POST:
			for i in range(sheet.nrows):
				rows_with_results[i] = request.POST.get('count_row_' + str(i), 0)
			for i in range(ncols):
				column_data_types[i] = models.int_safe(request.POST.get('select_' + str(i), 0))
				column_split_values[i] = models.int_safe(request.POST.get('select_split_' + str(i), 0))
			header_row = models.int_safe(request.POST.get('header_row', 0))
			settings['save_old_results'] = models.int_safe(request.POST.get('save_old_results', OLD_RESULTS_LEAVE_ALL))
			settings['show_gender_column'] = models.int_safe(request.POST.get('show_gender_column', 0)) > 0
			if settings['show_gender_column']:
				for i in range(sheet.nrows):
					settings['genders'][i] = ('gender_row_' + str(i)) in request.POST
			settings['show_category_column'] = models.int_safe(request.POST.get('show_category_column', 0)) > 0
			if settings['show_category_column']:
				for i in range(sheet.nrows):
					settings['categories'][i] = request.POST.get('category_row_' + str(i), '').strip()
			settings['cumulative_splits'] = 'cumulative_splits' in request.POST
			if models.int_safe(request.POST.get('empty_means', 0)) == models.STATUS_DNS:
				settings['empty_means_DNS'] = True
			settings['use_places_from_protocol'] = 'use_places_from_protocol' in request.POST
			settings['show_category_prefix_choices'] = 'category_prefix' in request.POST
			if settings['show_category_prefix_choices']:
				settings['category_prefix'] = models.int_safe(request.POST.get('category_prefix', CATEGORY_PREFIX_NONE))
		else: # default values
			for i in range(header_row + 1, sheet.nrows):
				rows_with_results[i] = 1
		if (not any(column_data_types)) or ( (not to_submit) and (u'refresh_row_headers' in request.POST) ):
			column_data_types, column_split_values = default_data_types(
				request, data, header_row, race.distance, column_data_types, column_split_values)
		for i in range(ncols):
			if column_split_values[i]:
				n_splits += 1

		if to_update_rows:
			# Are column types OK?
			type2col, split2col, column_types_ok = process_column_types(request, race, column_data_types, column_split_values)
			# Are data in all important columns OK?
			data, n_parse_errors, n_parse_warnings, column_numbers, settings = process_cell_values(
				race, rows_with_results, wb_xls.datemode, data, column_data_types, column_numbers, type2col, settings)
			context['n_parse_errors'] = n_parse_errors
			context['n_parse_warnings'] = n_parse_warnings
			context['ok_to_import'] = column_types_ok and (n_parse_errors == 0)
			if column_types_ok:
				if (not settings['show_gender_column']) and (type2col[CELL_DATA_GENDER] is None):
					settings['show_gender_column'] = True
					column_types_ok = False
					if type2col[CELL_DATA_CATEGORY] is None:
						messages.warning(request, u'В протоколе нет столбца с полом. Этот столбец добавлен автоматически. '
							+ u'Отметьте галочки в строках с женщинами.')
					else:
						for i in range(sheet.nrows):
							settings['genders'][i] = \
								models.string2gender(data[i][type2col[CELL_DATA_CATEGORY]]['value']) == models.GENDER_FEMALE
						messages.warning(request, u'В протоколе нет столбца с полом. Этот столбец добавлен автоматически. '
							+ u'Мы попытались заполнить его, исходя из столбца «Группа»; проверьте, что получилось.')
				if (not settings['show_category_column']) and (type2col[CELL_DATA_CATEGORY] is None):
					settings['show_category_column'] = True
					column_types_ok = False
					messages.warning(request, u'В протоколе нет столбца с категорией. Этот столбец добавлен автоматически. '
						+ u'Если хотите, заполните его.')
				if (not settings['show_category_prefix_choices']) and settings['has_categories_for_both_genders']:
					settings['show_category_prefix_choices'] = True
					messages.warning(request, u'Есть одинаковые группы у мужчин и у женщин. Вы можете указать, приписать ли '
						+ u'к названиям групп буквы, обозначающие пол.')

			if column_types_ok and (n_parse_errors == 0):
				if to_submit:
					load_protocol(request, race, protocol, data, rows_with_results, column_data_types,
						column_split_values, type2col, settings)
					if (races.count() == 1) and (not protocol.is_processed):
						protocol.mark_processed(request.user, comment=u'Автоматически при загрузке единственной дистанции')
						messages.success(request, u'Протокол помечен как полностью обработанный. Отлично!')
					# return render(request, "editor/protocol_details.html", context)
				else:
					messages.success(request, u'Все проверки пройдены, можно загружать!')

		context['column_data_types'] = [
			{'value': column_data_types[i], 'split': column_split_values[i]}
			for i in range(ncols)
		]
		context['used_rows'] = set([i for i in range(len(column_data_types)) if (column_data_types[i] != CELL_DATA_PASS)])
		context['data'] = [{'checked': rows_with_results[i], 'data': data[i],
			'gender': settings['genders'][i], 'category': settings['categories'][i]} for i in range(sheet.nrows)]
		context['header_row'] = header_row
		if settings['has_empty_results']:
			context['has_empty_results'] = settings['has_empty_results']
			context['STATUS_DNF'] = models.STATUS_DNF
			context['STATUS_DNS'] = models.STATUS_DNS
			context['empty_means_DNS'] = settings['empty_means_DNS']
	
		context['column_numbers'] = column_numbers
		context['cell_data_choices'] = CELL_DATA_CHOICES
		context['show_gender_column'] = settings['show_gender_column']
		context['show_category_column'] = settings['show_category_column']
		context['save_old_results'] = settings['save_old_results']
		context['use_places_from_protocol'] = settings['use_places_from_protocol']
		if n_splits >= 2:
			context['show_cumulative_splits'] = True
			context['cumulative_splits'] = settings['cumulative_splits']
		if settings['show_category_prefix_choices']:
			context['show_category_prefix_choices'] = settings['show_category_prefix_choices']
			context['CATEGORY_PREFIXES'] = CATEGORY_PREFIXES
			context['category_prefix'] = settings['category_prefix']
	context['page_title'] = u'Обработка протокола'
	context['distances'] = models.Distance.objects.filter(distance_type=race.distance.distance_type).order_by('-popularity_value', 'length')
	return render(request, "editor/protocol_details.html", context)

def process_protocol(race_id=None, protocol_id=None, sheet_index=None, settings={},
		header_row=None, column_data_types=None, column_split_values=None, rows_with_results=None, errors_limit=5):
	race = models.Race.objects.filter(pk=race_id).first()
	if race:
		print u'Работаем с забегом {}, дистанцией {} (id {}).'.format(race.event, race, race.id)
	else:
		print u'Не найдена дистанция с id', race_id
		return False
	event = race.event
	wb_xls = None

	protocols = event.get_xls_protocols()
	print u'Подходящие протоколы у дистанции:'
	for protocol in protocols:
		print u'{}, id {}'.format(protocol.upload.path, protocol.id)
	if protocol_id:
		protocol = protocols.get(pk=protocol_id)
		if not protocol:
			print u'Протокол с id {} не найден или имеет неправильный формат.'.format(protocol_id)
			return False
	else:
		protocol = protocols.first()
		if not protocol:
			print u'У выбранного забега нет ни одного подходящего протокола.'
			return False

	print u'Работаем с протоколом {}, id {}.'.format(protocol.upload.path, protocol.id)
	try:
		wb_xls = xlrd.open_workbook(protocol.upload.path)
	except:
		print u'Не получилось открыть файл протокола: ошибка xlrd.'
		return False

	sheetnames = wb_xls.sheet_names()
	print u'Листы в протоколе:'
	for i in range(len(sheetnames)):
		print u'№ {}: {}'.format(i, sheetnames[i])
	sheet_index = sheet_index if (sheet_index and (0 <= sheet_index < len(sheetnames))) else 0
	sheet = wb_xls.sheet_by_index(sheet_index)
	print u'Работаем с листом «{}», № {}.'.format(sheetnames[sheet_index], sheet_index)

	nrows = sheet.nrows
	ncols = sheet.ncols
	if ncols > MAX_N_COLS:
		print u'В протоколе целых {} столбцов! Это слишком много. Работаем с первыми {}'.format(ncols, MAX_N_COLS)
		ncols = MAX_N_COLS

	data = []
	max_nonempty_cells_number = 0
	max_nonempty_cells_index = 0
	for row_index in range(nrows):
		row = []
		nonempty_cells_number = 0
		for col_index in range(ncols):
			row.append(xlrd_cell2pair(sheet.cell(row_index,col_index), wb_xls.datemode))
			if sheet.cell_type(row_index,col_index) not in [xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK]:
				nonempty_cells_number += 1
		# row[0] = str(row_index) # + "(" + str(nonempty_cells_number) + ")"
		data.append(row)
		if nonempty_cells_number > max_nonempty_cells_number + 3:
			max_nonempty_cells_number = nonempty_cells_number
			max_nonempty_cells_index = row_index
	print u'Размер листа: {} строк, {} столбцов.'.format(len(data), len(data[0]) if data else 0)

	if 'save_old_results' not in settings:
		settings['save_old_results'] = OLD_RESULTS_LEAVE_ALL
	if 'cumulative_splits' not in settings:
		settings['cumulative_splits'] = False
	if 'use_places_from_protocol' not in settings:
		settings['use_places_from_protocol'] = False
	if 'empty_means_DNS' not in settings:
		settings['empty_means_DNS'] = False
	if 'category_prefix' not in settings:
		settings['category_prefix'] = CATEGORY_PREFIX_NONE
	if 'genders' not in settings:
		settings['genders'] = None
	if 'categories' not in settings:
		settings['categories'] = [''] * nrows
	settings['show_gender_column'] = False
	settings['show_category_column'] = False

	if header_row is None:
		header_row = max_nonempty_cells_index
	print u'Строка с заголовком таблицы: {}.'.format(header_row)
	if column_data_types is None:
		column_data_types = [CELL_DATA_PASS] * ncols
		column_split_values = [0] * ncols
		column_data_types, column_split_values = default_data_types(None, data, header_row, race.distance,
			column_data_types, column_split_values)
	if column_split_values is None:
		column_split_values = [0] * ncols
		column_split_distances = [None] * ncols
	else:
		column_split_distances = [models.Distance.objects.filter(pk=val).first() for val in column_split_values]
	print u'Типы и заголовки столбцов:'
	for i, data_type in enumerate(column_data_types):
		print u'{} ({}): {}'.format(i, data[header_row][i]['value'], CELL_DATA_CHOICES[data_type]),
		if data_type == CELL_DATA_SPLIT:
			print column_split_distances[i].name,
		print ''
	if rows_with_results is None:
		rows_with_results = [0] * nrows
		for i in range(header_row + 1, nrows):
			rows_with_results[i] = 1
	print u'Обрабатываем диапазоны строк:'
	cur_segment_start = -1
	for i in range(nrows):
		if rows_with_results[i]:
			if cur_segment_start < 0:
				cur_segment_start = i
		else:
			if cur_segment_start >= 0:
				print u'Строки {}-{}'.format(cur_segment_start, i - 1)
				cur_segment_start = -1
	if rows_with_results[-1]:
		print u'Строки {}-{}'.format(cur_segment_start, nrows - 1)

	# Are column types OK?
	type2col, split2col, column_types_ok = process_column_types(None, race, column_data_types, column_split_values)
	# Are data in all important columns OK?
	column_numbers = [{'number': i} for i in range(ncols)]
	data, n_parse_errors, n_parse_warnings, column_numbers, settings = process_cell_values(
		race, rows_with_results, wb_xls.datemode, data, column_data_types, column_numbers, type2col, settings)
	print u'Всего ошибок:', n_parse_errors
	print u'Всего предупреждений:', n_parse_warnings
	ok_to_import = column_types_ok and (n_parse_errors == 0)
	if column_types_ok:
		if (settings['genders'] is None) and (type2col[CELL_DATA_GENDER] is None):
			if settings['try_get_gender_from_group'] and not (type2col[CELL_DATA_CATEGORY] is None):
				print u'Пол в протоколе не указан. Пробуем извлечь его из столбца с группой...'
				settings['genders'] = [False] * nrows
				gender_guessed = 0
				gender_not_guessed = 0
				for i in range(nrows):
					if rows_with_results[i]:
						gender = models.string2gender(data[i][type2col[CELL_DATA_CATEGORY]]['value'])
						if gender == models.GENDER_UNKNOWN:
							gender_not_guessed += 1
						else:
							gender_guessed += 1
						settings['genders'][i] = (gender == models.GENDER_FEMALE)
				print (u'Получилось понять пол у {} строк. Не получилось — у {} строк. ' +
					u'Вы можете также передать как параметр массив settings["genders"]').format(gender_guessed, gender_not_guessed)
			elif settings['all_are_male']:
				print u'Пол в протоколе не указан. Считаем всех мужчинами'
				settings['genders'] = [False] * nrows
			elif settings['all_are_female']:
				print u'Пол в протоколе не указан. Считаем всех женщинами'
				settings['genders'] = [True] * nrows
			else:
				print u'Ошибка: вы не указали пол спортсменов!'
				column_types_ok = False
		if (settings['categories'] is None) and (type2col[CELL_DATA_CATEGORY] is None):
			print u'Ошибка: вы не указали группы спортсменов!'
			column_types_ok = False

	if not column_types_ok:
		return False
	for col_index in range(ncols):
		if 'errors' in column_numbers[col_index]:
			errors_total = column_numbers[col_index]['errors']
			errors_printed = 0
			print u'Столбец {} ({}): {} ошибок. Первые из них:'.format(
				col_index, data[header_row][col_index]['value'], errors_total)
			for row_index in range(nrows):
				if 'error' in data[row_index][col_index]:
					print u'({}, {}): Значение «{}», ошибка «{}»'.format(row_index, col_index,
						data[row_index][col_index]['value'], data[row_index][col_index]['error'])
					errors_printed += 1
					if (errors_printed == errors_limit) or (errors_printed == errors_total):
						break
		if 'warnings' in column_numbers[col_index]:
			warnings_total = column_numbers[col_index]['warnings']
			warnings_printed = 0
			print u'Столбец {} ({}): {} предупреждений. Первые из них:'.format(
				col_index, data[header_row][col_index]['value'], warnings_total)
			for row_index in range(nrows):
				if 'warning' in data[row_index][col_index]:
					print u'({}, {}): Значение «{}», ошибка «{}»'.format(row_index, col_index,
						data[row_index][col_index]['value'], data[row_index][col_index]['warning'])
					warnings_printed += 1
					if (warnings_printed == errors_limit) or (warnings_printed == warnings_total):
						break
	if (n_parse_errors == 0):
		if settings['try_load']:
			print u'Все проверки пройдены, загружаем!'
			load_protocol(None, race, protocol, data, rows_with_results, column_data_types,
				column_split_values, type2col, settings)
		else:
			print u'Все проверки пройдены, можно загружать!'
	return True

@group_required('admins')
def events_for_result_import(request):
	context = {}
	context['page_title'] = u'Забеги с протоколами и без результатов'

	context['races_for_klb'] = []
	races_for_klb = models.Race.objects.filter(
		Q(distance__distance_type=models.TYPE_MINUTES) | Q(distance__distance_type=models.TYPE_METERS, distance__length__gte=10000),
		event__start_date__year=models.CUR_KLB_YEAR,
		was_checked_for_klb=False,
		loaded=models.RESULTS_LOADED).select_related('event', 'distance').order_by('event__start_date')[:50]
	for race in races_for_klb:
		if (race.get_klb_status() == models.KLB_STATUS_OK) and not race.klb_result_set.filter(result=None).exists():
			context['races_for_klb'].append(race)
			if len(context['races_for_klb']) >= 10:
				break

	protocols = models.Document.objects.filter(models.Q_IS_XLS_FILE,
		document_type__in=models.DOC_PROTOCOL_TYPES, event__isnull=False, is_processed=False)
	event_ids = set(protocols.values_list('event__id', flat=True))
	events_raw = models.Event.objects.filter(
		id__in=event_ids, start_date__lte=datetime.date.today() - datetime.timedelta(days=7)).prefetch_related(
		Prefetch('race_set',queryset=models.Race.objects.select_related(
			'distance').annotate(Count('result')).order_by('distance__distance_type', '-distance__length')),
		Prefetch('document_set',queryset=models.Document.objects.filter(models.Q_IS_XLS_FILE, document_type__in=models.DOC_PROTOCOL_TYPES))
		).order_by('-start_date')
	events = []
	for event in events_raw:
		if len(events) >= 50:
			break
		if event.race_set.filter(loaded=models.RESULTS_NOT_LOADED).exists() and event.document_set.exists():
			events.append(event)
	context['events'] = events
	countries = ('RU', 'BY', 'UA')
	context['large_races'] = models.Race.objects.filter(
		Q(event__city__region__country_id__in=countries) | Q(event__series__city__region__country_id__in=countries),
		loaded=models.RESULTS_NOT_LOADED).select_related('event', 'distance').order_by('-n_participants')[:20]

	return render(request, "editor/events_for_result_import.html", context)

@group_required('editors', 'admins')
def protocol_mark_processed(request, protocol_id):
	protocol = get_object_or_404(models.Document, models.Q_IS_XLS_FILE, document_type__in=models.DOC_PROTOCOL_TYPES, event__isnull=False, pk=protocol_id)
	event = protocol.event
	context, has_rights, target = check_rights(request, event=event)
	if not has_rights:
		return target
	if protocol.is_processed:
		messages.warning(request, u'Этот протокол уже был помечен как полностью обработанный.')
	else:
		protocol.mark_processed(request.user)
		messages.success(request, u'Протокол помечен как полностью обработанный. Отлично!')
	return redirect(event.get_protocol_details_url(protocol=protocol))
