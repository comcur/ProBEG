# -*- coding: utf-8 -*-
from django import forms
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm

class LoginForm(forms.Form):
	email = forms.CharField(
		label=u'Адрес электронной почты',
		max_length=100,
		widget=forms.TextInput(attrs={'class':'form-control'}))
	password = forms.CharField(
		label=u'Пароль',
		widget=forms.PasswordInput(attrs={'class':'form-control'}))

class RegisterForm(forms.Form):
	reg_lname = forms.CharField(
		label=u'Фамилия',
		max_length=100,
		required=True,
		widget=forms.TextInput(attrs={'class':'form-control'}))
	reg_fname = forms.CharField(
		label=u'Имя',
		max_length=100,
		required=True,
		widget=forms.TextInput(attrs={'class':'form-control'}))
	reg_email = forms.EmailField(
		label=u'Адрес электронной почты',
		max_length=100,
		widget=forms.EmailInput(attrs={'class':'form-control'}))
	reg_password = forms.CharField(
		label=u'Пароль (не меньше 6 символов)',
		min_length=6,
		widget=forms.PasswordInput(attrs={'class':'form-control'}))
	reg_password_confirm = forms.CharField(
		label=u'Повторите пароль',
		min_length=6,
		widget=forms.PasswordInput(attrs={'class':'form-control'}))

class MyPasswordChangeForm(PasswordChangeForm):
	def __init__(self, *args, **kwargs):
		super(MyPasswordChangeForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			self.fields[field].widget.attrs.update({'class': 'form-control'})

class MySetPasswordForm(SetPasswordForm):
	def __init__(self, *args, **kwargs):
		super(MySetPasswordForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			self.fields[field].widget.attrs.update({'class': 'form-control'})
