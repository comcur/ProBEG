# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib import messages

from results import models, results_util
from results.models_klb import get_regulations_link
from .views_common import group_required

@group_required('editors', 'admins')
def memo_editor(request):
	context = {}
	context['page_title'] = u'Памятка редактору'
	return render(request, "editor/memo_editor.html", context)

@group_required('admins')
def memo_admin(request):
	context = {}
	context['page_title'] = u'Памятка администратору'
	context['doc_types'] = models.DOCUMENT_TYPES
	return render(request, "editor/memo_admin.html", context)

@group_required('admins')
def memo_templates(request):
	context = {}
	context['page_title'] = u'Шаблоны для писем'
	context['year'] = models.CUR_KLB_YEAR
	context['SITE_URL'] = models.SITE_URL
	context['regulations_link'] = get_regulations_link(models.CUR_KLB_YEAR)
	return render(request, "editor/memo_templates.html", context)

@group_required('editors', 'admins')
def memo_spelling(request):
	context = {}
	context['page_title'] = u'Рекомендации по текстам'
	return render(request, "editor/memo_spelling.html", context)

@group_required('admins')
def memo_salary(request):
	context = {}
	context['page_title'] = u'Оплата работы на сайте'
	context['template_name'] = 'editor/memo_salary.html'
	return render(request, "results/base_template.html", context)

@group_required('admins')
def search_by_id(request, id=None):
	context = {}
	phone_number = None
	if id is None:
		id = request.GET.get("id_for_search", '').strip()
	if id == '':
		return redirect("results:races")
	elif models.is_phone_number_correct(id):
		phone_number = ''.join(c for c in id if c.isdigit())[-7:]
		id = None
	elif models.int_safe(id) > 0:
		id = models.int_safe(id)
	# elif (id[0] in u'MmМмWw') and (models.int_safe(id[1:]) > 0):
	# 	runner = models.Runner.objects.filter(ak_person_id=id).first()
	# 	if runner:
	# 		return redirect(runner)
	# 	else:
	# 		return redirect("results:runners")
	# elif models.Event.objects.filter(ak_race_id=id).exists():
	# 	return redirect("results:event_details", ak_race_id=id)
	else:
		return redirect("results:races", race_name=id)
	if id:
		context['page_title'] = u'Объекты с id={}'.format(id)
		context['id'] = id
		context['series'] = models.Series.objects.filter(pk=id).first()
		context['event'] = models.Event.objects.filter(pk=id).first()
		context['race'] = models.Race.objects.filter(pk=id).first()
		context['news'] = models.News.objects.filter(pk=id).first()
		# context['runner'] = User.objects.filter(pk=id).first() # TODO
		context['city'] = models.City.objects.filter(pk=id).first()
		context['document'] = models.Document.objects.filter(pk=id).first()
		context['distance'] = models.Distance.objects.filter(pk=id).first()
		context['club'] = models.Club.objects.filter(pk=id).first()
		context['klb_person'] = models.Klb_person.objects.filter(pk=id).first()
		context['klb_team'] = models.Klb_team.objects.filter(pk=id).first()
		context['user'] = User.objects.filter(pk=id).first()
		context['user_profile'] = models.User_profile.objects.filter(pk=id).first()
		context['runner'] = models.Runner.objects.filter(pk=id).first()
		context['table_update'] = models.Table_update.objects.filter(pk=id).first()
		context['result'] = models.Result.objects.filter(pk=id).first()
		context['klb_participant'] = models.Klb_participant.objects.filter(pk=id).first()
		context['klb_result'] = models.Klb_result.objects.filter(pk=id).first()
		context['club_member'] = models.Club_member.objects.filter(pk=id).first()
	elif phone_number:
		context['page_title'] = u'Участники КЛБМатчей с телефонами, содержащими {}'.format(phone_number)
		context['phone_number'] = phone_number
		context['participants_with_phone_number'] = models.Klb_participant.objects.filter(phone_number_clean__contains=phone_number).select_related(
			'team__club', 'klb_person').order_by('match_year', 'klb_person__lname', 'klb_person__fname')
	return render(request, "editor/search_by_id.html", context)

@group_required('admins')
def restart(request):
	messages.success(request, u'Django перезапущен')
	results_util.restart_django()
	return redirect('results:main_page')
