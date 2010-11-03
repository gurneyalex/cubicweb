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
"""Bases HTML components:

* the rql input form
* the logged user link
"""
from __future__ import with_statement

__docformat__ = "restructuredtext en"
_ = unicode

from logilab.mtconverter import xml_escape
from logilab.common.deprecation import class_renamed
from rql import parse

from cubicweb.selectors import (yes, multi_etypes_rset, match_form_params,
                                match_context, configuration_values,
                                anonymous_user, authenticated_user)
from cubicweb.schema import display_name
from cubicweb.utils import wrap_on_write
from cubicweb.uilib import toggle_action
from cubicweb.web import component, uicfg
from cubicweb.web.htmlwidgets import (MenuWidget, PopupBoxMenu, BoxSeparator,
                                      BoxLink)

VISIBLE_PROP_DEF = {
    _('visible'):  dict(type='Boolean', default=True,
                        help=_('display the component or not')),
    }

class RQLInputForm(component.Component):
    """build the rql input form, usually displayed in the header"""
    __regid__ = 'rqlinput'
    cw_property_defs = VISIBLE_PROP_DEF
    visible = False

    def call(self, view=None):
        if hasattr(view, 'filter_box_context_info'):
            rset = view.filter_box_context_info()[0]
        else:
            rset = self.cw_rset
        # display multilines query as one line
        rql = rset is not None and rset.printable_rql(encoded=False) or self._cw.form.get('rql', '')
        rql = rql.replace(u"\n", u" ")
        req = self._cw
        self.w(u'''<div id="rqlinput" class="%s">
          <form action="%s">
<fieldset>
<input type="text" id="rql" name="rql" value="%s"  title="%s" tabindex="%s" accesskey="q" class="searchField" />
</fieldset>
''' % (not self.cw_propval('visible') and 'hidden' or '',
       self._cw.build_url('view'), xml_escape(rql), req._('full text or RQL query'), req.next_tabindex()))
        if self._cw.search_state[0] != 'normal':
            self.w(u'<input type="hidden" name="__mode" value="%s"/>'
                   % ':'.join(req.search_state[1]))
        self.w(u'</form></div>')



class HeaderComponent(component.CtxComponent): # XXX rename properly along with related context
    """if the user is the anonymous user, build a link to login else display a menu
    with user'action (preference, logout, etc...)
    """
    __abstract__ = True
    cw_property_defs = component.override_ctx(
        component.CtxComponent,
        vocabulary=['header-left', 'header-center', 'header-right'])
    # don't want user to hide this component using an cwproperty
    site_wide = True
    context = _('header-center')


class ApplLogo(HeaderComponent):
    """build the instance logo, usually displayed in the header"""
    __regid__ = 'logo'
    order = -1
    context = _('header-left')

    def render(self, w):
        w(u'<a href="%s"><img id="logo" src="%s" alt="logo"/></a>'
          % (self._cw.base_url(), self._cw.uiprops['LOGO']))


class ApplicationName(HeaderComponent):
    """display the instance name"""
    __regid__ = 'appliname'
    context = _('header-center')

    def render(self, w):
        title = self._cw.property_value('ui.site-title')
        if title:
            w(u'<span id="appliName"><a href="%s">%s</a></span>' % (
                self._cw.base_url(), xml_escape(title)))


class CookieLoginComponent(HeaderComponent):
    __regid__ = 'anonuserlink'
    __select__ = (HeaderComponent.__select__ & anonymous_user()
                  & configuration_values('auth-mode', 'cookie'))
    context = 'header-right'
    loginboxid = 'popupLoginBox'
    _html = u"""[<a class="logout" title="%s" href="javascript:
cw.htmlhelpers.popupLoginBox('%s', '__login');">%s</a>]"""

    def render(self, w):
        # XXX bw compat, though should warn about subclasses redefining call
        self.w = w
        self.call()

    def call(self):
        self.w(self._html % (self._cw._('login / password'),
                             self.loginboxid, self._cw._('i18n_login_popup')))
        self._cw.view('logform', rset=self.cw_rset, id=self.loginboxid,
                      klass='%s hidden' % self.loginboxid, title=False,
                      showmessage=False, w=self.w)


class HTTPLoginComponent(CookieLoginComponent):
    __select__ = (HeaderComponent.__select__ & anonymous_user()
                  & configuration_values('auth-mode', 'http'))

    def render(self, w):
        # this redirects to the 'login' controller which in turn
        # will raise a 401/Unauthorized
        req = self._cw
        w(u'[<a class="logout" title="%s" href="%s">%s</a>]'
          % (req._('login / password'), req.build_url('login'), req._('login')))


_UserLink = class_renamed('_UserLink', HeaderComponent)
AnonUserLink = class_renamed('AnonUserLink', CookieLoginComponent)
AnonUserLink.__abstract__ = True
AnonUserLink.__select__ &= yes(1)


class AnonUserStatusLink(HeaderComponent):
    __regid__ = 'userstatus'
    __select__ = HeaderComponent.__select__ & anonymous_user()
    context = _('header-right')
    order = HeaderComponent.order - 10

    def render(self, w):
        w(u'<span class="caption">%s</span>' % self._cw._('anonymous'))


class AuthenticatedUserStatus(AnonUserStatusLink):
    __select__ = HeaderComponent.__select__ & authenticated_user()

    def render(self, w):
        # display useractions and siteactions
        actions = self._cw.vreg['actions'].possible_actions(self._cw, rset=self.cw_rset)
        box = MenuWidget('', 'userActionsBox', _class='', islist=False)
        menu = PopupBoxMenu(self._cw.user.login, isitem=False)
        box.append(menu)
        for action in actions.get('useractions', ()):
            menu.append(BoxLink(action.url(), self._cw._(action.title),
                                action.html_class()))
        if actions.get('useractions') and actions.get('siteactions'):
            menu.append(BoxSeparator())
        for action in actions.get('siteactions', ()):
            menu.append(BoxLink(action.url(), self._cw._(action.title),
                                action.html_class()))
        box.render(w=w)


class ApplicationMessage(component.Component):
    """display messages given using the __message parameter into a special div
    section
    """
    __select__ = yes()
    __regid__ = 'applmessages'
    # don't want user to hide this component using an cwproperty
    cw_property_defs = {}

    def call(self):
        msgs = [msg for msg in (self._cw.get_shared_data('sources_error', pop=True),
                                self._cw.message) if msg]
        self.w(u'<div id="appMsg" onclick="%s" class="%s">\n' %
               (toggle_action('appMsg'), (msgs and ' ' or 'hidden')))
        for msg in msgs:
            self.w(u'<div class="message" id="%s">%s</div>' % (self.domid, msg))
        self.w(u'</div>')


class EtypeRestrictionComponent(component.Component):
    """displays the list of entity types contained in the resultset
    to be able to filter accordingly.
    """
    __regid__ = 'etypenavigation'
    __select__ = multi_etypes_rset() | match_form_params('__restrtype', '__restrtypes',
                                                       '__restrrql')
    cw_property_defs = VISIBLE_PROP_DEF
    # don't want user to hide this component using an cwproperty
    site_wide = True
    visible = False # disabled by default

    def call(self):
        _ = self._cw._
        self.w(u'<div id="etyperestriction">')
        restrtype = self._cw.form.get('__restrtype')
        restrtypes = self._cw.form.get('__restrtypes', '').split(',')
        restrrql = self._cw.form.get('__restrrql')
        if not restrrql:
            rqlst = self.cw_rset.syntax_tree()
            restrrql = rqlst.as_string(self._cw.encoding, self.cw_rset.args)
            restrtypes = self.cw_rset.column_types(0)
        else:
            rqlst = parse(restrrql)
        html = []
        on_etype = False
        etypes = sorted((display_name(self._cw, etype).capitalize(), etype)
                        for etype in restrtypes)
        for elabel, etype in etypes:
            if etype == restrtype:
                html.append(u'<span class="selected">%s</span>' % elabel)
                on_etype = True
            else:
                rqlst.save_state()
                for select in rqlst.children:
                    select.add_type_restriction(select.selection[0], etype)
                newrql = rqlst.as_string(self._cw.encoding, self.cw_rset.args)
                url = self._cw.build_url(rql=newrql, __restrrql=restrrql,
                                         __restrtype=etype, __restrtypes=','.join(restrtypes))
                html.append(u'<span><a href="%s">%s</a></span>' % (
                        xml_escape(url), elabel))
                rqlst.recover()
        if on_etype:
            url = self._cw.build_url(rql=restrrql)
            html.insert(0, u'<span><a href="%s">%s</a></span>' % (
                    url, _('Any')))
        else:
            html.insert(0, u'<span class="selected">%s</span>' % _('Any'))
        self.w(u'&#160;|&#160;'.join(html))
        self.w(u'</div>')

# contextual components ########################################################


class MetaDataComponent(component.EntityCtxComponent):
    __regid__ = 'metadata'
    context = 'navbottom'
    order = 1

    def render_body(self, w):
        self.entity.view('metadata', w=w)


class SectionLayout(component.Layout):
    __select__ = match_context('navtop', 'navbottom',
                               'navcontenttop', 'navcontentbottom')
    cssclass = 'section'

    def render(self, w):
        if self.init_rendering():
            view = self.cw_extra_kwargs['view']
            w(u'<div class="%s %s" id="%s">' % (self.cssclass, view.cssclass,
                                                view.domid))
            with wrap_on_write(w, '<h4>') as wow:
                view.render_title(wow)
            view.render_body(w)
            w(u'</div>\n')
