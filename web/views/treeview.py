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
"""Set of tree views / tree-building widgets, some based on jQuery treeview
plugin.
"""
__docformat__ = "restructuredtext en"

from warnings import warn

from logilab.mtconverter import xml_escape
from logilab.common.decorators import cached

from cubicweb.utils import make_uid
from cubicweb.selectors import implements, adaptable
from cubicweb.view import EntityView, EntityAdapter, implements_adapter_compat
from cubicweb.mixins import _done_init
from cubicweb.web import json
from cubicweb.interfaces import ITree
from cubicweb.web.views import baseviews

def treecookiename(treeid):
    return str('%s-treestate' % treeid)


class ITreeAdapter(EntityAdapter):
    """This adapter has to be overriden to be configured using the
    tree_relation, child_role and parent_role class attributes to
    benefit from this default implementation
    """
    __regid__ = 'ITree'
    __select__ = implements(ITree) # XXX for bw compat, else should be abstract

    tree_relation = None
    child_role = 'subject'
    parent_role = 'object'

    @implements_adapter_compat('ITree')
    def children_rql(self):
        """returns RQL to get children

        XXX should be removed from the public interface
        """
        return self.entity.cw_related_rql(self.tree_relation, self.parent_role)

    @implements_adapter_compat('ITree')
    def different_type_children(self, entities=True):
        """return children entities of different type as this entity.

        according to the `entities` parameter, return entity objects or the
        equivalent result set
        """
        res = self.entity.related(self.tree_relation, self.parent_role,
                                  entities=entities)
        eschema = self.entity.e_schema
        if entities:
            return [e for e in res if e.e_schema != eschema]
        return res.filtered_rset(lambda x: x.e_schema != eschema, self.entity.cw_col)

    @implements_adapter_compat('ITree')
    def same_type_children(self, entities=True):
        """return children entities of the same type as this entity.

        according to the `entities` parameter, return entity objects or the
        equivalent result set
        """
        res = self.entity.related(self.tree_relation, self.parent_role,
                                  entities=entities)
        eschema = self.entity.e_schema
        if entities:
            return [e for e in res if e.e_schema == eschema]
        return res.filtered_rset(lambda x: x.e_schema is eschema, self.entity.cw_col)

    @implements_adapter_compat('ITree')
    def is_leaf(self):
        """returns true if this node as no child"""
        return len(self.children()) == 0

    @implements_adapter_compat('ITree')
    def is_root(self):
        """returns true if this node has no parent"""
        return self.parent() is None

    @implements_adapter_compat('ITree')
    def root(self):
        """return the root object"""
        return self._cw.entity_from_eid(self.path()[0])

    @implements_adapter_compat('ITree')
    def parent(self):
        """return the parent entity if any, else None (e.g. if we are on the
        root)
        """
        try:
            return self.entity.related(self.tree_relation, self.child_role,
                                       entities=True)[0]
        except (KeyError, IndexError):
            return None

    @implements_adapter_compat('ITree')
    def children(self, entities=True, sametype=False):
        """return children entities

        according to the `entities` parameter, return entity objects or the
        equivalent result set
        """
        if sametype:
            return self.same_type_children(entities)
        else:
            return self.entity.related(self.tree_relation, self.parent_role,
                                       entities=entities)

    @implements_adapter_compat('ITree')
    def iterparents(self, strict=True):
        def _uptoroot(self):
            curr = self
            while True:
                curr = curr.parent()
                if curr is None:
                    break
                yield curr
                curr = curr.cw_adapt_to('ITree')
        if not strict:
            return chain([self.entity], _uptoroot(self))
        return _uptoroot(self)

    @implements_adapter_compat('ITree')
    def iterchildren(self, _done=None):
        """iterates over the item's children"""
        if _done is None:
            _done = set()
        for child in self.children():
            if child.eid in _done:
                self.error('loop in %s tree', child.__regid__.lower())
                continue
            yield child
            _done.add(child.eid)

    @implements_adapter_compat('ITree')
    def prefixiter(self, _done=None):
        if _done is None:
            _done = set()
        if self.entity.eid in _done:
            return
        _done.add(self.entity.eid)
        yield self.entity
        for child in self.same_type_children():
            for entity in child.cw_adapt_to('ITree').prefixiter(_done):
                yield entity

    @cached
    @implements_adapter_compat('ITree')
    def path(self):
        """returns the list of eids from the root object to this object"""
        path = []
        adapter = self
        entity = adapter.entity
        while entity is not None:
            if entity.eid in path:
                self.error('loop in %s tree', entity.__regid__.lower())
                break
            path.append(entity.eid)
            try:
                # check we are not jumping to another tree
                if (adapter.tree_relation != self.tree_relation or
                    adapter.child_role != self.child_role):
                    break
                entity = adapter.parent()
                adapter = entity.cw_adapt_to('ITree')
            except AttributeError:
                break
        path.reverse()
        return path


class BaseTreeView(baseviews.ListView):
    """base tree view"""
    __regid__ = 'tree'
    __select__ = adaptable('ITree')
    item_vid = 'treeitem'

    def call(self, done=None, **kwargs):
        if done is None:
            done = set()
        super(TreeViewMixIn, self).call(done=done, **kwargs)

    def cell_call(self, row, col=0, vid=None, done=None, **kwargs):
        done, entity = _done_init(done, self, row, col)
        if done is None:
            # entity is actually an error message
            self.w(u'<li class="badcontent">%s</li>' % entity)
            return
        self.open_item(entity)
        entity.view(vid or self.item_vid, w=self.w, **kwargs)
        relatedrset = entity.cw_adapt_to('ITree').children(entities=False)
        self.wview(self.__regid__, relatedrset, 'null', done=done, **kwargs)
        self.close_item(entity)

    def open_item(self, entity):
        self.w(u'<li class="%s">\n' % entity.__regid__.lower())
    def close_item(self, entity):
        self.w(u'</li>\n')



class TreePathView(EntityView):
    """a recursive path view"""
    __regid__ = 'path'
    __select__ = adaptable('ITree')
    item_vid = 'oneline'
    separator = u'&#160;&gt;&#160;'

    def call(self, **kwargs):
        self.w(u'<div class="pathbar">')
        super(TreePathMixIn, self).call(**kwargs)
        self.w(u'</div>')

    def cell_call(self, row, col=0, vid=None, done=None, **kwargs):
        done, entity = _done_init(done, self, row, col)
        if done is None:
            # entity is actually an error message
            self.w(u'<span class="badcontent">%s</span>' % entity)
            return
        parent = entity.cw_adapt_to('ITree').parent_entity()
        if parent:
            parent.view(self.__regid__, w=self.w, done=done)
            self.w(self.separator)
        entity.view(vid or self.item_vid, w=self.w)


# XXX rename regid to ajaxtree/foldabletree or something like that (same for
# treeitemview)
class TreeView(EntityView):
    """ajax tree view, click to expand folder"""

    __regid__ = 'treeview'
    itemvid = 'treeitemview'
    subvid = 'oneline'
    css_classes = 'treeview widget'
    title = _('tree view')

    def _init_params(self, subvid, treeid, initial_load, initial_thru_ajax, morekwargs):
        form = self._cw.form
        if subvid is None:
            subvid = form.pop('treesubvid', self.subvid) # consume it
        if treeid is None:
            treeid = form.pop('treeid', None)
            if treeid is None:
                treeid = 'throw_away' + make_uid('uid')
        if 'morekwargs' in self._cw.form:
            ajaxargs = json.loads(form.pop('morekwargs'))
            # got unicode & python keywords must be strings
            morekwargs.update(dict((str(k), v)
                                   for k, v in ajaxargs.iteritems()))
        toplevel_thru_ajax = form.pop('treeview_top', False) or initial_thru_ajax
        toplevel = toplevel_thru_ajax or (initial_load and not form.get('fname'))
        return subvid, treeid, toplevel_thru_ajax, toplevel

    def _init_headers(self, treeid, toplevel_thru_ajax):
        self._cw.add_css('jquery.treeview.css')
        self._cw.add_js(('cubicweb.ajax.js', 'cubicweb.widgets.js', 'jquery.treeview.js'))
        self._cw.html_headers.add_onload(u"""
jQuery("#tree-%s").treeview({toggle: toggleTree, prerendered: true});""" % treeid)

    def call(self, subvid=None, treeid=None,
             initial_load=True, initial_thru_ajax=False, **morekwargs):
        subvid, treeid, toplevel_thru_ajax, toplevel = self._init_params(
            subvid, treeid, initial_load, initial_thru_ajax, morekwargs)
        ulid = ' '
        if toplevel:
            self._init_headers(treeid, toplevel_thru_ajax)
            ulid = ' id="tree-%s"' % treeid
        self.w(u'<ul%s class="%s">' % (ulid, self.css_classes))
        # XXX force sorting on x.sortvalue() (which return dc_title by default)
        # we need proper ITree & co specification to avoid this.
        # (pb when type ambiguity at the other side of the tree relation,
        # unability to provide generic implementation on eg Folder...)
        for i, entity in enumerate(sorted(self.cw_rset.entities(),
                                          key=lambda x: x.sortvalue())):
            if i+1 < len(self.cw_rset):
                morekwargs['is_last'] = False
            else:
                morekwargs['is_last'] = True
            entity.view(self.itemvid, vid=subvid, parentvid=self.__regid__,
                        treeid=treeid, w=self.w, **morekwargs)
        self.w(u'</ul>')

    def cell_call(self, *args, **allargs):
        """ does not makes much sense until you have to invoke
        somentity.view('treeview') """
        allargs.pop('row')
        allargs.pop('col')
        self.call(*args, **allargs)


class FileTreeView(TreeView):
    """specific version of the treeview to display file trees
    """
    __regid__ = 'filetree'
    css_classes = 'treeview widget filetree'
    title = _('file tree view')

    def call(self, subvid=None, treeid=None, initial_load=True, **kwargs):
        super(FileTreeView, self).call(treeid=treeid, subvid='filetree-oneline',
                                       initial_load=initial_load, **kwargs)

class FileItemInnerView(EntityView):
    """inner view used by the TreeItemView instead of oneline view

    This view adds an enclosing <span> with some specific CSS classes
    around the oneline view. This is needed by the jquery treeview plugin.
    """
    __regid__ = 'filetree-oneline'

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        if entity.cw_adapt_to('ITree') and not entity.is_leaf():
            self.w(u'<div class="folder">%s</div>\n' % entity.view('oneline'))
        else:
            # XXX define specific CSS classes according to mime types
            self.w(u'<div class="file">%s</div>\n' % entity.view('oneline'))


class DefaultTreeViewItemView(EntityView):
    """default treeitem view for entities which don't adapt to ITree"""
    __regid__ = 'treeitemview'

    def cell_call(self, row, col, vid='oneline', treeid=None, **morekwargs):
        assert treeid is not None
        itemview = self._cw.view(vid, self.cw_rset, row=row, col=col)
        last_class = morekwargs['is_last'] and ' class="last"' or ''
        self.w(u'<li%s>%s</li>' % (last_class, itemview))


class TreeViewItemView(EntityView):
    """specific treeitem view for entities which adapt to ITree

    (each item should be expandable if it's not a tree leaf)
    """
    __regid__ = 'treeitemview'
    __select__ = adaptable('ITree')
    default_branch_state_is_open = False

    def open_state(self, eeid, treeid):
        cookies = self._cw.get_cookie()
        treestate = cookies.get(treecookiename(treeid))
        if treestate:
            return str(eeid) in treestate.value.split(';')
        return self.default_branch_state_is_open

    def cell_call(self, row, col, treeid, vid='oneline', parentvid='treeview',
                  is_last=False, **morekwargs):
        w = self.w
        entity = self.cw_rset.get_entity(row, col)
        itree = entity.cw_adapt_to('ITree')
        liclasses = []
        is_open = self.open_state(entity.eid, treeid)
        is_leaf = not hasattr(entity, 'is_leaf') or itree.is_leaf()
        if is_leaf:
            if is_last:
                liclasses.append('last')
            w(u'<li class="%s">' % u' '.join(liclasses))
        else:
            rql = itree.children_rql() % {'x': entity.eid}
            url = xml_escape(self._cw.build_url('json', rql=rql, vid=parentvid,
                                                pageid=self._cw.pageid,
                                                treeid=treeid,
                                                fname='view',
                                                treesubvid=vid,
                                                morekwargs=json.dumps(morekwargs)))
            divclasses = ['hitarea']
            if is_open:
                liclasses.append('collapsable')
                divclasses.append('collapsable-hitarea')
            else:
                liclasses.append('expandable')
                divclasses.append('expandable-hitarea')
            if is_last:
                if is_open:
                    liclasses.append('lastCollapsable')
                    divclasses.append('lastCollapsable-hitarea')
                else:
                    liclasses.append('lastExpandable')
                    divclasses.append('lastExpandable-hitarea')
            if is_open:
                w(u'<li class="%s">' % u' '.join(liclasses))
            else:
                w(u'<li cubicweb:loadurl="%s" class="%s">' % (url, u' '.join(liclasses)))
            if treeid.startswith('throw_away'):
                divtail = ''
            else:
                divtail = """ onclick="asyncRemoteExec('node_clicked', '%s', '%s')" """ % (
                    treeid, entity.eid)
            w(u'<div class="%s"%s></div>' % (u' '.join(divclasses), divtail))

            # add empty <ul> because jquery's treeview plugin checks for
            # sublists presence
            if not is_open:
                w(u'<ul class="placeholder"><li>place holder</li></ul>')
        # the local node info
        self.wview(vid, self.cw_rset, row=row, col=col, **morekwargs)
        if is_open and not is_leaf: #  => rql is defined
            self.wview(parentvid, itree.children(entities=False), subvid=vid,
                       treeid=treeid, initial_load=False, **morekwargs)
        w(u'</li>')

