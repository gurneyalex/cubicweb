"""
generic boxes for CubicWeb web client:

* actions box
* possible views box

additional (disabled by default) boxes
* schema box
* startup views box

:organization: Logilab
:copyright: 2001-2009 LOGILAB S.A. (Paris, FRANCE), license is LGPL v2.
:contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
:license: GNU Lesser General Public License, v2.1 - http://www.gnu.org/licenses
"""
__docformat__ = "restructuredtext en"
_ = unicode

from warnings import warn

from logilab.mtconverter import xml_escape

from cubicweb.selectors import match_user_groups, non_final_entity
from cubicweb.view import EntityView
from cubicweb.schema import display_name
from cubicweb.web.htmlwidgets import BoxWidget, BoxMenu, BoxHtml, RawBoxItem
from cubicweb.web import uicfg
from cubicweb.web.box import BoxTemplate


class EditBox(BoxTemplate): # XXX rename to ActionsBox
    """
    box with all actions impacting the entity displayed: edit, copy, delete
    change state, add related entities
    """
    __regid__ = 'edit_box'
    __select__ = BoxTemplate.__select__ & non_final_entity()

    title = _('actions')
    order = 2

    def call(self, view=None, **kwargs):
        _ = self.req._
        title = _(self.title)
        if self.rset:
            etypes = self.rset.column_types(0)
            if len(etypes) == 1:
                plural = self.rset.rowcount > 1 and 'plural' or ''
                etypelabel = display_name(self.req, iter(etypes).next(), plural)
                title = u'%s - %s' % (title, etypelabel.lower())
        box = BoxWidget(title, self.id, _class="greyBoxFrame")
        self._menus_in_order = []
        self._menus_by_id = {}
        # build list of actions
        actions = self.vreg['actions'].possible_actions(self.req, self.rset,
                                                        view=view)
        other_menu = self._get_menu('moreactions', _('more actions'))
        for category, defaultmenu in (('mainactions', box),
                                      ('moreactions', other_menu),
                                      ('addrelated', None)):
            for action in actions.get(category, ()):
                if category == 'addrelated':
                    warn('"addrelated" category is deprecated, use "moreaction"'
                         ' category w/ "addrelated" submenu',
                         DeprecationWarning)
                    defaultmenu = self._get_menu('addrelated', _('add'), _('add'))
                if action.submenu:
                    menu = self._get_menu(action.submenu)
                else:
                    menu = defaultmenu
                action.fill_menu(self, menu)
        if box.is_empty() and not other_menu.is_empty():
            box.items = other_menu.items
            other_menu.items = []
        else: # ensure 'more actions' menu appears last
            self._menus_in_order.remove(other_menu)
            self._menus_in_order.append(other_menu)
        for submenu in self._menus_in_order:
            self.add_submenu(box, submenu)
        if not box.is_empty():
            box.render(self.w)

    def _get_menu(self, id, title=None, label_prefix=None):
        try:
            return self._menus_by_id[id]
        except KeyError:
            if title is None:
                title = self.req._(id)
            self._menus_by_id[id] = menu = BoxMenu(title)
            menu.label_prefix = label_prefix
            self._menus_in_order.append(menu)
            return menu

    def add_submenu(self, box, submenu, label_prefix=None):
        appendanyway = getattr(submenu, 'append_anyway', False)
        if len(submenu.items) == 1 and not appendanyway:
            boxlink = submenu.items[0]
            if submenu.label_prefix:
                boxlink.label = u'%s %s' % (submenu.label_prefix, boxlink.label)
            box.append(boxlink)
        elif submenu.items:
            box.append(submenu)
        elif appendanyway:
            box.append(RawBoxItem(xml_escape(submenu.label)))


class SearchBox(BoxTemplate):
    """display a box with a simple search form"""
    __regid__ = 'search_box'

    visible = True # enabled by default
    title = _('search')
    order = 0
    formdef = u"""<form action="%s">
<table id="tsearch"><tr><td>
<input id="norql" type="text" accesskey="q" tabindex="%s" title="search text" value="%s" name="rql" />
<input type="hidden" name="__fromsearchbox" value="1" />
<input type="hidden" name="subvid" value="tsearch" />
</td><td>
<input tabindex="%s" type="submit" id="rqlboxsubmit" class="rqlsubmit" value="" />
</td></tr></table>
</form>"""

    def call(self, view=None, **kwargs):
        req = self.req
        if req.form.pop('__fromsearchbox', None):
            rql = req.form.get('rql', '')
        else:
            rql = ''
        form = self.formdef % (req.build_url('view'), req.next_tabindex(),
                               xml_escape(rql), req.next_tabindex())
        title = u"""<span onclick="javascript: toggleVisibility('rqlinput')">%s</span>""" % req._(self.title)
        box = BoxWidget(title, self.id, _class="searchBoxFrame", islist=False, escape=False)
        box.append(BoxHtml(form))
        box.render(self.w)


# boxes disabled by default ###################################################

class PossibleViewsBox(BoxTemplate):
    """display a box containing links to all possible views"""
    __regid__ = 'possible_views_box'
    __select__ = BoxTemplate.__select__ & match_user_groups('users', 'managers')

    visible = False
    title = _('possible views')
    order = 10

    def call(self, **kwargs):
        box = BoxWidget(self.req._(self.title), self.id)
        views = [v for v in self.vreg['views'].possible_views(self.req,
                                                              rset=self.rset)
                 if v.category != 'startupview']
        for category, views in self.sort_actions(views):
            menu = BoxMenu(category)
            for view in views:
                menu.append(self.box_action(view))
            box.append(menu)
        if not box.is_empty():
            box.render(self.w)


class StartupViewsBox(BoxTemplate):
    """display a box containing links to all startup views"""
    __regid__ = 'startup_views_box'
    visible = False # disabled by default
    title = _('startup views')
    order = 70

    def call(self, **kwargs):
        box = BoxWidget(self.req._(self.title), self.id)
        for view in self.vreg['views'].possible_views(self.req, None):
            if view.category == 'startupview':
                box.append(self.box_action(view))

        if not box.is_empty():
            box.render(self.w)


# helper classes ##############################################################

class SideBoxView(EntityView):
    """helper view class to display some entities in a sidebox"""
    __regid__ = 'sidebox'

    def call(self, boxclass='sideBox', title=u''):
        """display a list of entities by calling their <item_vid> view"""
        if title:
            self.w(u'<div class="sideBoxTitle"><span>%s</span></div>' % title)
        self.w(u'<div class="%s"><div class="sideBoxBody">' % boxclass)
        # if not too much entities, show them all in a list
        maxrelated = self.req.property_value('navigation.related-limit')
        if self.rset.rowcount <= maxrelated:
            if len(self.rset) == 1:
                self.wview('incontext', self.rset, row=0)
            elif 1 < len(self.rset) < 5:
                self.wview('csv', self.rset)
            else:
                self.wview('simplelist', self.rset)
        # else show links to display related entities
        else:
            self.rset.limit(maxrelated)
            rql = self.rset.printable_rql(encoded=False)
            self.wview('simplelist', self.rset)
            self.w(u'[<a href="%s">%s</a>]' % (self.build_url(rql=rql),
                                               self.req._('see them all')))
        self.w(u'</div>\n</div>\n')
