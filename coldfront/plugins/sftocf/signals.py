"""signals for sftocf plugin"""
import django.dispatch

starfish_add_aduser = django.dispatch.Signal()
starfish_remove_aduser = django.dispatch.Signal()
starfish_add_adgroup = django.dispatch.Signal()
