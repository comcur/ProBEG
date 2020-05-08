# -*- coding: utf-8 -*-
from __future__ import division
from django.template.defaultfilters import stringfilter
from django.contrib.auth.models import Group
from django import template

from results import models
from results.results_util import plural_ending, plural_ending_new, get_age_on_date

register = template.Library()

@register.filter
def is_checkbox(field):
	return field.field.widget.__class__.__name__ == 'CheckboxInput'

@register.filter
def is_radio(field):
	return field.field.widget.__class__.__name__ == 'RadioSelect'

@register.filter
def is_multicheckbox(field):
	return field.field.widget.__class__.__name__ == 'CheckboxSelectMultiple'

@register.filter
def klass(field):
	return field.field.widget.__class__.__name__

@register.filter(is_safe=True)
def label_with_classes(value, arg):
	return value.label_tag(attrs={'class': arg})

@register.filter(is_safe=True)
def label_with_col_classes(value, arg):
	return value.label_tag(attrs={'class': "col-sm-{} control-label".format(arg)})

@register.filter(is_safe=True)
def has_posts_in_social_page(news, page):
	return news.social_post_set.filter(social_page=page).exists()

@register.filter
@stringfilter
def add_prefix(value):
	if value and (value[:4] != "http"):
		return '{}/{}'.format(models.SITE_URL_OLD, value)
	return value

@register.filter
def has_group(user, group_name):
	return (Group.objects.filter(name=group_name).first() in user.groups.all()) if user else False

@register.filter
def secs2time(value):
	return models.secs2time(value)

@register.filter
def centisecs2time(value, round_hundredths=False):
	return models.centisecs2time(value, round_hundredths)

@register.filter
def date_rus(value):
	return models.date2str(value, with_nbsp=False)

@register.filter
def subtract(value, arg):
	return value - arg

@register.filter
def pace(value):
	seconds = value % 60
	minutes = value // 60
	return u'{}:{}/км'.format(minutes, unicode(seconds).zfill(2))

@register.filter
def inverse(value):
	return -value

@register.filter
def div(value, arg):
	return value // arg

@register.filter(is_safe=True)
def label_with_classes(value, arg):
	return value.label_tag(attrs={'class': arg})

@register.filter
def get_team(runner, year):
	return runner.klb_person.get_team(year) if runner.klb_person else None

@register.filter(is_safe=True)
def get_social_url(auth):
	if auth.provider == 'vk-oauth2':
		return 'https://vk.com/id{}'.format(auth.uid)
	if auth.provider == 'twitter':
		return 'https://twitter.com/intent/user?user_id={}'.format(auth.uid)
	return ''

@register.filter(is_safe=True)
def get_social_editor_url(auth):
	return '/admin/social_django/usersocialauth/{}/change/'.format(auth.id)
	
@register.simple_tag
def get_verbose_field_name(instance, field_name):
	return instance._meta.get_field(field_name).verbose_name
	
@register.filter
def wo_last_word(value):
	return ' '.join(value.split()[:-1])
	
@register.filter
def wo_first_and_last_word(value):
	return ' '.join(value.split()[1:-1])
	
@register.filter
def percent(whole, part): # For e.g. 'с трёх забегов'
	if (whole > 0) and (part is not None):
		return min(100, int(part * 100 / whole))
	return 100

@register.filter
def age_on_event(runner, event):
	return get_age_on_date(event.start_date, runner.birthday)

@register.filter
def ending(value, word_type):
	return plural_ending_new(value, word_type)

@register.filter
def plural_ending_1(value): # For e.g. 'результат'
	return plural_ending(value, [u'', u'а', u'ов'])

@register.filter
def plural_ending_2(value): # For e.g. 'трасса', 'команда','женщина'
	return plural_ending(value, [u'а', u'ы', u''])

@register.filter
def plural_ending_3(value): # For e.g. 'новость'
	return plural_ending(value, [u'ь', u'и', u'ей'])

@register.filter
def plural_ending_4(value): # For e.g. 'дистанция'
	return plural_ending(value, [u'я', u'и', u'й'])

@register.filter
def plural_ending_5(value): # For e.g. 'завершивши_ся', 'предстоящий', 'похожий'
	return plural_ending(value, [u'й', u'х', u'х'])

@register.filter
def plural_ending_6(value): # For e.g. 'обработанный'
	return plural_ending(value, [u'й', u'х', u'х'])

@register.filter
def plural_ending_7(value): # For e.g. 'предупреждение'
	return plural_ending(value, [u'е', u'я', u'й'])

@register.filter
def plural_ending_8(value): # For e.g. 'ошибка'
	return plural_ending(value, [u'ка', u'ки', u'ок'])

@register.filter
def plural_ending_9(value): # For e.g. 'человек'
	return plural_ending(value, [u'', u'а', u''])

@register.filter
def plural_ending_10(value): # For e.g. 'планиру?т'
	return u'е' if (value == 1) else u'ю'

@register.filter
def plural_ending_11(value): # For e.g. 'год/лет'
	return plural_ending(value, [u'год', u'года', u'лет'])

@register.filter
def plural_ending_12(value): # For e.g. 'ваш'
	return plural_ending(value, [u'', u'и', u'и'])

@register.filter
def plural_ending_13(value): # For e.g. 'мужчина'
	return plural_ending(value, [u'а', u'', u''])

@register.filter
def plural_ending_14(value): # For e.g. 'о дистанциях'
	return plural_ending(value, [u'и', u'ях', u'ях'])

@register.filter
def plural_ending_15(value): # For e.g. 'о забегах'
	return plural_ending(value, [u'е', u'ах', u'ах'])

@register.filter
def plural_ending_16(value): # For e.g. 'с трёх забегов'
	return plural_ending(value, [u'а', u'ов', u'ов'])
