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

from logilab.mtconverter import xml_escape

from cubicweb.selectors import match_user_groups, non_final_entity
from cubicweb.view import EntityView
from cubicweb.schema import display_name
from cubicweb.web.htmlwidgets import BoxWidget, BoxMenu, BoxHtml, RawBoxItem
from cubicweb.web import uicfg
from cubicweb.web.box import BoxTemplate


class EditBox(BoxTemplate):
    """
    box with all actions impacting the entity displayed: edit, copy, delete
    change state, add related entities
    """
    id = 'edit_box'
    __select__ = BoxTemplate.__select__ & non_final_entity()

    title = _('actions')
    order = 2
    # class attributes below are actually stored in the uicfg module since we
    # don't want them to be reloaded
    appearsin_addmenu = uicfg.actionbox_appearsin_addmenu

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
        # build list of actions
        actions = self.vreg['actions'].possible_actions(self.req, self.rset,
                                                        view=view)
        add_menu = BoxMenu(_('add')) # 'addrelated' category
        other_menu = BoxMenu(_('more actions')) # 'moreactions' category
        searchstate = self.req.search_state[0]
        for category, menu in (('mainactions', box),
                               ('addrelated', add_menu),
                               ('moreactions', other_menu)):
            for action in actions.get(category, ()):
                menu.append(self.box_action(action))
        if self.rset and self.rset.rowcount == 1 and \
               not self.schema[self.rset.description[0][0]].is_final() and \
               searchstate == 'normal':
            entity = self.rset.get_entity(0, 0)
            for action in self.schema_actions(entity):
                add_menu.append(action)
            self.workflow_actions(entity, box)
        if box.is_empty() and not other_menu.is_empty():
            box.items = other_menu.items
            other_menu.items = []
        self.add_submenu(box, add_menu, _('add'))
        self.add_submenu(box, other_menu)
        if not box.is_empty():
            box.render(self.w)

    def add_submenu(self, box, submenu, label_prefix=None):
        if len(submenu.items) == 1:
            boxlink = submenu.items[0]
            if label_prefix:
                boxlink.label = u'%s %s' % (label_prefix, boxlink.label)
            box.append(boxlink)
        elif submenu.items:
            box.append(submenu)

    def schema_actions(self, entity):
        user = self.req.user
        actions = []
        _ = self.req._
        eschema = entity.e_schema
        for rschema, teschema, x in self.add_related_schemas(entity):
            if x == 'subject':
                label = 'add %s %s %s %s' % (eschema, rschema, teschema, x)
                url = self.linkto_url(entity, rschema, teschema, 'object')
            else:
                label = 'add %s %s %s %s' % (teschema, rschema, eschema, x)
                url = self.linkto_url(entity, rschema, teschema, 'subject')
            actions.append(self.mk_action(_(label), url))
        return actions

    def add_related_schemas(self, entity):
        """this is actually used ui method to generate 'addrelated' actions from
        the schema.

        If you don't want any auto-generated actions, you should overrides this
        method to return an empty list. If you only want some, you can configure
        them by using uicfg.actionbox_appearsin_addmenu
        """
        req = self.req
        eschema = entity.e_schema
        for role, rschemas in (('subject', eschema.subject_relations()),
                               ('object', eschema.object_relations())):
            for rschema in rschemas:
                if rschema.is_final():
                    continue
                # check the relation can be added as well
                # XXX consider autoform_permissions_overrides?
                if role == 'subject'and not rschema.has_perm(req, 'add',
                                                             fromeid=entity.eid):
                    continue
                if role == 'object'and not rschema.has_perm(req, 'add',
                                                            toeid=entity.eid):
                    continue
                # check the target types can be added as well
                for teschema in rschema.targets(eschema, role):
                    if not self.appearsin_addmenu.etype_get(eschema, rschema,
                                                            role, teschema):
                        continue
                    if teschema.has_local_role('add') or teschema.has_perm(req, 'add'):
                        yield rschema, teschema, role


    def workflow_actions(self, entity, box):
        if entity.e_schema.has_subject_relation('in_state') and entity.in_state:
            _ = self.req._
            menu_title = u'%s: %s' % (_('state'), entity.printable_state)
            menu_items = []
            for tr in entity.possible_transitions():
                url = entity.absolute_url(vid='statuschange', treid=tr.eid)
                menu_items.append(self.mk_action(_(tr.name), url))
            # don't propose to see wf if user can't pass any transition
            if menu_items:
                wfurl = self.build_url('cwetype/%s'%entity.e_schema, vid='workflow')
                menu_items.append(self.mk_action(_('view workflow'), wfurl))
            if entity.workflow_history:
                wfurl = entity.absolute_url(vid='wfhistory')
                menu_items.append(self.mk_action(_('view history'), wfurl))
            box.append(BoxMenu(menu_title, menu_items))
        return None

    def linkto_url(self, entity, rtype, etype, target):
        return self.build_url(vid='creation', etype=etype,
                              __linkto='%s:%s:%s' % (rtype, entity.eid, target),
                              __redirectpath=entity.rest_path(), # should not be url quoted!
                              __redirectvid=self.req.form.get('vid', ''))


class SearchBox(BoxTemplate):
    """display a box with a simple search form"""
    id = 'search_box'

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
    id = 'possible_views_box'
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
    id = 'startup_views_box'
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
    id = 'sidebox'

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
