# -*- coding: utf-8 -*-
from django.contrib.auth.models import Group
from django.core.urlresolvers import reverse
from django.db.models import Count
from django.db.models import Q
from django import forms
import datetime
import os
import re

import models
import results_util

def validate_email(value):
	if value and not models.is_email_correct(value):
		raise forms.ValidationError(u'Некорректный адрес электронной почты')
def validate_phone_number(value):
	if value and not models.is_phone_number_correct(value):
		raise forms.ValidationError(u'Некорректный номер телефона. Номер должен начинаться на 8 или на +, чтобы мы могли позвонить по нему из России')

class CustomDateInput(forms.widgets.TextInput):
	input_type = 'date'
class CustomDateTimeInput(forms.widgets.TextInput):
	input_type = 'datetime'
class CustomTimeInput(forms.widgets.TextInput):
	input_type = 'time'
class UserModelChoiceField(forms.ModelChoiceField):
	def label_from_instance(self, obj):
		 return obj.get_full_name()

class CustomClearableFileInput(forms.widgets.ClearableFileInput):
	template_with_initial = (
		u'%(initial_text)s: <a href="%(initial_url)s">%(initial)s</a> '
		u'%(clear_template)s<br />%(input_text)s: %(input)s'
	)
	template_with_clear = u'%(clear)s <label for="%(clear_checkbox_id)s">%(clear_checkbox_label)s</label>'

class ModelFormWithCity(forms.ModelForm):
	city_id = forms.CharField(
		label=u"Город",
		required=False,
		widget=forms.Select(choices=[]))
	def clean(self):
		cleaned_data = super(ModelFormWithCity, self).clean()
		city_id = cleaned_data.get("city_id")
		cleaned_data['city'] = models.City.objects.filter(pk=city_id).first() if city_id else None
		self.instance.city = cleaned_data['city']
		return cleaned_data

class FormWithCity(forms.Form):
	city_id = forms.CharField(
		label=u"Город",
		required=False,
		widget=forms.Select(choices=[]))
	def __init__(self, *args, **kwargs):
		city_required = kwargs.pop('city_required', False)
		super(FormWithCity, self).__init__(*args, **kwargs)
		if city_required:
			self.fields['city_id'].required = True
	def clean(self):
		cleaned_data = super(FormWithCity, self).clean()
		city_id = cleaned_data.get("city_id")
		cleaned_data['city'] = models.City.objects.filter(pk=city_id).first() if city_id else None
		return cleaned_data

class RoundedFieldsForm(forms.Form):
	def __init__(self, *args, **kwargs):
		super(RoundedFieldsForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			self.fields[field].widget.attrs.update({'class': 'form-control'})

class RoundedFieldsModelForm(forms.ModelForm):
	def __init__(self, *args, **kwargs):
		super(RoundedFieldsModelForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			widget = self.fields[field].widget
			if widget.__class__.__name__ not in ('RadioSelect', 'RadioSelectWithoutUl', 'CheckboxInput', 'CheckboxSelectMultiple'):
				widget.attrs.update({'class': 'form-control'})

def get_region_choices_for_participants_list(participants):
	region_ids = set(participants.values_list('klb_person__city__region_id', flat=True).distinct())
	return [
				(country.name, 
					[(region['id'], region['name_full'])
						for region in country.region_set.filter(active=True, pk__in=region_ids).order_by('name').values('id', 'name_full')
					]
				)
				for country in models.Country.objects.filter(value__lt=models.DEFAULT_COUNTRY_SORT_VALUE).order_by('value', 'name')
			]

def get_country_choices_for_participants_list(participants):
	country_ids = set(participants.values_list('klb_person__city__region__country_id', flat=True).distinct())
	return [(country['id'], country['name'])
		for country in models.Country.objects.filter(pk__in=country_ids).order_by('name').values('id', 'name')
	]

CHOICES_REGIONS_BY_COUNTRY = []
for country in models.Country.objects.filter(value__lt=models.DEFAULT_COUNTRY_SORT_VALUE).order_by('value', 'name'):
	CHOICES_REGIONS_BY_COUNTRY.append((
		country.name, 
		[(region['id'], region['name_full'])
			for region in country.region_set.filter(active=True).order_by('name').values('id', 'name_full')]
	))

CHOICES_OTHER_COUNTRIES = [(region['id'], region['name_full'])
	for region in models.Region.objects.filter(country__value=models.DEFAULT_COUNTRY_SORT_VALUE).order_by('name').values('id', 'name_full')
]
class RegionOrCountryField(forms.ChoiceField):
	def __init__(self, *args, **kwargs):
		if 'label' not in kwargs:
			kwargs['label'] = u'Регион (для России, Украины, Беларуси) или страна'
		if 'required' not in kwargs:
			kwargs['required'] = False
		super(RegionOrCountryField, self).__init__(*args, **kwargs)
		self.choices = [('', u'Не выбран')] + CHOICES_REGIONS_BY_COUNTRY + CHOICES_OTHER_COUNTRIES
	def clean(self, value):
		if value:
			value = super(RegionOrCountryField, self).clean(value)
			return models.Region.objects.filter(pk=value).first()
		if self.required:
			raise forms.ValidationError(u'Пожалуйста, выберите регион или страну')
		return None

class UserProfileForm(ModelFormWithCity):
	lname = forms.CharField(
		label=u'Фамилия',
		max_length=100,
		widget=forms.TextInput(attrs={'size': 30}),
		required=True)
	fname = forms.CharField(
		label=u'Имя',
		max_length=100,
		widget=forms.TextInput(attrs={'size': 30}),
		required=True)
	email = forms.EmailField(
		label=u'Адрес электронной почты',
		max_length=200,
		widget=forms.EmailInput(attrs={'size': 30}),
		required=True)
	is_new_city = forms.BooleanField(
		label=u'Моего города нет в списке (в таком случае заполните форму ниже)',
		required=False)
	region = RegionOrCountryField()
	new_city = forms.CharField(
		label=u'Название города',
		max_length=100,
		required=False)
	user = None
	def __init__(self, *args, **kwargs):
		city = kwargs.pop('city')
		self.user = kwargs.pop('user')

		initial = kwargs.get('initial', {})
		initial['lname'] = self.user.last_name
		initial['fname'] = self.user.first_name
		initial['email'] = self.user.email
		if city:
			initial['region'] = city.region.id
		kwargs['initial'] = initial
		super(UserProfileForm, self).__init__(*args, **kwargs)
		if self.instance.is_agree_with_policy:
			self.fields['is_agree_with_policy'].widget = forms.HiddenInput()
		else:
			self.fields['is_agree_with_policy'].required = True
	def clean_email(self):
		email = self.cleaned_data.get('email', '')
		validate_email(email)
		return email
	def clean_phone_number(self):
		phone_number = self.cleaned_data.get('phone_number', '')
		validate_phone_number(phone_number)
		return phone_number
	def clean_birthday(self):
		birthday = self.cleaned_data.get('birthday')
		if birthday and (birthday >= datetime.date.today()):
			raise forms.ValidationError(u'Вы указали дату рождения в будущем')
		return birthday
	def clean(self):
		cleaned_data = super(UserProfileForm, self).clean()
		if cleaned_data['gender'] == models.GENDER_UNKNOWN:
			raise forms.ValidationError(u'Пожалуйста, укажите Ваш пол')
		avatar = cleaned_data.get('avatar', None)
		if (avatar == False) and self.instance.avatar:
			if os.path.isfile(self.instance.avatar.path):
				self.instance.avatar.delete(False)
			if os.path.isfile(self.instance.avatar_thumb.path):
				self.instance.avatar_thumb.delete(False)
		if cleaned_data.get("is_new_city"):
			region = cleaned_data.get("region")
			new_city = cleaned_data.get("new_city")
			if not region:
				raise forms.ValidationError(u'Город не сохранён. Укажите страну или регион.')
			if cleaned_data.get("new_city").strip() == "":
				raise forms.ValidationError(u'Город не сохранён. Название города не может быть пустым.')
			city = models.City.objects.filter(region=region, name=new_city).first()
			if not city:
				city = models.City.objects.create(region=region, name=new_city, created_by=self.user)
				models.log_obj_create(self.user, city, action=models.ACTION_CREATE, field_list=['region', 'name', 'created_by'])
			self.instance.city = city
	class Meta:
		model = models.User_profile
		fields = ['email', 'lname', 'fname', 'midname', 'gender', 'club', 'birthday', 'club_name', 'phone_number',
			'is_new_city', 'region', 'city_id', 'new_city', 'is_public', 'ok_to_send_news', 'ok_to_send_results', 'avatar', 'is_agree_with_policy',
			'strava_account', 'hide_parkruns_in_calendar',
			]
		labels = {
			'city_id': u'Город',
			'phone_number': u'Номер телефона (будем использовать только для экстренных случаев и регистрации в КЛБМатч)',
		}
		widgets = {
			'avatar': CustomClearableFileInput(),
			'birthday': CustomDateInput(),
			'midname': forms.TextInput(attrs={'size': 30}),
			'strava_account': forms.NumberInput(attrs={'size': 30}),
			'club_name': forms.TextInput(attrs={'size': 30}),
			'phone_number': forms.TextInput(attrs={'size': 30}),
		}

class UserNameForm(forms.ModelForm):
	def clean_lname(self):
		return self.cleaned_data.get('lname', '').strip().title()
	def clean_fname(self):
		return self.cleaned_data.get('fname', '').strip().title()
	def clean_midname(self):
		return self.cleaned_data.get('midname', '').strip().title()
	def clean_comment(self):
		return self.cleaned_data.get('comment', '').strip()
	def clean(self):
		cleaned_data = super(UserNameForm, self).clean()
		lname = cleaned_data['lname']
		fname = cleaned_data['fname']
		midname = cleaned_data['midname']
		comment = cleaned_data['comment']
		if self.instance.runner.extra_name_set.filter(lname=lname, fname=fname, midname=midname).exists():
			raise forms.ValidationError(u'Вы уже добавляли точно такое же имя.')
	class Meta:
		model = models.Extra_name
		fields = ['lname', 'fname', 'midname', 'comment']

class PaginateForm(FormWithCity):
	country = forms.ModelChoiceField(
		label=u"Страна",
		queryset=models.Country.objects.annotate(num_events=Count('series')+Count('event')).filter(num_events__gt=0).order_by('value', 'name'),
		empty_label="(любая)",
		required=False)
	region = forms.ModelChoiceField(
		label=u"Или регион (для России, Украины, Беларуси)",
		queryset=models.Region.objects.filter(active=1).order_by('name'),
		empty_label="(любой)",
		required=False)

DATE_REGION_ALL = 0
DATE_REGION_PAST = 1
DATE_REGION_FUTURE = 2
DATE_REGION_NEXT_WEEK = 3
DATE_REGION_NEXT_MONTH = 4
DATE_REGION_DEFAULT = DATE_REGION_ALL
class EventForm(PaginateForm):
	race_name = forms.CharField(
		label=u'Название забега или часть названия',
		# widget=forms.TextInput(attrs={'style': 'width:99%;'}),
		max_length=100,
		required=False)
	date_region = forms.ChoiceField(
		label=u'Когда',
		choices=(
			(DATE_REGION_ALL, u'в прошлом и в будущем'),
			(DATE_REGION_FUTURE, u'сегодня и позже'),
			(DATE_REGION_PAST, u'сегодня и раньше'),
			(DATE_REGION_NEXT_WEEK, u'в ближайшую неделю'),
			(DATE_REGION_NEXT_MONTH, u'в ближайший месяц'),
		),
		initial=DATE_REGION_DEFAULT)
	date_from = forms.DateField(
		label=u"Не раньше",
		widget=CustomDateInput,
		required=False)
	date_to = forms.DateField(
		label=u"Не позже",
		widget=CustomDateInput,
		required=False)
	distance_from = forms.DecimalField(
		label=u"Дистанция не меньше (км)",
		min_value=0.,
		max_digits=8,
		decimal_places=3,
		required=False)
	distance_to = forms.DecimalField(
		label=u"Не больше (км)",
		min_value=0.,
		max_digits=8,
		decimal_places=3,
		required=False)
	hide_parkruns = forms.BooleanField(
		label=u"Скрыть забеги parkrun",
		required=False)
	only_with_results = forms.BooleanField(
		label=u"Только забеги с уже загруженными результатами",
		required=False)
	def __init__(self, *args, **kwargs):
		super(EventForm, self).__init__(*args, **kwargs)
		self.label_suffix = ''
		self.order_fields(['date_region', 'country', 'region', 'city_id', 'race_name',
			'date_from', 'date_to', 'distance_from', 'distance_to', 'hide_parkruns'])
	def clean(self):
		cleaned_data = super(EventForm, self).clean()
		if (cleaned_data.get('date_from')) and cleaned_data['date_from'] < models.DATE_MIN:
			cleaned_data['date_from'] = models.DATE_MIN
		if cleaned_data.get('date_to'):
			if cleaned_data['date_to'] < models.DATE_MIN:
				cleaned_data['date_to'] = models.DATE_MIN
			elif cleaned_data['date_to'] > models.DATE_MAX:
				cleaned_data['date_to'] = models.DATE_MAX
		return cleaned_data

class RunnerForm(RoundedFieldsForm):
	lname = forms.CharField(
		max_length=100,
		widget=forms.TextInput(attrs={'placeholder': u'Фамилия'}),
		required=False)
	fname = forms.CharField(
		max_length=100,
		widget=forms.TextInput(attrs={'placeholder': u'Имя'}),
		required=False)
	birthday_from = forms.DateField(
		label=u"Родился не раньше",
		widget=CustomDateInput,
		required=False)
	birthday_to = forms.DateField(
		label=u"не позже",
		widget=CustomDateInput,
		required=False)
	is_user = forms.BooleanField(
		label=u"Зарегистрирован на сайте",
		required=False)
	is_in_klb = forms.BooleanField(
		label=u"Участник КЛБМатча",
		required=False)
	# is_ak_person = forms.BooleanField(
	# 	label=u"Есть в базе АК55",
	# 	required=False)
	is_in_parkrun = forms.BooleanField(
		label=u"Есть parkrun id",
		required=False)

class ResultForm(PaginateForm):
	race_name = forms.CharField(
		label=u'Название забега или часть названия',
		max_length=100,
		required=False)
	date_from = forms.DateField(
		label=u"Не раньше",
		widget=CustomDateInput,
		required=False)
	date_to = forms.DateField(
		label=u"Не позже",
		widget=CustomDateInput,
		required=False)
	distance_from = forms.IntegerField(
		label=u"Дистанция не меньше (км)",
		min_value=0,
		required=False)
	distance_to = forms.IntegerField(
		label=u"Не больше (км)",
		min_value=0,
		required=False)
	result_from = forms.IntegerField(
		label=u"Результат не меньше (сек)",
		min_value=0,
		required=False)
	result_to = forms.IntegerField(
		label=u"Не больше (сек)",
		min_value=0,
		required=False)
	lname = forms.CharField(
		label=u'Фамилия',
		max_length=100,
		required=False)
	fname = forms.CharField(
		label=u'Имя',
		max_length=100,
		required=False)
	midname = forms.CharField(
		label=u'Отчество',
		max_length=100,
		required=False)
	club = forms.CharField(
		label=u'Клуб',
		max_length=100,
		required=False)
	disconnected = forms.BooleanField(
		label=u"Не привязанные к людям",
		required=False)
	def __init__(self, *args, **kwargs):
		super(ResultForm, self).__init__(*args, **kwargs)
		self.order_fields(['country', 'region', 'city_id', 'race_name',
			'date_from', 'date_to', 'distance_from', 'distance_to',
			'result_from', 'result_to', 'lname', 'fname', 'midname', 'club', 'disconnected'])

class ResultFilterForm(forms.Form):
	name = forms.CharField(
		label='',
		max_length=100,
		widget=forms.TextInput(attrs={'placeholder': u'Имя, клуб, результат'}),
		required=False)
	def __init__(self, race, *args, **kwargs):
		super(ResultFilterForm, self).__init__(*args, **kwargs)
		total_count = race.n_participants

		if race.loaded == models.RESULTS_LOADED:
			gender_choices = [('', u'Мужчины и женщины ({})'.format(race.n_participants))]
			if race.n_participants_men:
				gender_choices.append((2, u'Мужчины ({})'.format(race.n_participants_men)))
			n_participants_women = race.get_n_participants_women()
			if n_participants_women:
				gender_choices.append((1, u'Женщины ({})'.format(n_participants_women)))
		else:
			gender_choices = [('', u'Мужчины и женщины'), ('2', u'Мужчины'), ('1', u'Женщины')]
		self.fields['gender'] = forms.ChoiceField(
			choices=gender_choices,
			required=False
		)

		if race.loaded == models.RESULTS_LOADED:
			category_choices = [('', u'Все группы ({})'.format(total_count))]
			for category_size in race.category_size_set.filter(size__gt=0).order_by('name'):
				category_choices.append((category_size.id, u'{} ({})'.format(category_size.name, category_size.size)))
		else:
			category_choices = [('', u'Все группы')]
			for category_size in race.category_size_set.order_by('name'):
				category_choices.append((category_size.id, category_size.name))
		if len(category_choices) > 1:
			self.fields['category'] = forms.ChoiceField(
				choices=category_choices,
				required=False
			)

class RunnerResultFilterForm(forms.Form):
	name = forms.CharField(
		label='',
		max_length=100,
		widget=forms.TextInput(attrs={'placeholder': u'Название'}),
		required=False)
	def __init__(self, results, *args, **kwargs):
		super(RunnerResultFilterForm, self).__init__(*args, **kwargs)
		total_count = results.count()
		all_series = {}
		distances = {}
		for result in results: # race__event__series should be in select_related
			series = result.race.event.series
			if series.id in all_series:
				all_series[series.id]['count'] += 1
			else:
				all_series[series.id] = {'name': series.name, 'count': 1}
			distance = result.race.distance
			if distance.id in distances:
				distances[distance.id]['count'] += 1
			else:
				distances[distance.id] = {'name': distance.name, 'count': 1}
		series_choices = [('', u'Все серии ({})'.format(total_count))]
		for id, values in sorted(all_series.items(), key=lambda x: (-x[1]['count'], x[1]['name'])):
			series_choices.append((id, u'{} ({})'.format(values['name'], values['count'])))
		self.fields['series'] = forms.ChoiceField(
			choices=series_choices,
			required=False
		)
		distance_choices = [('', u'Все дистанции ({})'.format(total_count))]
		for id, values in sorted(distances.items(), key=lambda x: (-x[1]['count'], x[1]['name'])):
			distance_choices.append((id, u'{} ({})'.format(values['name'], values['count'])))
		self.fields['distance'] = forms.ChoiceField(
			choices=distance_choices,
			required=False
		)

# When going to add series for some editor
class SeriesEditorForm(forms.Form):
	series_id = forms.IntegerField(
		label=u"id серии для редактирования",
		min_value=1,
		required=True)

# When searching through all series list
class NewsSearchForm(FormWithCity):
	country = forms.ModelChoiceField(
		label=u"Страна",
		queryset=models.Country.objects.annotate(num_events=Count('series')).filter(num_events__gt=0).order_by('value', 'name'),
		empty_label="(любая)",
		required=False)
	region = forms.ModelChoiceField(
		label=u"Регион",
		queryset=models.Region.objects.filter(active=1).order_by('name'),
		empty_label="(любой)",
		required=False)
	news_text = forms.CharField(
		label=u'Часть текста или названия',
		max_length=100,
		required=False)
	published_by_me = forms.BooleanField(
		label=u"Созданные мной",
		required=False)
	date_from = forms.DateField(
		label=u"Не раньше",
		widget=CustomDateInput,
		required=False)
	date_to = forms.DateField(
		label=u"Не позже",
		widget=CustomDateInput,
		required=False)

class MessageToInfoForm(RoundedFieldsModelForm):
	def __init__(self, request, *args, **kwargs):
		self.user = request.user
		initial = kwargs.get('initial', {})
		initial['page_from'] = request.get_full_path()[:255]
		if request.user.is_authenticated():
			initial['sender_name'] = request.user.first_name + ' ' + request.user.last_name
			initial['sender_email'] = request.user.email
		if 'advert' in request.GET:
			advert = models.int_safe(request.GET['advert'])
			if advert == 1:
				initial['title'] = u'Рекламное место на странице календаря забегов'
			if advert == 2:
				initial['title'] = u'Оплата через сайт'
		elif 'runner' in request.GET:
			runner = models.Runner.objects.filter(pk=request.GET['runner']).first()
			if runner:
				initial['title'] = runner.name_with_midname()
		elif 'event_id' in request.GET:
			event = models.Event.objects.filter(pk=request.GET['event_id']).first()
			if event:
				initial['title'] = u'Ошибка на странице забега {} ({})'.format(event.name, event.dateFull().replace('&nbsp;', ' '))
				initial['body'] = u'\n\nСтраница забега: {}{}'.format(models.SITE_URL, event.get_absolute_url())
		kwargs['initial'] = initial
		super(MessageToInfoForm, self).__init__(*args, **kwargs)
	def clean_body(self):
		body = self.cleaned_data['body'].strip()
		if body == '':
			raise forms.ValidationError(u'Текст сообщения не может быть пустым.')
		return body
	def clean(self):
		cleaned_data = super(MessageToInfoForm, self).clean()
		if self.user.is_authenticated():
			self.instance.created_by = self.user
		cleaned_data['title'] = u'Письмо с base.probeg.org. Тема: {}'.format(cleaned_data['title'] if cleaned_data['title'] else u'(не указана)')
		cleaned_data['sender_name'] = cleaned_data['sender_name'] if cleaned_data['sender_name'] else u'(не указан)'
		if self.user.is_authenticated() and hasattr(self.user, 'user_profile'):
			user_page = models.SITE_URL + self.user.user_profile.get_absolute_url()
		else:
			user_page = ''
		cleaned_data['body'] = u'Отправитель: {} {}\nОбратный адрес: {}\n\n{}'.format(
				cleaned_data['sender_name'],
				user_page,
				(cleaned_data['sender_email'] if cleaned_data['sender_email'] else u'(не указан)'),
				cleaned_data['body'] if ('body' in cleaned_data) else u'(сообщение отправлено пустым)'
			)
		cleaned_data['sender_email'] = models.ROBOT_MAIL_HEADER
		# cleaned_data['sender_email'] = u'{} <{}>'.format(cleaned_data['sender_name'], cleaned_data['sender_email']) # Problems with DKIM
		self.instance.target_email = models.INFO_MAIL # 'alexey.chernov@gmail.com'
		return cleaned_data
	class Meta:
		model = models.Message_from_site
		fields = ['page_from', 'sender_name', 'sender_email', 'title', 'body', 'attachment']
		labels = {
			'sender_email': u'Ваш электронный адрес (на него мы отправим ответ)',
		}
		widgets = {
			'page_from': forms.HiddenInput,
			'sender_email': forms.EmailInput,
			'body': forms.Textarea(attrs={'rows': 6})
		}

def get_wrong_club_letter_text(table_update, event):
	res = ''
	user = table_update.user
	if table_update.is_for_klb and (table_update.model_name == 'Event') and (user != models.USER_ROBOT_CONNECTOR):
		year = event.start_date.year
		result = models.Result.objects.filter(pk=table_update.child_id, race__event=event).first()
		if result and models.is_active_klb_year(year):
			runner = result.runner
			if runner and runner.klb_person:
				klb_person = runner.klb_person
				team = klb_person.get_team(year)
				if team and result.club_name and not team.string_contains_team_or_club_name(result.club_name):
					res = u' {}, добрый день!'.format(user.first_name)
					if user == runner.user:
						res += u'\n\nСейчас в протоколе забега {}{} у Вас указан клуб «{}», '.format(models.SITE_URL,
							result.race.get_absolute_url(), result.club_name)
						if team.name == team.club.name:
							res += u'а клуб «{}» не упомянут.'.format(team.name)
						else:
							res += u'а ни команда «{}», ни клуб «{}» не упомянуты.'.format(team.name, team.club.name)
						res += u' Так что результат в зачёт КЛБМатча пока не идёт. В Ваш послужной список результат всё равно добавили: {}{}'.format(
							models.SITE_URL, user.user_profile.get_absolute_url())
						res += u'\n\nЕсли организаторы исправят клуб в протоколе, пришлите нам ссылку на него, и засчитаем результат в матч.'
					else:
						res += u'\n\nУ бегуна {}, участни{} команды «{}», в протоколе {}{} указан клуб «{}», '.format(runner.name(),
							u'ка' if runner.gender == models.GENDER_MALE else u'цы', team.name,
							models.SITE_URL, result.race.get_absolute_url(), result.club_name)
						if team.name == team.club.name:
							res += u'а клуб «{}» не упомянут.'.format(team.name)
						else:
							res += u'а ни команда «{}», ни клуб «{}» не упомянуты.'.format(team.name, team.club.name)
						res += u' Так что результат в зачёт КЛБМатча пока не идёт; результат к человеку всё равно привязали, '
						res += u'на {} странице {}{} он уже есть.'.format(u'его' if runner.gender == models.GENDER_MALE else u'её', models.SITE_URL,
							runner.get_runner_or_user_url())
						res += u'\n\nЕсли организаторы исправят клуб в протоколе, пришлите нам ссылку на него, и засчитаем результат в матч.'
						comment_field = table_update.field_update_set.filter(field_name=models.UPDATE_COMMENT_FIELD_NAME).first()
						if (comment_field is None) or (u'из неофициального' not in comment_field.new_value):
							res += u'\n\nПожалуйста, обращайте на это внимание при добавлении результатов в КЛБМатч. '
							res += u'Вся нужная информация есть на странице привязки результатов к участникам матча.'
	return res

class MessageFromInfoForm(RoundedFieldsModelForm):
	def __init__(self, *args, **kwargs):
		initial = kwargs.get('initial', {})
		initial['body'] = ''
		self.user = kwargs.pop('request').user
		table_update = kwargs.pop('table_update', None)
		event = kwargs.pop('event', None)
		user = kwargs.pop('user', None)
		to_participants = kwargs.pop('to_participants', False)
		wo_protocols = kwargs.pop('wo_protocols', False)
		wrong_club = kwargs.pop('wrong_club', False)
		# initial['sender_name'] = request.user.first_name + ' ' + request.user.last_name
		if table_update: # We're writing letter to author of this table update
			event_name = ''
			if table_update.model_name == 'Event':
				event = models.Event.objects.filter(pk=table_update.row_id).first()
				if event:
					event_name = event.name
					if wrong_club:
						initial['body'] = get_wrong_club_letter_text(table_update, event)
			elif table_update.model_name == 'Series':
				series = models.Series.objects.filter(pk=table_update.row_id).first()
				if series:
					event_name = series.name
			initial['title'] = u'[Ticket {}] {}'.format(table_update.id, event_name)
			initial['target_email'] = table_update.user.email
			initial['table_update'] = table_update
		elif event:
			initial['title'] = u'{} ({})'.format(event.name, event.date(with_nobr=False))
			if to_participants: # We're writing letter to all participants of some event
				initial['target_email'] = ', '.join(event.calendar_set.values_list('user__email', flat=True))
				participate_verb = u'планировали' if event.is_in_past() else u'планируете'
				initial['body'] = u' Добрый день!\n\nВы указали на сайте {}, что {} участвовать в забеге {} ({}, {}).'.format(
					models.SITE_URL, participate_verb, event.name, event.date(with_nobr=False), event.strCityCountry(with_nbsp=False))
				initial['body'] += u'\n\nСообщаем, что'
				initial['body'] += u'\n\nСтраница забега на нашем сайте: {}{}'.format(models.SITE_URL, event.get_absolute_url())
			else: # We're writing letter to event organizers
				initial['target_email'] = event.email
				if wo_protocols:
					races_wo_results = event.race_set.filter(has_no_results=False).exclude(loaded=models.RESULTS_LOADED).order_by(
						'distance__distance_type', '-distance__length')
					if races_wo_results.exists():
						initial['title'] += u' — протокол забега'
						initial['body'] = u' Добрый день!\n\nМы будем рады выложить для всех желающих протокол забега '
						initial['body'] += u'«{}», прошедшего {}, '.format(event.name, event.date(with_nobr=False))
						if races_wo_results.count() == 1:
							initial['body'] += u'на дистанцию {}.'.format(races_wo_results[0].distance.name)
						else:
							initial['body'] += u'на дистанции {}.'.format(u', '.join(x.distance.name for x in races_wo_results))
						initial['body'] += u'\nСможете ли прислать его в любом формате '
						initial['body'] += u'(лучше всего — в формате xls или xlsx, но любой другой тоже подойдёт)?'
						initial['body'] += u'\n\nПохоже, никто кроме вас тут не сможет нам помочь.'
						initial['body'] += u'\nМы разместим ссылки на протоколы на страницах нашего календаря забегов '
						initial['body'] += u'{}{} и {}.'.format(models.SITE_URL, event.get_absolute_url(), event.series.get_old_url())
						initial['body'] += u'\n\nИли, возможно, протокол просто не составлялся или забегов на эти дистанции вообще не было?'
						initial['body'] += u' Тогда, пожалуйста, сообщите нам об этом.\n\nСпасибо!'
						if not event.ask_for_protocol_sent:
							event.ask_for_protocol_sent = True
							event.save()
						models.log_obj_create(self.user, event, models.ACTION_UPDATE, field_list=['ask_for_protocol_sent'], comment=u'При создании письма организаторам')

		elif user: # We're writing to some exact user
			initial['target_email'] = user.email
			initial['body'] = u' {}, добрый день!'.format(user.first_name)
		initial['body'] += u'\n\n---\n{} {},\nКоманда сайта {}'.format(self.user.first_name, self.user.last_name, models.SITE_URL)
		kwargs['initial'] = initial
		super(MessageFromInfoForm, self).__init__(*args, **kwargs)
	def clean_title(self):
		title = self.cleaned_data['title'].strip()
		if title == '':
			raise forms.ValidationError(u'Тема сообщения не может быть пустой.')
		return title
	def clean_target_email(self):
		target_email = self.cleaned_data['target_email'].strip()
		if target_email == '':
			raise forms.ValidationError(u'Вы не указали адрес, куда отправлять сообщение.')
		return target_email
	def clean(self):
		cleaned_data = super(MessageFromInfoForm, self).clean()
		self.instance.created_by = self.user
		self.instance.bcc = models.INFO_MAIL
		# cleaned_data['sender_name'] = cleaned_data['sender_name'] if cleaned_data['sender_name'] else u'(не указан)'
		return cleaned_data
	class Meta:
		model = models.Message_from_site
		fields = ['target_email', 'title', 'body', 'attachment', 'table_update'] # 'sender_name', 
		labels = {
			# 'sender_name': u'Ваше имя для поля «Отправитель»',
		}
		widgets = {
			'body': forms.Textarea(attrs={'rows': 7}),
			'table_update': forms.HiddenInput,
		}

class UnofficialResultForm(RoundedFieldsModelForm):
	distance = forms.ModelChoiceField(
		label=u"Дистанция",
		queryset=models.Distance.objects.none(),
		empty_label=None,
		required=True)
	strava_link = forms.CharField(
		label=u'Ссылка на пробежку на Strava вида strava.com/activities/... или strava.app.link/... (необязательно)',
		max_length=100,
		required=False)
	def __init__(self, *args, **kwargs):
		self.event = kwargs.pop('event', None)
		super(UnofficialResultForm, self).__init__(*args, **kwargs)
		distances = self.event.race_set.exclude(loaded__in=(models.RESULTS_LOADED, models.RESULTS_SOME_OFFICIAL)).values_list('distance_id', flat=True)
		self.fields['distance'].queryset = models.Distance.objects.filter(pk__in=distances).order_by('distance_type', '-length')
		self.fields['comment'].required = True
		self.fields['time_raw'].required = True
	def clean(self):
		cleaned_data = super(UnofficialResultForm, self).clean()
		distance = cleaned_data['distance']
		race = self.event.race_set.exclude(loaded=models.RESULTS_LOADED).filter(distance=distance).first()
		if race is None:
			raise forms.ValidationError(u'Пожалуйста, выберите дистанцию из доступных.')
		self.instance.race = race
		time_raw = cleaned_data.get('time_raw', '')
		if distance.distance_type == models.TYPE_MINUTES:
			result = models.int_safe(time_raw)
		else:
			result = models.string2centiseconds(time_raw)
		if result == 0:
			raise forms.ValidationError(u'Пожалуйста, введите результат в указанном формате.')

		strava_link = cleaned_data.get('strava_link')
		if strava_link:
			strava_number = results_util.maybe_strava_activity_number(strava_link)
			if not strava_number:
				user = self.instance.user
				user_url = user.user_profile.get_absolute_url() if hasattr(user, 'user_profile') else ''
				models.send_panic_email('Incorrect Strava link', u'{} {}{} tried to add Strava link {} to race {}{}'.format(
					user.get_full_name(), models.SITE_URL, user_url, strava_link, models.SITE_URL, race.get_absolute_url()))
				raise forms.ValidationError(u'Некорректная ссылка на пробежку в Strava. Нужная ссылка должна содержать strava.com/activities/<число>'
					+ u' или strava.app.link/<буквы и цифры>')
			cleaned_data['strava_number'] = strava_number
		self.instance.result = result
		return cleaned_data
	class Meta:
		model = models.Result
		fields = ['distance', 'time_raw', 'comment', 'strava_link']
		labels = {
			'comment': u'Адрес страницы с результатами мероприятия или, если её нет, комментарий',
			'time_raw': u'Результат (если время – чч:мм:сс или чч:мм:сс,хх, если расстояние – число в метрах)',
		}

class UnofficialSeriesForm(ModelFormWithCity):
	region = RegionOrCountryField(
		required=True,
		label=u'* Регион (для России, Украины, Беларуси) или страна')
	new_city = forms.CharField(
		label=u'Не нашли нужный город? Напишите сюда его название',
		max_length=100,
		required=False)
	i_am_organizer = forms.BooleanField(
		label=u'Я — один из организаторов забега. Прошу выдать мне права на редактирование забегов этой серии',
		required=False)
	attachment = forms.FileField(
		label=u'Вы можете приложить файл до 20 МБ',
		required=False)
	def __init__(self, *args, **kwargs):
		super(UnofficialSeriesForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			if field == 'i_am_organizer':
				self.fields[field].widget.attrs.update({'class': 'checkbox'})
			else:
				self.fields[field].widget.attrs.update({'class': 'form-control'})
		self.fields['surface_type'].required = True
		self.fields['surface_type'].choices = models.SURFACE_TYPES[1:-1]
	def clean_name(self):
		name = self.cleaned_data['name'].strip()
		if name == '':
			raise forms.ValidationError(u'Название события не может быть пустым.')
		return name
	def clean(self):
		cleaned_data = super(UnofficialSeriesForm, self).clean()
		user = self.instance.created_by
		# raise forms.ValidationError(', '.join([unicode(key) + ':' + unicode(val) for key, val in cleaned_data.items()]))
		if not (cleaned_data.get('url_site', '').strip() or cleaned_data.get('comment_private', '').strip()):
			raise forms.ValidationError(u'Или укажите сайт события, или напишите комментарий.')
		if not cleaned_data.get('distances_raw', '').strip():
			raise forms.ValidationError(u'Укажите дистанции, которые были на забеге, через запятую')
		if cleaned_data['city'] and cleaned_data['new_city'].strip():
			raise forms.ValidationError(u'Либо выберите город из выпадающего списка, либо укажите новый город.')
		if cleaned_data['city'] is None: # Creating new city
			new_city = cleaned_data['new_city'].strip()
			if not new_city:
				raise forms.ValidationError(u'Выберите город из выпадающего списка или укажите новый город, если не нашли нужный.')
			region = cleaned_data.get('region')
			if not region:
				raise forms.ValidationError(u'Укажите страну или регион нового города.')
			if models.City.objects.filter(region=region, name=new_city).exists():
				city = models.City.objects.filter(region=region, name=new_city).first()
			else:
				city = models.City.objects.create(
					region=region,
					name=new_city,
					created_by=user,
				)
				models.log_obj_create(user, city, action=models.ACTION_CREATE, field_list=['region', 'name', 'created_by'])
			cleaned_data['city'] = city

		old_series = models.Series.objects.filter(name=cleaned_data['name'], city=cleaned_data['city']).first()
		if old_series:
			raise forms.ValidationError(u'В базе уже есть серия <a href="{}">{}</a> в городе {}. Возможно, она Вам и нужна?'.format(
				old_series.get_absolute_url(), cleaned_data['name'], cleaned_data['city'].name))

		series = models.Series.objects.create(
			name=cleaned_data['name'],
			city=cleaned_data['city'],
			url_site=cleaned_data.get('url_site', ''),
			comment_private=cleaned_data['comment_private'],
			created_by=user,
			surface_type=cleaned_data['surface_type'],
			)
		series.clean()
		series.save()
		models.log_obj_create(user, series, action=models.ACTION_CREATE, field_list=['name', 'city', 'url_site', 'comment_private', 'created_by'])
		self.instance.series = series

		if cleaned_data.get('i_am_organizer'):
			models.Series_editor.objects.create(series=series, user=user, added_by=user)
			group = Group.objects.get(name='editors')
			user.groups.add(group)
		return cleaned_data
	class Meta:
		model = models.Event
		fields = ['name', 'region', 'city_id', 'new_city', 'surface_type',
			'start_date', 'finish_date', 'start_time', 'url_site', 'distances_raw', 'comment_private', 'attachment',
			]
		labels = {
			'name': u'* Название забега',
			'start_date': u'* Дата старта',
			'surface_type': u'* Вид забега',
			'city_id': u'* Город',
			'distances_raw': u'* Дистанции через запятую («марафон», «полумарафон», либо целое число и «м» или «км» после него, вроде «2400 м»)',
		}
		widgets = {
			'start_date': CustomDateInput,
			'finish_date': CustomDateInput,
			'start_time': CustomTimeInput,
		}

class UnofficialEventForm(RoundedFieldsModelForm):
	attachment = forms.FileField(
		label=u'Вы можете приложить файл до 20 МБ',
		required=False)
	def __init__(self, *args, **kwargs):
		super(UnofficialEventForm, self).__init__(*args, **kwargs)
		self.fields['name'].required = False
	def clean_name(self):
		name = self.cleaned_data['name'].strip()
		if name == '':
			name = self.instance.series.name
		return name
	def clean(self):
		cleaned_data = super(UnofficialEventForm, self).clean()
		series = self.instance.series
		if 'start_date' not in cleaned_data:
			raise forms.ValidationError(u'Пожалуйста, укажите дату старта мероприятия.')
		if not cleaned_data.get('distances_raw', '').strip():
			raise forms.ValidationError(u'Укажите дистанции, которые были на забеге, через запятую')
		if series.event_set.filter(start_date=cleaned_data['start_date']).exists():
			raise forms.ValidationError(u'В серии «{}» уже есть забег, проходящий {}.'.format(
				series.name, cleaned_data['start_date']))
		url_site = cleaned_data.get('url_site', '').strip()
		comment_private = cleaned_data.get('comment_private', '').strip()
		if (url_site == '') and (comment_private == ''):
			raise forms.ValidationError(u'Или укажите сайт события, или напишите комментарий.')
		self.instance.source = u'Через форму «Добавить событие» на сайте'
		return cleaned_data
	class Meta:
		model = models.Event
		fields = ['name', 'start_date', 'finish_date', 'start_place', 'start_time',
			'url_site', 'distances_raw', 'comment_private', 'attachment',
			]
		labels = {
			'name': u'Название забега (оставьте пустым, если совпадает с названием серии)',
			'distances_raw': u'Дистанции через запятую («5 км», «марафон», «1234 м» и т.п., без кавычек)',
		}
		widgets = {
			'start_date': CustomDateInput(),
			'finish_date': CustomDateInput(),
			'start_time': CustomTimeInput(),
		}

DISTANCE_CHOICES = (
	(0, u'выберите из меню или заполните поле ниже'),
	(10000, u'10 км'),
	(15000, u'15 км'),
	(20000, u'20 км'),
	(21100, u'полумарафон'),
	(30000, u'30 км'),
	(42200, u'марафон'),
	(100000, u'100 км'),
)
DISTANCE_DICT = dict(DISTANCE_CHOICES)
class CalculatorForm(RoundedFieldsForm):
	gender = forms.ChoiceField(
		label=u'Пол',
		choices=models.GENDER_CHOICES[1:],
		initial=models.GENDER_MALE
		)
	birthyear = forms.IntegerField(
		label=u'Год рождения',
		widget=forms.NumberInput(),
		min_value=1900,
		max_value=models.CUR_KLB_YEAR
		)
	distance_menu = forms.ChoiceField(
		label=u"Точная дистанция",
		choices=DISTANCE_CHOICES
		)
	distance_exact = forms.DecimalField(
		label=u"Или укажите дистанцию в километрах",
		min_value=9.5,
		max_value=350,
		decimal_places=3,
		required=False)
	itra_score = forms.ChoiceField(
		label=u'Баллы ITRA',
		choices=((0, u'нет'), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), )
		)
	result = forms.CharField(
		label=u'Время (чч:мм:сс или чч:мм:сс,хх)',
		max_length=11,
		required=True
		)
	def clean_result(self):
		result = models.string2centiseconds(self.cleaned_data['result'].strip())
		if result == 0:
			raise forms.ValidationError(u'Пожалуйста, введите результат в указанном формате.')
		return result
	def clean(self):
		cleaned_data = super(CalculatorForm, self).clean()
		if cleaned_data.get('distance_exact', 0):
			cleaned_data['distance'] = int(cleaned_data['distance_exact'] * 1000)
			cleaned_data['distance_text'] = u'{} км'.format(cleaned_data['distance_exact'])
		elif int(cleaned_data['distance_menu']):
			cleaned_data['distance'] = int(cleaned_data['distance_menu'])
			cleaned_data['distance_text'] = DISTANCE_DICT[cleaned_data['distance']]
		else:
			raise forms.ValidationError(u'Выберите дистанцию из выпадающего меню или укажите точное значение в поле ниже.')
		cleaned_data['gender'] = models.int_safe(cleaned_data['gender'])
		return cleaned_data

MAX_UPLOAD_SIZE = 5242880
class AddReviewForm(forms.Form):
	event_id = forms.IntegerField(
		widget=forms.HiddenInput(),
		required=True)
	doc_type = forms.ChoiceField(
		label=u'Что Вы прикладываете',
		widget=forms.RadioSelect(),
		choices=(
			(models.DOC_TYPE_IMPRESSIONS, u'Отчёт о забеге'),
			(models.DOC_TYPE_PHOTOS, u'Ссылка на фотоальбом с забега (не меньше 10 фотографий)'),
		),
		initial=1)
	url = forms.URLField(
		label=u'Ссылка на отчёт или фотоальбом',
		required=False)
	author = forms.CharField(
		label=u'Автор отчёта или фотографий',
		max_length=100,
		required=True)
	attachment = forms.FileField(
		label=u'Или приложите файл с отчётом (не больше 5 МБ)',
		required=False)
	def __init__(self, *args, **kwargs):
		super(AddReviewForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			if field != 'doc_type':
				self.fields[field].widget.attrs.update({'class': 'form-control'})
	def clean_attachment(self):
		attachment = self.cleaned_data['attachment']
		if attachment:
			content_type = attachment.content_type
			if content_type in ['application/pdf', 'application/msword']:
				if attachment._size > MAX_UPLOAD_SIZE:
					raise forms.ValidationError(u'Вы можете загрузить файл размером до {} байт. Ваш файл – размером {} байт.'.format(
						filesizeformat(MAX_UPLOAD_SIZE), content._size))
			else:
				raise forms.ValidationError(u'Вы можете загрузить только файлы в формате DOC или PDF.')
		return attachment
	def clean(self):
		cleaned_data = super(AddReviewForm, self).clean()
		url = cleaned_data.get('url', '').strip()
		attachment = cleaned_data.get('attachment')
		if (not url) and (not attachment):
			raise forms.ValidationError(u'Пожалуйста, укажите ссылку или приложите файл с отчётом.')
		if url and attachment:
			raise forms.ValidationError(u'Пожалуйста, укажите что-нибудь одно – или ссылку, или файл с отчётом.')
		if 'strava.com' in url:
			raise forms.ValidationError(u'Эта форма — именно для отчётов о забегах. Вы можете добавить ссылку на свою пробежку в Страве '
				+ u'на странице {}{}'.format(models.SITE_URL, reverse('results:my_strava_links')))
		if (cleaned_data['doc_type'] == models.DOC_TYPE_PHOTOS) and attachment:
			raise forms.ValidationError(u'К сожалению, загрузить фотографии к нам на сайт нельзя – у нас не так много места. '
				+ u'Пожалуйста, воспользуйтесь любым фотохостингом и опубликуйте у нас ссылку на альбом.')
		event = models.Event.objects.filter(pk=cleaned_data.get('event_id', 0)).first()
		if (attachment is None) and models.Document.objects.filter(
				event_id=cleaned_data.get('event_id', 0),
				document_type=cleaned_data['doc_type'],
				url_original=cleaned_data['url']
				):
			raise forms.ValidationError(u'Эта ссылка уже есть на странице этого забега.')
		return cleaned_data

class ClubAndNumberForm(forms.Form):
	n_persons = forms.IntegerField(
		initial=1,
		widget=forms.NumberInput(attrs={'size': 6}),
		min_value=1,
		max_value=50,
		required=True)
	club = forms.ModelChoiceField(
		label=u"Клуб",
		queryset=models.Club.objects.filter(
			pk__in=set(models.Klb_team.objects.filter(year=models.CUR_KLB_YEAR).exclude(
				number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER).values_list('club_id', flat=True))).order_by('name'),
		empty_label=u'Индивидуальные участники',
		required=False)

class ClubsEditorForm(RoundedFieldsForm):
	club = forms.ModelChoiceField(
		label=u"Клуб",
		queryset = models.Club.objects.order_by('name'),
		empty_label=u'Выберите клуб',
		required=True)
	def __init__(self, *args, **kwargs):
		user = kwargs.pop('user', None)
		super(ClubsEditorForm, self).__init__(*args, **kwargs)
		user_club_ids = set(user.club_editor_set.values_list('pk', flat=True))
		self.fields['club'].queryset = models.Club.objects.exclude(pk__in=user_club_ids).order_by('name')

class KlbAgeGroupForm(RoundedFieldsForm):
	age_group = forms.ModelChoiceField(
		label=u"Возрастная группа",
		queryset=models.Klb_age_group.objects.none(),
		empty_label=None,
		required=True)
	def __init__(self, *args, **kwargs):
		if 'initial' in kwargs:
			year = kwargs['initial']['age_group'].match_year
		else:
			year = kwargs.pop('year', models.CUR_KLB_YEAR)
		super(KlbAgeGroupForm, self).__init__(*args, **kwargs)
		self.fields['age_group'].queryset = models.Klb_age_group.get_groups_by_year(year)

class KlbMatchCategoryForm(RoundedFieldsForm):
	match_category = forms.ModelChoiceField(
		label=u"Зачёт",
		queryset=models.Klb_match_category.objects.none(),
		empty_label=None,
		required=True)
	def __init__(self, *args, **kwargs):
		if 'initial' in kwargs:
			year = kwargs['initial']['match_category'].year
		else:
			year = kwargs.pop('year', models.CUR_KLB_YEAR)
		super(KlbMatchCategoryForm, self).__init__(*args, **kwargs)
		self.fields['match_category'].queryset = models.Klb_match_category.get_categories_by_year(year)

class KlbParticipantFilterForm(RoundedFieldsForm):
	template = forms.CharField(
		label='',
		max_length=100,
		widget=forms.TextInput(attrs={'placeholder': u'Имя, город, команда'}),
		required=False)
	region = forms.ChoiceField(
		label='',
		choices=[('', u'Регион')],
		required=False)
	country = forms.ChoiceField(
		label='',
		choices=[('', u'Страна')],
		required=False)
	def __init__(self, *args, **kwargs):
		participants = kwargs.pop('participants', set())
		super(KlbParticipantFilterForm, self).__init__(*args, **kwargs)
		self.fields['region'].choices += get_region_choices_for_participants_list(participants)
		self.fields['country'].choices += get_country_choices_for_participants_list(participants)

PROTOCOL_ABSENT = 1
PROTOCOL_BAD_FORMAT = 2
DEFAULT_REGION_ID = 46
class ProtocolHelpForm(forms.Form):
	events_type = forms.ChoiceField(
		label=u"Забеги, на которых",
		choices=(
			(PROTOCOL_ABSENT, u'протокола нет совсем'),
			(PROTOCOL_BAD_FORMAT, u'есть протокол в неудобном формате'),
		),
		initial=1)
	year = forms.ChoiceField(
		label=u"Год",
		choices=[(0, u'за все годы')] + [(x, x) for x in range(1970, datetime.date.today().year + 1)],
		initial=models.CUR_KLB_YEAR - 1)
	region = RegionOrCountryField(
		required=True,
		initial=DEFAULT_REGION_ID)

RATING_N_FINISHERS = 0
RATING_N_FINISHERS_MALE = 1
RATING_N_FINISHERS_FEMALE = 2
RATING_BEST_MALE = 3
RATING_BEST_FEMALE = 4
RATING_TYPES = (
	(RATING_N_FINISHERS, u'Число финишировавших'),
	(RATING_N_FINISHERS_MALE, u'Число финишировавших мужчин'),
	(RATING_N_FINISHERS_FEMALE, u'Число финишировавших женщин'),
	(RATING_BEST_MALE, u'Результат победителя среди мужчин'),
	(RATING_BEST_FEMALE, u'Результат победителя среди женщин'),
)
RATING_TYPES_DEGREES = (
	(RATING_N_FINISHERS, u'числу финишировавших'),
	(RATING_N_FINISHERS_MALE, u'числу финишировавших мужчин'),
	(RATING_N_FINISHERS_FEMALE, u'числу финишировавших женщин'),
	(RATING_BEST_MALE, u'результату победителя среди мужчин'),
	(RATING_BEST_FEMALE, u'результату победителя среди женщин'),
)
RATING_TYPES_CODES = {
	RATING_N_FINISHERS: u'n_finishers',
	RATING_N_FINISHERS_MALE: u'n_finishers_men',
	RATING_N_FINISHERS_FEMALE: u'n_finishers_women',
	RATING_BEST_MALE: u'best_male_result',
	RATING_BEST_FEMALE: u'best_female_result',
}
RATING_TYPES_CODES_INV = {v: k for k, v in RATING_TYPES_CODES.iteritems()}
RATING_TYPES_BY_FINISHERS = (RATING_N_FINISHERS, RATING_N_FINISHERS_MALE, RATING_N_FINISHERS_FEMALE)
RATING_TYPE_DEFAULT = RATING_N_FINISHERS

today = datetime.date.today()
RATING_YEAR_ALL = 0
RATING_YEARS_RANGE = range(today.year, 2006, -1)
RATING_YEARS = RATING_YEARS_RANGE + [RATING_YEAR_ALL]
RATING_YEAR_DEFAULT = (today.year - 1) if (today.month < 6) else today.year

RATING_COUNTRY_ALL = 'ALL'
RATING_COUNTRY_IDS = results_util.THREE_COUNTRY_IDS + (RATING_COUNTRY_ALL, )
RATING_COUNTRY_DEFAULT = 'RU'
RATING_COUNTRIES_DEGREES = {
	'RU': u'в России',
	'UA': u'на Украине',
	'BY': u'в Беларуси',
	RATING_COUNTRY_ALL: u'в России, Беларуси, Украине',
}
def get_degree_from_country(country):
	if country:
		return RATING_COUNTRIES_DEGREES[country.id]
	return RATING_COUNTRIES_DEGREES['ALL']

class RatingForm(forms.Form):
	country_id = forms.ChoiceField(
		label=u"Страна",
		choices=list(models.Country.objects.filter(pk__in=RATING_COUNTRY_IDS).order_by('value').values_list('pk', 'name'))
			+ [('ALL', u'Все страны'), ],
		initial='RU',
	)
	year = forms.ChoiceField(
		label=u"Год",
		choices=[(x, x) for x in RATING_YEARS_RANGE] + [(RATING_YEAR_ALL, u'за все годы')],
		initial=RATING_YEAR_DEFAULT,
	)
	distance_id = forms.ChoiceField(
		label=u"Дистанция",
		choices=list(models.Distance.objects.filter(pk__in=results_util.DISTANCES_FOR_RATING).order_by('distance_type', '-length').values_list(
			'pk', 'name')) + [(results_util.DISTANCE_ANY, u'все дистанции'), (results_util.DISTANCE_WHOLE_EVENTS, u'события целиком')],
		initial=results_util.DIST_MARATHON_ID,
	)
	rating_type = forms.ChoiceField(
		label=u"Показатель",
		choices=RATING_TYPES,
		initial=RATING_TYPE_DEFAULT,
	)
	def clean(self):
		cleaned_data = super(RatingForm, self).clean()
		if (models.int_safe(cleaned_data['distance_id']) in (results_util.DISTANCE_ANY, results_util.DISTANCE_WHOLE_EVENTS)) \
				and (models.int_safe(cleaned_data['rating_type']) in (RATING_BEST_MALE, RATING_BEST_FEMALE)):
			cleaned_data['rating_type'] = RATING_TYPE_DEFAULT
			# self.data['rating_type'] = RATING_TYPE_DEFAULT
		return cleaned_data

class AgeGroupRecordsForDistanceForm(forms.Form):
	country_id = forms.ChoiceField(
		label=u"Страна",
		choices=models.Country.objects.filter(pk='RU').order_by('value').values_list('pk', 'name'),
		# choices=models.Country.objects.filter(pk__in=RATING_COUNTRY_IDS).order_by('value').values_list('pk', 'name'),
	)
	distance_id = forms.ChoiceField(
		label=u"Дистанция",
		choices=models.Distance.objects.filter(pk__in=results_util.DISTANCES_FOR_COUNTRY_RECORDS).order_by('distance_type', '-length').values_list(
			'pk', 'name'),
	)
	def __init__(self, *args, **kwargs):
		super(AgeGroupRecordsForDistanceForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			self.fields[field].widget.attrs.update({'class': 'form-control'})

class AgeGroupRecordForm(AgeGroupRecordsForDistanceForm):
	gender = forms.ChoiceField(
		label=u'Пол',
		choices=models.GENDER_CHOICES[1:],
	)
	age = forms.ChoiceField(
		label=u"Возрастная группа",
		choices=[(age_group.age_min if age_group.age_min else 0, age_group) for age_group in models.Record_age_group.objects.all()],
		required=True,
	)

class RegistrantAndRaceForm(RoundedFieldsForm):
	registrant = forms.ChoiceField(
		label=u"Кого вы регистрируете",
		widget=forms.RadioSelect(),
		initial=0,
		required=True)
	race = forms.ModelChoiceField(
		label=u"Дистанция",
		queryset=models.Race.objects.none(),
		empty_label=None,
		widget=forms.RadioSelect(),
		required=True)
	def __init__(self, *args, **kwargs):
		user = kwargs.pop('user')
		event = kwargs.pop('event')
		super(RegistrantAndRaceForm, self).__init__(*args, **kwargs)
		self.fields['race'].queryset = event.get_reg_race_set(open_only=True)
		self.fields['registrant'].choices = [(0, u'себя')] \
			+ [(registrant.id, unicode(registrant)) for registrant in user.saved_registrant_set.order_by('lname', 'fname')] \
			+ [(-1, u'другого человека')]

class RegistrationForm(ModelFormWithCity):
	region = RegionOrCountryField(required=True)
	new_city_name = forms.CharField(
		label=u'Если вашего населённого пункта нет в выпадающем меню, напишите здесь его название',
		max_length=100,
		required=False)
	def __init__(self, *args, **kwargs):
		instance = kwargs['instance']
		self.user = instance.user
		registration = kwargs.pop('registration')

		registrant_id = kwargs.pop('registrant_id', 0)
		for_himself = (registrant_id == 0)
		registrant = None
		if registrant_id > 0:
			registrant = self.user.saved_registrant_set.filter(pk=registrant_id).first()

		initial = kwargs.get('initial', {})
		initial['user'] = self.user

		if for_himself:
			initial['lname'] = self.user.last_name
			initial['fname'] = self.user.first_name
			initial['email'] = self.user.email
			if hasattr(self.user, 'user_profile'):
				profile = self.user.user_profile
				initial['midname'] = profile.midname
				if profile.city:
					initial['region'] = profile.city.region.id
					initial['city_id'] = profile.city.id
				initial['gender'] = profile.gender
				initial['birthday'] = profile.birthday
				initial['phone_number'] = profile.phone_number
				initial['emergency_name'] = profile.emergency_name
				initial['emergency_phone_number'] = profile.emergency_phone_number
				initial['club_name'] = profile.club_name
				if registration.is_address_needed:
					initial['zipcode'] = profile.zipcode
					initial['address'] = profile.address
		elif registrant:
			for field in registrant.__class__._meta.get_fields():
				if field.name not in ['id', 'user', 'created_time', 'city']:
					initial[field.name] = getattr(registrant, field.name)
			if registrant.city:
				initial['region'] = registrant.city.region.id
				initial['city_id'] = registrant.city.id

		kwargs['initial'] = initial
		super(RegistrationForm, self).__init__(*args, **kwargs)

		if registration.is_address_needed:
			self.fields['zipcode'].required = True
			self.fields['address'].required = True
		else:
			self.fields['zipcode'].widget = forms.HiddenInput()
			self.fields['address'].widget = forms.HiddenInput()

		if registration.is_midname_needed:
			self.fields['midname'].label = u'Отчество'
			self.fields['midname'].required = True

		if not (for_himself or registrant):
			self.fields['save_registrant_data'] = forms.BooleanField(
				label=u'Сохранить введённые данные для будущих регистраций',
				initial=True,
				required=False)
		
		for field in self.fields:
			if self.fields[field].widget.__class__.__name__ not in ('RadioSelect', 'CheckboxInput', 'CheckboxSelectMultiple'):
				self.fields[field].widget.attrs.update({'class': 'form-control'})
	def clean(self):
		cleaned_data = super(RegistrationForm, self).clean()
		city = cleaned_data.get('city')
		new_city_name = cleaned_data.get('new_city_name', '').strip()
		if new_city_name and city:
			raise forms.ValidationError(u'Либо выберите город из выпадающего списка, либо введите название нового города, но не одновременно')
		if (not new_city_name) and (not city):
			raise forms.ValidationError(u'Либо выберите город из выпадающего списка, либо введите название нового города')
		if new_city_name:
			region = cleaned_data["region"]
			new_city = region.city_set.filter(name=new_city_name).first()
			if not new_city:
				new_city = models.City.objects.create(region=region, name=new_city_name, created_by=self.user)
				models.log_obj_create(self.user, new_city, action=models.ACTION_CREATE, field_list=['region', 'name', 'created_by'])
			cleaned_data['city'] = new_city
			self.instance.city = new_city
		if 'email' not in cleaned_data:
			cleaned_data['email'] = ''
		if cleaned_data.get('save_registrant_data'):
			saved_registrant = models.Saved_registrant(user=self.user)
			for field in saved_registrant.__class__._meta.get_fields():
				if field.name not in ['id', 'user', 'created_time']:
					try:
						setattr(saved_registrant, field.name, cleaned_data.get(field.name))
					except:
						pass
			saved_registrant.save()
		return cleaned_data
	class Meta:
		model = models.Registrant
		fields = ['gender', 'lname', 'fname', 'midname', 'region', 'city_id', 'new_city_name',
			'birthday', 'email', 'phone_number', 'emergency_name', 'emergency_phone_number', 'zipcode', 'address', 'club_name']
		labels = {
			'city_id': u'Город',
			'club_name': u'Клуб (необязательно)'
		}
		widgets = {
			'birthday': CustomDateInput(),
			'email': forms.EmailInput(),
		}

class PriceQuestionsForm(forms.Form):
	race_cost = forms.ModelChoiceField(
		label=u"Стоимость участия",
		queryset=models.Race_cost.objects.none(),
		empty_label=None,
		widget=forms.RadioSelect(),
		required=True)
	def __init__(self, *args, **kwargs):
		registration = kwargs.pop('registration')
		registrant = kwargs.pop('registrant')
		race = kwargs.pop('race')
		race_details = race.reg_race_details
		super(PriceQuestionsForm, self).__init__(*args, **kwargs)

		for question in race.get_reg_question_set_for_today():
			field_name = 'question_{}'.format(question.id)
			if question.multiple_answers:
				self.fields[field_name] = forms.MultipleChoiceField(
					label=question.name,
					choices=[(choice.id, choice.get_name_with_price()) for choice in question.reg_question_choice_set.filter(is_visible=True)],
					initial=[choice.id for choice in question.reg_question_choice_set.filter(is_visible=True, is_default=True)],
					widget=forms.CheckboxSelectMultiple(),
					required=question.is_required,
				)
			else:
				self.fields[field_name] = forms.ChoiceField(
					label=question.name,
					choices=[(choice.id, choice.get_name_with_price()) for choice in question.reg_question_choice_set.filter(is_visible=True)],
					initial=question.get_default_choice(),
					widget=forms.RadioSelect(),
					required=question.is_required,
				)

		tariffs = race_details.get_current_race_costs(registrant)
		self.fields['race_cost'].queryset = tariffs
		self.fields['race_cost'].initial = tariffs.first()
		self.fields['race_cost'].empty_label = None

		for field in self.fields:
			if self.fields[field].widget.__class__.__name__ not in ('RadioSelect', 'CheckboxInput', 'CheckboxSelectMultiple'):
				self.fields[field].widget.attrs.update({'class': 'form-control'})

class ClubRecordsForm(forms.Form):
	year = forms.ChoiceField(
		label=u"Год",
		choices=[(RATING_YEAR_ALL, u'все годы')],
		initial=RATING_YEAR_ALL,
	)
	def __init__(self, *args, **kwargs):
		club = kwargs.pop('club')
		oldest_team = club.klb_team_set.order_by('year').first()
		super(ClubRecordsForm, self).__init__(*args, **kwargs)
		if oldest_team:
			self.fields['year'].choices = [(x, u'{} год'.format(x)) for x in range(oldest_team.year, datetime.date.today().year + 1)] \
				+ [(RATING_YEAR_ALL, u'все годы')]
			# self.fields['year'].initial = models.CUR_KLB_YEAR

class PaymentForm(RoundedFieldsModelForm):
	def __init__(self, *args, **kwargs):
		user = kwargs.pop('user')
		if user.is_authenticated():
			initial = kwargs.get('initial', {})
			initial['sender'] = u'{} {}'.format(user.first_name, user.last_name)
			kwargs['initial'] = initial
		super(PaymentForm, self).__init__(*args, **kwargs)
	def clean_amount(self):
		amount = self.cleaned_data.get('amount')
		if amount < models.MIN_PAYMENT_AMOUNT:
			raise forms.ValidationError(u'Сумма не может меньше {} рублей'.format(models.MIN_PAYMENT_AMOUNT))
		if amount > models.MAX_PAYMENT_AMOUNT:
			raise forms.ValidationError(u'Сумма не может превышать {} рублей'.format(models.MAX_PAYMENT_AMOUNT))
		return amount
	class Meta:
		model = models.Payment_moneta
		fields = ['amount', 'description', 'sender', ]
		labels = {
			'amount': u'Сумма в рублях',
			'description': u'Что вы оплачиваете',
		}
		widgets = {
			'amount': forms.NumberInput(attrs={'step': .01}),
			'description': forms.Textarea(attrs={'rows': 4, 'placeholder': u'Клуб и список людей, за кого оплачиваете участие'})
		}

class RadioSelectWithoutUl(forms.RadioSelect):
	template_name = 'my_widgets/radio.html'

class MedalOrderForm(RoundedFieldsModelForm):
	to_save_address = forms.BooleanField(
		label=u'Сохранить этот адрес для будущих заказов',
		required=False)
	def __init__(self, *args, **kwargs):
		self.user = kwargs.pop('user')
		if self.user.is_authenticated():
			initial = kwargs.get('initial', {})
			initial['lname'] = self.user.last_name
			initial['fname'] = self.user.first_name
			initial['email'] = self.user.email
			if hasattr(self.user, 'user_profile'):
				profile = self.user.user_profile
				initial['midname'] = profile.midname
				initial['phone_number'] = profile.phone_number
				initial['zipcode'] = profile.zipcode
				initial['address'] = profile.address
			kwargs['initial'] = initial
		super(MedalOrderForm, self).__init__(*args, **kwargs)
		if not self.user.is_authenticated():
			del self.fields['to_save_address']
	def clean(self):
		cleaned_data = super(MedalOrderForm, self).clean()
		delivery_method = cleaned_data.get('delivery_method')
		zipcode = cleaned_data.get('zipcode', '').strip()
		address = cleaned_data.get('address', '').strip()
		if delivery_method == 2:
			if (not zipcode) or (not address):
				raise forms.ValidationError(u'Пожалуйста, укажите Ваши индекс и адрес, или выберите другой способ доставки')
		elif delivery_method == 3:
			if not cleaned_data.get('comment'):
				raise forms.ValidationError(u'Пожалуйста, укажите в поле «Комментарий», как вы хотите забрать медали, или выберите другой способ доставки')
		if cleaned_data.get('to_save_address') and hasattr(self.user, 'user_profile') and zipcode and address:
			profile = self.user.user_profile
			fields_changed = []
			if profile.zipcode != zipcode:
				profile.zipcode = zipcode
				fields_changed.append('zipcode')
			if profile.address != address:
				profile.address = address
				fields_changed.append('address')
			if fields_changed:
				profile.save()
				models.log_obj_create(self.user, profile, models.ACTION_UPDATE, field_list=fields_changed, comment=u'При создании заказа на доставку медалей')
		return cleaned_data
	class Meta:
		model = models.Medal_order
		fields = ['fname', 'lname', 'email', 'phone_number', 'n_medals', 'delivery_method', 'zipcode', 'address', 'to_save_address', 'comment']
		widgets = {
			'n_medals': forms.NumberInput,
			'delivery_method': RadioSelectWithoutUl,
			'comment': forms.Textarea(attrs={'rows': 4, 'placeholder': u'Например, имена участников матча, если заказываете больше одной медали с шильдами'})
		}
