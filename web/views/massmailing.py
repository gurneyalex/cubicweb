"""Mass mailing form views

:organization: Logilab
:copyright: 2007-2009 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
:contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
"""
__docformat__ = "restructuredtext en"

import operator

from logilab.mtconverter import html_escape

from cubicweb.interfaces import IEmailable
from cubicweb.selectors import implements, match_user_groups
from cubicweb.view import EntityView
from cubicweb.web import stdmsgs
from cubicweb.web.action import Action
from cubicweb.web.form import FieldsForm, FormRenderer
from cubicweb.web.formfields import StringField
from cubicweb.web.formwidgets import CheckBox, TextInput, AjaxWidget


class SendEmailAction(Action):
    id = 'sendemail'
    # XXX should check email is set as well
    __select__ = implements(IEmailable) & match_user_groups('managers', 'users')

    title = _('send email')
    category = 'mainactions'

    def url(self):
        params = {'vid': 'massmailing', '__force_display': 1}
        if self.req.form.has_key('rql'):
            params['rql'] = self.req.form['rql']
        return self.build_url(self.req.relative_path(includeparams=False),
                              **params)

            
class MassMailingForm(FieldsForm):
    id = 'massmailing'
    
    sender = StringField(widget=TextInput({'disabled': 'disabled'}), label=_('From:'))
    recipient = StringField(widget=CheckBox(), label=_('Recipients:'))
    subject = StringField(label=_('Subject:'))
    mailbody = StringField(widget=AjaxWidget(wdgtype='TemplateTextField',
                                             inputid='mailarea'))

    def form_field_vocabulary(self, field):
        if field.name == 'recipient':
            vocab = [(entity.get_email(), entity.eid) for entity in self.rset.entities()]
            return [(label, value) for label, value in vocab if label]
        return super(MassMailingForm, self).form_field_vocabulary(field)
    
    def form_field_value(self, field, values):
        if field.name == 'recipient':
            return [entity.eid for entity in self.rset.entities() if entity.get_email()]
        elif field.name == 'mailbody':
            field.widget.attrs['cubicweb:variables'] = self.get_allowed_substitutions()
        return super(MassMailingForm, self).form_field_value(field, values)

    def form_buttons(self):
        context = {'domid': self.domid,
                   'cancel' : self.req._(stdmsgs.BUTTON_CANCEL),
                   'cancelimgpath' : self.req.external_resource('CANCEL_EMAIL_ICON'),
                   'send' : self.req._('send email'),
                   'sendimgpath' : self.req.external_resource('SEND_EMAIL_ICON'),
                   }
        return ['''<a id="sendbutton" href="javascript: $('%(domid)s').submit()">
<img src="%(sendimgpath)s" alt="%(send)s"/>%(send)s</a>''' % context,
                '''<a id="cancelbutton" href="javascript: history.back()">
<img src="%(cancelimgpath)s" alt="%(cancel)s"/>%(cancel)s</a>''' % context,
                ]
    
    def get_allowed_substitutions(self):
        attrs = []
        for coltype in self.rset.column_types(0):
            eclass = self.vreg.etype_class(coltype)
            attrs.append(eclass.allowed_massmail_keys())
        return sorted(reduce(operator.and_, attrs))

    def build_substitutions_help(self):
        insertLink = u'<a href="javascript: insertText(\'%%(%s)s\', \'emailarea\');">%%(%s)s</a>'
        substs = (u'<div class="substitution">%s</div>' % (insertLink % (subst, subst))
                  for subst in self.get_allowed_substitutions())
        helpmsg = self.req._('You can use any of the following substitutions in your text')
        return u'<div id="substitutions"><span>%s</span>%s</div>' % (
            helpmsg, u'\n'.join(substs))


class MassMailingFormRenderer(FormRenderer):
    button_bar_class = u'toolbar'
    
    def _render_fields(self, fields, w, form):
        w(u'<table class="headersform">')
        for field in fields:
            if field.name == 'mailbody':
                w(u'</table>')
                w(u'<table>')
                w(u'<tr><td><div>')
            else:
                w(u'<tr>')
                w(u'<td class="hlabel">%s</td>' % self.render_label(form, field))
                w(u'<td class="hvalue">')
            w(field.render(form, self))
            if field.name == 'mailbody':
                w(u'</div></td>')
                w(u'<td>%s</td>' % form.build_substitutions_help())
                w(u'</tr>')
            else:
                w(u'</td></tr>')
        w(u'</table>')

    
class MassMailingFormView(EntityView):
    id = 'massmailing'
    __select__ = implements(IEmailable) & match_user_groups('managers', 'users')

    def call(self):
        req = self.req
        req.add_js('cubicweb.widgets.js')
        req.add_css('cubicweb.mailform.css')
        from_addr = '%s <%s>' % (req.user.dc_title(), req.user.get_email())
        form = self.vreg.select_object('forms', 'massmailing', self.req, self.rset,
                                       action='sendmail', domid='sendmail')
        self.w(form.form_render(sender=from_addr, renderer=MassMailingFormRenderer()))


    
