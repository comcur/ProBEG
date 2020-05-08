# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages

from editor.views.views_common import *
from results.models import *
from editor.forms import *

@group_required('admins')
def district_details(request, district_id):
	district = get_object_or_404(TestModel, pk=district_id)

	context = {}
	context['district'] = district
	context['frmDistrict'] = DistrictForm(instance=district)
	context['form_title'] = u'{} (id {})'.format(district, district.id)
	return render(request, "editor/district_details.html", context)

@group_required('admins')
def district_update(request, district_id):
	district = get_object_or_404(TestModel, pk=district_id)
	if (request.method == 'POST'):
		form = DistrictForm(data=request.POST, instance=district)
		if form.is_valid():
			district.save()
			messages.success(request, u'Округ «{}» успешно обновлен. Проверьте, всё ли правильно.'.format(district))
			return redirect('editor:district_details', district_id=district.id)
		else:
			messages.warning(request, u"Серия не обновлена. Пожалуйста, исправьте ошибки в форме." + unicode(form.is_bound))
	else:
		form = DistrictForm(instance=district)
	return district_details(request, district_id=district_id)
