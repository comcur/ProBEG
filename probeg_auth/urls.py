# -*- coding: utf-8 -*-
from django.contrib.auth import views as auth_views
from django.core.urlresolvers import reverse
from django.conf.urls import url

from . import views, forms
from results import models

app_name = 'probeg_auth'

urlpatterns = [
	url(r'login/$', views.login_view, name='login'),
	url(r'logout/$', auth_views.LogoutView.as_view(), name='logout'),
	url(r'register/$', views.register_view, name='register'),
	url(r'password_change/$', auth_views.PasswordChangeView.as_view(
			template_name='probeg_auth/password_change_form.html',
			success_url='/password_change/done/',
			form_class=forms.MyPasswordChangeForm,
		),
		name="password_change"),
	url(r'password_change/done/$',
		auth_views.PasswordChangeDoneView.as_view(template_name='probeg_auth/password_change_done.html'),
		name='password_change_done'),
	url(r'password_reset/$', auth_views.PasswordResetView.as_view(
			template_name='probeg_auth/password_reset_form.html',
			email_template_name='probeg_auth/password_reset_email.html',
			subject_template_name='probeg_auth/password_reset_subject.html',
			success_url='{}/password_reset/done'.format(app_name),
		),
		name='password_reset'),
	url(r'password_reset/done/$', auth_views.PasswordResetDoneView.as_view(
			template_name='probeg_auth/password_reset_done.html',
		),
		name='password_reset_done'),
	url(r'reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
		auth_views.PasswordResetConfirmView.as_view(
			template_name='probeg_auth/password_reset_confirm.html',
			success_url='{}reset/done/'.format(app_name),
			form_class=forms.MySetPasswordForm,
			post_reset_login=True,
			post_reset_login_backend='django.contrib.auth.backends.ModelBackend',
		),
		name='password_reset_confirm'),
	url(r'reset/done/$', auth_views.PasswordResetCompleteView.as_view(
			template_name='probeg_auth/password_reset_complete.html',
		),
		name='password_reset_complete'),
]
