# copyright 2003-2010 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
# contact http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This file is part of CubicWeb.
#
# CubicWeb is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# CubicWeb is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with CubicWeb.  If not, see <http://www.gnu.org/licenses/>.
"""Specific views for CWProperty

"""
__docformat__ = "restructuredtext en"
_ = unicode

from logilab.mtconverter import xml_escape

from logilab.common.decorators import cached

from cubicweb import UnknownProperty
from cubicweb.selectors import (one_line_rset, none_rset, implements,
                                match_user_groups, objectify_selector,
                                logged_user_in_rset)
from cubicweb.view import StartupView
from cubicweb.web import uicfg, stdmsgs
from cubicweb.web.form import FormViewMixIn
from cubicweb.web.formfields import FIELDS, StringField
from cubicweb.web.formwidgets import (Select, TextInput, Button, SubmitButton,
                                      FieldWidget)
from cubicweb.web.views import primary, formrenderers

uicfg.primaryview_section.tag_object_of(('*', 'for_user', '*'), 'hidden')

# some string we want to be internationalizable for nicer display of property
# groups
_('navigation')
_('ui')
_('boxes')
_('components')
_('contentnavigation')
_('navigation.combobox-limit')
_('navigation.page-size')
_('navigation.related-limit')
_('navigation.short-line-size')
_('ui.date-format')
_('ui.datetime-format')
_('ui.default-text-format')
_('ui.fckeditor')
_('ui.float-format')
_('ui.language')
_('ui.time-format')
_('open all')
_('ui.main-template')
_('ui.site-title')
_('ui.encoding')
_('category')


def make_togglable_link(nodeid, label):
    """builds a HTML link that switches the visibility & remembers it"""
    action = u"javascript: togglePrefVisibility('%s')" % nodeid
    return u'<a href="%s">%s</a>' % (action, label)

def css_class(someclass):
    return someclass and 'class="%s"' % someclass or ''


class CWPropertyPrimaryView(primary.PrimaryView):
    __select__ = implements('CWProperty')
    skip_none = False


class SystemCWPropertiesForm(FormViewMixIn, StartupView):
    """site-wide properties edition form"""
    __regid__ = 'systempropertiesform'
    __select__ = none_rset() & match_user_groups('managers')
    form_buttons = [SubmitButton()]

    title = _('site configuration')
    category = 'startupview'

    def linkable(self):
        return True

    def url(self):
        """return the url associated with this view. We can omit rql here"""
        return self._cw.build_url('view', vid=self.__regid__)

    def _cookie_name(self, somestr):
        return str('%s_property_%s' % (self._cw.vreg.config.appid, somestr))

    def _group_status(self, group, default=u'hidden'):
        """return css class name 'hidden' (collapsed), or '' (open)"""
        cookies = self._cw.get_cookie()
        cookiename = self._cookie_name(group)
        cookie = cookies.get(cookiename)
        if cookie is None:
            cookies[cookiename] = default
            self._cw.set_cookie(cookies, cookiename, maxage=None)
            status = default
        else:
            status = cookie.value
        return status

    def call(self, **kwargs):
        self._cw.add_js(('cubicweb.edition.js', 'cubicweb.preferences.js', 'cubicweb.ajax.js'))
        self._cw.add_css('cubicweb.preferences.css')
        vreg = self._cw.vreg
        values = self.defined_keys
        groupedopts = {}
        mainopts = {}
        # "self.id=='systempropertiesform'" to skip site wide properties on
        # user's preference but not site's configuration
        for key in vreg.user_property_keys(self.__regid__=='systempropertiesform'):
            parts = key.split('.')
            if parts[0] in vreg and len(parts) >= 3:
                # appobject configuration
                reg = parts[0]
                propid = parts[-1]
                oid = '.'.join(parts[1:-1])
                groupedopts.setdefault(reg, {}).setdefault(oid, []).append(key)
            else:
                mainopts.setdefault(parts[0], []).append(key)
        # precompute form to consume error message
        for group, keys in mainopts.items():
            mainopts[group] = self.form(group, keys, False)

        for group, objects in groupedopts.items():
            for oid, keys in objects.items():
                groupedopts[group][oid] = self.form(group + '-' + oid, keys, True)

        w = self.w
        req = self._cw
        _ = req._
        w(u'<h1>%s</h1>\n' % _(self.title))
        for label, group, form in sorted((_(g), g, f)
                                         for g, f in mainopts.iteritems()):
            status = css_class(self._group_status(group))
            w(u'<h2 class="propertiesform">%s</h2>\n' %
            (make_togglable_link('fieldset_' + group, label.capitalize())))
            w(u'<div id="fieldset_%s" %s>' % (group, status))
            w(u'<fieldset class="preferences">')
            w(form)
            w(u'</fieldset></div>')

        for label, group, objects in sorted((_(g), g, o)
                                            for g, o in groupedopts.iteritems()):
            status = css_class(self._group_status(group))
            w(u'<h2 class="propertiesform">%s</h2>\n' %
              (make_togglable_link('fieldset_' + group, label.capitalize())))
            w(u'<div id="fieldset_%s" %s>' % (group, status))
            # create selection
            sorted_objects =  sorted((self._cw.__('%s_%s' % (group, o)), o, f)
                                           for o, f in objects.iteritems())
            for label, oid, form in sorted_objects:
                w(u'<div class="component">')
                w(u'''<div class="componentLink"><a href="javascript:noop();"
                           onclick="javascript:toggleVisibility('field_%(oid)s_%(group)s')"
                           class="componentTitle">%(label)s</a>''' % {'label':label, 'oid':oid, 'group':group})
                w(u''' (<div class="openlink"><a href="javascript:noop();"
                             onclick="javascript:openFieldset('fieldset_%(group)s')">%(label)s</a></div>)'''
                  % {'label':_('open all'), 'group':group})
                w(u'</div>')
                docmsgid = '%s_%s_description' % (group, oid)
                doc = _(docmsgid)
                if doc != docmsgid:
                    w(u'<div class="helper">%s</div>' % xml_escape(doc).capitalize())
                w(u'</div>')
                w(u'<fieldset id="field_%(oid)s_%(group)s" class="%(group)s preferences hidden">'
                  % {'oid':oid, 'group':group})
                w(form)
                w(u'</fieldset>')
            w(u'</div>')

    @property
    @cached
    def cwprops_rset(self):
        return self._cw.execute('Any P,K,V WHERE P is CWProperty, P pkey K, '
                                'P value V, NOT P for_user U')

    @property
    def defined_keys(self):
        values = {}
        for i, entity in enumerate(self.cwprops_rset.entities()):
            values[entity.pkey] = i
        return values

    def entity_for_key(self, key):
        values = self.defined_keys
        if key in values:
            entity = self.cwprops_rset.get_entity(values[key], 0)
        else:
            entity = self._cw.vreg['etypes'].etype_class('CWProperty')(self._cw)
            entity.eid = self._cw.varmaker.next()
            entity['pkey'] = key
            entity['value'] = self._cw.vreg.property_value(key)
        return entity

    def form(self, formid, keys, splitlabel=False):
        form = self._cw.vreg['forms'].select(
            'composite', self._cw, domid=formid, action=self._cw.build_url(),
            form_buttons=self.form_buttons,
            onsubmit="return validatePrefsForm('%s')" % formid,
            submitmsg=self._cw._('changes applied'))
        path = self._cw.relative_path()
        if '?' in path:
            path, params = path.split('?', 1)
            form.add_hidden('__redirectparams', params)
        form.add_hidden('__redirectpath', path)
        for key in keys:
            self.form_row(form, key, splitlabel)
        renderer = self._cw.vreg['formrenderers'].select('cwproperties', self._cw,
                                                     display_progress_div=False)
        return form.render(renderer=renderer)

    def form_row(self, form, key, splitlabel):
        entity = self.entity_for_key(key)
        if splitlabel:
            label = key.split('.')[-1]
        else:
            label = key
        subform = self._cw.vreg['forms'].select('base', self._cw, entity=entity,
                                                mainform=False)
        subform.append_field(PropertyValueField(name='value', label=label, role='subject',
                                                eidparam=True))
        #subform.vreg = self._cw.vreg
        subform.add_hidden('pkey', key, eidparam=True, role='subject')
        form.add_subform(subform)
        return subform


class CWPropertiesForm(SystemCWPropertiesForm):
    """user's preferences properties edition form"""
    __regid__ = 'propertiesform'
    __select__ = (
        (none_rset() & match_user_groups('users','managers'))
        | (one_line_rset() & match_user_groups('users') & logged_user_in_rset())
        | (one_line_rset() & match_user_groups('managers') & implements('CWUser'))
        )

    title = _('preferences')

    @property
    def user(self):
        if self.cw_rset is None:
            return self._cw.user
        return self.cw_rset.get_entity(self.cw_row or 0, self.cw_col or 0)

    @property
    @cached
    def cwprops_rset(self):
        return self._cw.execute('Any P,K,V WHERE P is CWProperty, P pkey K, P value V,'
                                'P for_user U, U eid %(x)s', {'x': self.user.eid})

    def form_row(self, form, key, splitlabel):
        subform = super(CWPropertiesForm, self).form_row(form, key, splitlabel)
        # if user is in the managers group and the property is being created,
        # we have to set for_user explicitly
        if not subform.edited_entity.has_eid() and self.user.matching_groups('managers'):
            subform.add_hidden('for_user', self.user.eid, eidparam=True, role='subject')


# cwproperty form objects ######################################################

class PlaceHolderWidget(FieldWidget):

    def render(self, form, field, renderer):
        domid = field.dom_id(form)
        # empty span as well else html validation fail (label is refering to
        # this id)
        return '<div id="div:%s"><span id="%s">%s</span></div>' % (
            domid, domid, form._cw._('select a key first'))


class NotEditableWidget(FieldWidget):
    def __init__(self, value, msg=None):
        self.value = value
        self.msg = msg

    def render(self, form, field, renderer):
        domid = field.dom_id(form)
        value = '<span class="value" id="%s">%s</span>' % (domid, self.value)
        if self.msg:
            value + '<div class="helper">%s</div>' % self.msg
        return value


class PropertyKeyField(StringField):
    """specific field for CWProperty.pkey to set the value widget according to
    the selected key
    """
    widget = Select

    def render(self, form, renderer):
        wdg = self.get_widget(form)
        wdg.attrs['tabindex'] = form._cw.next_tabindex()
        wdg.attrs['onchange'] = "javascript:setPropValueWidget('%s', %s)" % (
            form.edited_entity.eid, form._cw.next_tabindex())
        return wdg.render(form, self, renderer)

    def vocabulary(self, form):
        entity = form.edited_entity
        _ = form._cw._
        if entity.has_eid():
            return [(_(entity.pkey), entity.pkey)]
        choices = entity._cw.vreg.user_property_keys()
        return [(u'', u'')] + sorted(zip((_(v) for v in choices), choices))


class PropertyValueField(StringField):
    """specific field for CWProperty.value  which will be different according to
    the selected key type and vocabulary information
    """
    widget = PlaceHolderWidget

    def render(self, form, renderer=None, tabindex=None):
        wdg = self.get_widget(form)
        if tabindex is not None:
            wdg.attrs['tabindex'] = tabindex
        return wdg.render(form, self, renderer)

    def form_init(self, form):
        entity = form.edited_entity
        if not (entity.has_eid() or 'pkey' in entity):
            # no key set yet, just include an empty div which will be filled
            # on key selection
            return
        try:
            pdef = form._cw.vreg.property_info(entity.pkey)
        except UnknownProperty, ex:
            self.warning('%s (you should probably delete that property '
                         'from the database)', ex)
            msg = form._cw._('you should probably delete that property')
            self.widget = NotEditableWidget(entity.printable_value('value'),
                                            '%s (%s)' % (msg, ex))
        if entity.pkey.startswith('system.'):
            msg = form._cw._('value associated to this key is not editable '
                             'manually')
            self.widget = NotEditableWidget(entity.printable_value('value'), msg)
        # XXX race condition when used from CWPropertyForm, should not rely on
        # instance attributes
        self.value = pdef['default']
        self.help = pdef['help']
        vocab = pdef['vocabulary']
        if vocab is not None:
            if callable(vocab):
                # list() just in case its a generator function
                self.choices = list(vocab(form._cw))
            else:
                self.choices = vocab
            wdg = Select()
        elif pdef['type'] == 'String': # else we'll get a TextArea by default
            wdg = TextInput()
        else:
            field = FIELDS[pdef['type']]()
            wdg = field.widget
            if pdef['type'] == 'Boolean':
                self.choices = field.vocabulary(form)
        self.widget = wdg


class CWPropertiesFormRenderer(formrenderers.FormRenderer):
    """specific renderer for properties"""
    __regid__ = 'cwproperties'

    def open_form(self, form, values):
        err = '<div class="formsg"></div>'
        return super(CWPropertiesFormRenderer, self).open_form(form, values) + err

    def _render_fields(self, fields, w, form):
        for field in fields:
            w(u'<div class="preffield">\n')
            if self.display_label:
                w(u'%s' % self.render_label(form, field))
            error = form.field_error(field)
            if error:
                w(u'<span class="error">%s</span>' % err)
            w(u'%s' % self.render_help(form, field))
            w(u'<div class="prefinput">')
            w(field.render(form, self))
            w(u'</div>')
            w(u'</div>')

    def render_buttons(self, w, form):
        w(u'<div>\n')
        for button in form.form_buttons:
            w(u'%s\n' % button.render(form))
        w(u'</div>')


_afs = uicfg.autoform_section
_afs.tag_subject_of(('*', 'for_user', '*'), 'main', 'hidden')
_afs.tag_object_of(('*', 'for_user', '*'), 'main', 'hidden')
_aff = uicfg.autoform_field
_aff.tag_attribute(('CWProperty', 'pkey'), PropertyKeyField)
_aff.tag_attribute(('CWProperty', 'value'), PropertyValueField)
