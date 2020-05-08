# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.db.models import Count
from django.db.models.functions import Lower
from collections import Counter

from results import models
from editor import forms
from .views_user_actions import log_form_change
from .views_common import group_required

# Print all runner_names from database
@group_required('admins')
def runner_names(request):
	if 'frmName_submit' in request.POST:
		form = forms.RunnerNameForm(request.POST)
		if form.is_valid():
			form.instance.name = form.instance.name.title()
			runner_name = form.save()
			log_form_change(request.user, form, action=models.ACTION_CREATE)
			messages.success(request, u'Имя «{}» (пол: {}) успешно создано'.format(runner_name.name, runner_name.get_gender_display()))
			return redirect('editor:runner_names')
		else:
			messages.warning(request, u"Имя не создано. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = forms.RunnerNameForm()
	context = {}
	context['form'] = form
	context['page_title'] = u'Имена для бегунов'
	context['names_male'] = models.Runner_name.objects.filter(gender=models.GENDER_MALE).order_by('name')
	context['names_female'] = models.Runner_name.objects.filter(gender=models.GENDER_FEMALE).order_by('name')
	return render(request, "editor/runner_names.html", context)

@group_required('admins')
def runner_name_delete(request, runner_name_id):
	runner_name = get_object_or_404(models.Runner_name, pk=runner_name_id)
	name = runner_name.name
	models.log_obj_delete(request.user, runner_name)
	runner_name.delete()
	messages.success(request, u'Имя «{}» успешно удалено.'.format(name))
	return redirect('editor:runner_names')

# Print all runner_names from database
@group_required('admins')
def popular_names_in_free_results(request):
	context = {}
	context['page_title'] = u'Самые популярные имена среди непривязанных результатов'
	context['min_count'] = 10

	names_dict = Counter()
	for a, b in models.Result.objects.filter(user=None, runner=None).exclude(lname='').exclude(fname='').values_list('lname', 'fname'):
		names_dict[(a.lower(), b.lower())] += 1
	names_dict_rev = sorted([(v, k) for k, v in names_dict.items() if v >= context['min_count']], key=lambda x:-x[0])
	context['names'] = [(count, name[0].title(), name[1].title(), models.Runner.objects.filter(lname=name[0], fname=name[1]).count()) for count, name in names_dict_rev]

	return render(request, "editor/popular_names_in_free_results.html", context)
