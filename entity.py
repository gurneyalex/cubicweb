# copyright 2003-2011 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
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
"""Base class for entity objects manipulated in clients"""

__docformat__ = "restructuredtext en"

from warnings import warn

from logilab.common import interface
from logilab.common.decorators import cached
from logilab.common.deprecation import deprecated
from logilab.mtconverter import TransformData, TransformError, xml_escape

from rql.utils import rqlvar_maker

from cubicweb import Unauthorized, typed_eid, neg_role
from cubicweb.rset import ResultSet
from cubicweb.selectors import yes
from cubicweb.appobject import AppObject
from cubicweb.req import _check_cw_unsafe
from cubicweb.schema import RQLVocabularyConstraint, RQLConstraint
from cubicweb.rqlrewrite import RQLRewriter

from cubicweb.uilib import printable_value, soup2xhtml
from cubicweb.mixins import MI_REL_TRIGGERS
from cubicweb.mttransforms import ENGINE

_marker = object()

def greater_card(rschema, subjtypes, objtypes, index):
    for subjtype in subjtypes:
        for objtype in objtypes:
            card = rschema.rdef(subjtype, objtype).cardinality[index]
            if card in '+*':
                return card
    return '1'

def can_use_rest_path(value):
    """return True if value can be used at the end of a Rest URL path"""
    if value is None:
        return False
    value = unicode(value)
    # the check for ?, /, & are to prevent problems when running
    # behind Apache mod_proxy
    if value == u'' or u'?' in value or u'/' in value or u'&' in value:
        return False
    return True


def remove_ambiguous_rels(attr_set, subjtypes, schema):
    '''remove from `attr_set` the relations of entity types `subjtypes` that have
    different entity type sets as target'''
    for attr in attr_set.copy():
        rschema = schema.rschema(attr)
        if rschema.final:
            continue
        ttypes = None
        for subjtype in subjtypes:
            cur_ttypes = rschema.objects(subjtype)
            if ttypes is None:
                ttypes = cur_ttypes
            elif cur_ttypes != ttypes:
                attr_set.remove(attr)
                break


class Entity(AppObject):
    """an entity instance has e_schema automagically set on
    the class and instances has access to their issuing cursor.

    A property is set for each attribute and relation on each entity's type
    class. Becare that among attributes, 'eid' is *NEITHER* stored in the
    dict containment (which acts as a cache for other attributes dynamically
    fetched)

    :type e_schema: `cubicweb.schema.EntitySchema`
    :ivar e_schema: the entity's schema

    :type rest_var: str
    :cvar rest_var: indicates which attribute should be used to build REST urls
                    If None is specified, the first non-meta attribute will
                    be used

    :type skip_copy_for: list
    :cvar skip_copy_for: a list of relations that should be skipped when copying
                         this kind of entity. Note that some relations such
                         as composite relations or relations that have '?1' as object
                         cardinality are always skipped.
    """
    __registry__ = 'etypes'
    __select__ = yes()

    # class attributes that must be set in class definition
    rest_attr = None
    fetch_attrs = None
    skip_copy_for = ('in_state',)
    # class attributes set automatically at registration time
    e_schema = None

    @classmethod
    def __initialize__(cls, schema):
        """initialize a specific entity class by adding descriptors to access
        entity type's attributes and relations
        """
        etype = cls.__regid__
        assert etype != 'Any', etype
        cls.e_schema = eschema = schema.eschema(etype)
        for rschema, _ in eschema.attribute_definitions():
            if rschema.type == 'eid':
                continue
            setattr(cls, rschema.type, Attribute(rschema.type))
        mixins = []
        for rschema, _, role in eschema.relation_definitions():
            if (rschema, role) in MI_REL_TRIGGERS:
                mixin = MI_REL_TRIGGERS[(rschema, role)]
                if not (issubclass(cls, mixin) or mixin in mixins): # already mixed ?
                    mixins.append(mixin)
                for iface in getattr(mixin, '__implements__', ()):
                    if not interface.implements(cls, iface):
                        interface.extend(cls, iface)
            if role == 'subject':
                attr = rschema.type
            else:
                attr = 'reverse_%s' % rschema.type
            setattr(cls, attr, Relation(rschema, role))
        if mixins:
            # see etype class instantation in cwvreg.ETypeRegistry.etype_class method:
            # due to class dumping, cls is the generated top level class with actual
            # user class as (only) parent. Since we want to be able to override mixins
            # method from this user class, we have to take care to insert mixins after that
            # class
            #
            # note that we don't plug mixins as user class parent since it causes pb
            # with some cases of entity classes inheritance.
            mixins.insert(0, cls.__bases__[0])
            mixins += cls.__bases__[1:]
            cls.__bases__ = tuple(mixins)
            cls.info('plugged %s mixins on %s', mixins, cls)

    fetch_attrs = ('modification_date',)
    @classmethod
    def fetch_order(cls, attr, var):
        """class method used to control sort order when multiple entities of
        this type are fetched
        """
        return cls.fetch_unrelated_order(attr, var)

    @classmethod
    def fetch_unrelated_order(cls, attr, var):
        """class method used to control sort order when multiple entities of
        this type are fetched to use in edition (eg propose them to create a
        new relation on an edited entity).
        """
        if attr == 'modification_date':
            return '%s DESC' % var
        return None

    @classmethod
    def fetch_rql(cls, user, restriction=None, fetchattrs=None, mainvar='X',
                  settype=True, ordermethod='fetch_order'):
        """return a rql to fetch all entities of the class type"""
        # XXX update api and implementation to AST manipulation (see unrelated rql)
        restrictions = restriction or []
        if settype:
            restrictions.append('%s is %s' % (mainvar, cls.__regid__))
        if fetchattrs is None:
            fetchattrs = cls.fetch_attrs
        selection = [mainvar]
        orderby = []
        # start from 26 to avoid possible conflicts with X
        # XXX not enough to be sure it'll be no conflicts
        varmaker = rqlvar_maker(index=26)
        cls._fetch_restrictions(mainvar, varmaker, fetchattrs, selection,
                                orderby, restrictions, user, ordermethod)
        rql = 'Any %s' % ','.join(selection)
        if orderby:
            rql +=  ' ORDERBY %s' % ','.join(orderby)
        rql += ' WHERE %s' % ', '.join(restrictions)
        return rql

    @classmethod
    def _fetch_restrictions(cls, mainvar, varmaker, fetchattrs,
                            selection, orderby, restrictions, user,
                            ordermethod='fetch_order', visited=None):
        eschema = cls.e_schema
        if visited is None:
            visited = set((eschema.type,))
        elif eschema.type in visited:
            # avoid infinite recursion
            return
        else:
            visited.add(eschema.type)
        _fetchattrs = []
        for attr in fetchattrs:
            try:
                rschema = eschema.subjrels[attr]
            except KeyError:
                cls.warning('skipping fetch_attr %s defined in %s (not found in schema)',
                            attr, cls.__regid__)
                continue
            rdef = eschema.rdef(attr)
            if not user.matching_groups(rdef.get_groups('read')):
                continue
            var = varmaker.next()
            selection.append(var)
            restriction = '%s %s %s' % (mainvar, attr, var)
            restrictions.append(restriction)
            if not rschema.final:
                card = rdef.cardinality[0]
                if card not in '?1':
                    cls.warning('bad relation %s specified in fetch attrs for %s',
                                 attr, cls)
                    selection.pop()
                    restrictions.pop()
                    continue
                # XXX we need outer join in case the relation is not mandatory
                # (card == '?')  *or if the entity is being added*, since in
                # that case the relation may still be missing. As we miss this
                # later information here, systematically add it.
                restrictions[-1] += '?'
                targettypes = rschema.objects(eschema.type)
                # XXX user._cw.vreg iiiirk
                etypecls = user._cw.vreg['etypes'].etype_class(targettypes[0])
                if len(targettypes) > 1:
                    # find fetch_attrs common to all destination types
                    fetchattrs = user._cw.vreg['etypes'].fetch_attrs(targettypes)
                    remove_ambiguous_rels(fetchattrs, targettypes, user._cw.vreg.schema)
                else:
                    fetchattrs = etypecls.fetch_attrs
                etypecls._fetch_restrictions(var, varmaker, fetchattrs,
                                             selection, orderby, restrictions,
                                             user, ordermethod, visited=visited)
            if ordermethod is not None:
                orderterm = getattr(cls, ordermethod)(attr, var)
                if orderterm:
                    orderby.append(orderterm)
        return selection, orderby, restrictions

    @classmethod
    @cached
    def _rest_attr_info(cls):
        mainattr, needcheck = 'eid', True
        if cls.rest_attr:
            mainattr = cls.rest_attr
            needcheck = not cls.e_schema.has_unique_values(mainattr)
        else:
            for rschema in cls.e_schema.subject_relations():
                if rschema.final and rschema != 'eid' and cls.e_schema.has_unique_values(rschema):
                    mainattr = str(rschema)
                    needcheck = False
                    break
        if mainattr == 'eid':
            needcheck = False
        return mainattr, needcheck

    @classmethod
    def cw_instantiate(cls, execute, **kwargs):
        """add a new entity of this given type

        Example (in a shell session):

        >>> companycls = vreg['etypes'].etype_class(('Company')
        >>> personcls = vreg['etypes'].etype_class(('Person')
        >>> c = companycls.cw_instantiate(session.execute, name=u'Logilab')
        >>> p = personcls.cw_instantiate(session.execute, firstname=u'John', lastname=u'Doe',
        ...                              works_for=c)

        You can also set relation where the entity has 'object' role by
        prefixing the relation by 'reverse_'.
        """
        rql = 'INSERT %s X' % cls.__regid__
        relations = []
        restrictions = set()
        pending_relations = []
        eschema = cls.e_schema
        qargs = {}
        for attr, value in kwargs.items():
            if attr.startswith('reverse_'):
                attr = attr[len('reverse_'):]
                role = 'object'
            else:
                role = 'subject'
            assert eschema.has_relation(attr, role), '%s %s not found on %s' % (attr, role, eschema)
            rschema = eschema.subjrels[attr] if role == 'subject' else eschema.objrels[attr]
            if not rschema.final and isinstance(value, (tuple, list, set, frozenset)):
                if len(value) == 1:
                    value = iter(value).next()
                else:
                    # prepare IN clause
                    pending_relations.append( (attr, role, value) )
                    continue
            if rschema.final: # attribute
                relations.append('X %s %%(%s)s' % (attr, attr))
            else:
                rvar = attr.upper()
                if role == 'object':
                    relations.append('%s %s X' % (rvar, attr))
                else:
                    relations.append('X %s %s' % (attr, rvar))
                restriction = '%s eid %%(%s)s' % (rvar, attr)
                if not restriction in restrictions:
                    restrictions.add(restriction)
                if hasattr(value, 'eid'):
                    value = value.eid
            qargs[attr] = value
        if relations:
            rql = '%s: %s' % (rql, ', '.join(relations))
        if restrictions:
            rql = '%s WHERE %s' % (rql, ', '.join(restrictions))
        created = execute(rql, qargs).get_entity(0, 0)
        for attr, role, values in pending_relations:
            if role == 'object':
                restr = 'Y %s X' % attr
            else:
                restr = 'X %s Y' % attr
            execute('SET %s WHERE X eid %%(x)s, Y eid IN (%s)' % (
                restr, ','.join(str(getattr(r, 'eid', r)) for r in values)),
                    {'x': created.eid}, build_descr=False)
        return created

    def __init__(self, req, rset=None, row=None, col=0):
        AppObject.__init__(self, req, rset=rset, row=row, col=col)
        self._cw_related_cache = {}
        if rset is not None:
            self.eid = rset[row][col]
        else:
            self.eid = None
        self._cw_is_saved = True
        self.cw_attr_cache = {}

    def __repr__(self):
        return '<Entity %s %s %s at %s>' % (
            self.e_schema, self.eid, self.cw_attr_cache.keys(), id(self))

    def __cmp__(self, other):
        raise NotImplementedError('comparison not implemented for %s' % self.__class__)

    def __json_encode__(self):
        """custom json dumps hook to dump the entity's eid
        which is not part of dict structure itself
        """
        dumpable = dict(self)
        dumpable['eid'] = self.eid
        return dumpable

    def cw_adapt_to(self, interface):
        """return an adapter the entity to the given interface name.

        return None if it can not be adapted.
        """
        try:
            cache = self._cw_adapters_cache
        except AttributeError:
            self._cw_adapters_cache = cache = {}
        try:
            return cache[interface]
        except KeyError:
            adapter = self._cw.vreg['adapters'].select_or_none(
                interface, self._cw, entity=self)
            cache[interface] = adapter
            return adapter

    def has_eid(self): # XXX cw_has_eid
        """return True if the entity has an attributed eid (False
        meaning that the entity has to be created
        """
        try:
            typed_eid(self.eid)
            return True
        except (ValueError, TypeError):
            return False

    def cw_is_saved(self):
        """during entity creation, there is some time during which the entity
        has an eid attributed though it's not saved (eg during
        'before_add_entity' hooks). You can use this method to ensure the entity
        has an eid *and* is saved in its source.
        """
        return self.has_eid() and self._cw_is_saved

    @cached
    def cw_metainformation(self):
        res = dict(zip(('type', 'source', 'extid'), self._cw.describe(self.eid)))
        res['source'] = self._cw.source_defs()[res['source']]
        return res

    def cw_check_perm(self, action):
        self.e_schema.check_perm(self._cw, action, eid=self.eid)

    def cw_has_perm(self, action):
        return self.e_schema.has_perm(self._cw, action, eid=self.eid)

    def view(self, __vid, __registry='views', w=None, initargs=None, **kwargs): # XXX cw_view
        """shortcut to apply a view on this entity"""
        if initargs is None:
            initargs = kwargs
        else:
            initargs.update(kwargs)
        view = self._cw.vreg[__registry].select(__vid, self._cw, rset=self.cw_rset,
                                                row=self.cw_row, col=self.cw_col,
                                                **initargs)
        return view.render(row=self.cw_row, col=self.cw_col, w=w, **kwargs)

    def absolute_url(self, *args, **kwargs): # XXX cw_url
        """return an absolute url to view this entity"""
        # use *args since we don't want first argument to be "anonymous" to
        # avoid potential clash with kwargs
        if args:
            assert len(args) == 1, 'only 0 or 1 non-named-argument expected'
            method = args[0]
        else:
            method = None
        # in linksearch mode, we don't want external urls else selecting
        # the object for use in the relation is tricky
        # XXX search_state is web specific
        use_ext_id = False
        if 'base_url' not in kwargs and \
               getattr(self._cw, 'search_state', ('normal',))[0] == 'normal':
            baseurl = self.cw_metainformation()['source'].get('base-url')
            if baseurl:
                kwargs['base_url'] = baseurl
                use_ext_id = True
        if method in (None, 'view'):
            try:
                kwargs['_restpath'] = self.rest_path(use_ext_id)
            except TypeError:
                warn('[3.4] %s: rest_path() now take use_ext_eid argument, '
                     'please update' % self.__regid__, DeprecationWarning)
                kwargs['_restpath'] = self.rest_path()
        else:
            kwargs['rql'] = 'Any X WHERE X eid %s' % self.eid
        return self._cw.build_url(method, **kwargs)

    def rest_path(self, use_ext_eid=False): # XXX cw_rest_path
        """returns a REST-like (relative) path for this entity"""
        mainattr, needcheck = self._rest_attr_info()
        etype = str(self.e_schema)
        path = etype.lower()
        if mainattr != 'eid':
            value = getattr(self, mainattr)
            if not can_use_rest_path(value):
                mainattr = 'eid'
                path += '/eid'
            elif needcheck:
                # make sure url is not ambiguous
                try:
                    nbresults = self.__unique
                except AttributeError:
                    rql = 'Any COUNT(X) WHERE X is %s, X %s %%(value)s' % (
                        etype, mainattr)
                    nbresults = self.__unique = self._cw.execute(rql, {'value' : value})[0][0]
                if nbresults != 1: # ambiguity?
                    mainattr = 'eid'
                    path += '/eid'
        if mainattr == 'eid':
            if use_ext_eid:
                value = self.cw_metainformation()['extid']
            else:
                value = self.eid
        return '%s/%s' % (path, self._cw.url_quote(value))

    def cw_attr_metadata(self, attr, metadata):
        """return a metadata for an attribute (None if unspecified)"""
        value = getattr(self, '%s_%s' % (attr, metadata), None)
        if value is None and metadata == 'encoding':
            value = self._cw.vreg.property_value('ui.encoding')
        return value

    def printable_value(self, attr, value=_marker, attrtype=None,
                        format='text/html', displaytime=True): # XXX cw_printable_value
        """return a displayable value (i.e. unicode string) which may contains
        html tags
        """
        attr = str(attr)
        if value is _marker:
            value = getattr(self, attr)
        if isinstance(value, basestring):
            value = value.strip()
        if value is None or value == '': # don't use "not", 0 is an acceptable value
            return u''
        if attrtype is None:
            attrtype = self.e_schema.destination(attr)
        props = self.e_schema.rdef(attr)
        if attrtype == 'String':
            # internalinalized *and* formatted string such as schema
            # description...
            if props.internationalizable:
                value = self._cw._(value)
            attrformat = self.cw_attr_metadata(attr, 'format')
            if attrformat:
                return self._cw_mtc_transform(value, attrformat, format,
                                              self._cw.encoding)
        elif attrtype == 'Bytes':
            attrformat = self.cw_attr_metadata(attr, 'format')
            if attrformat:
                encoding = self.cw_attr_metadata(attr, 'encoding')
                return self._cw_mtc_transform(value.getvalue(), attrformat, format,
                                              encoding)
            return u''
        value = printable_value(self._cw, attrtype, value, props,
                                displaytime=displaytime)
        if format == 'text/html':
            value = xml_escape(value)
        return value

    def _cw_mtc_transform(self, data, format, target_format, encoding,
                          _engine=ENGINE):
        trdata = TransformData(data, format, encoding, appobject=self)
        data = _engine.convert(trdata, target_format).decode()
        if format == 'text/html':
            data = soup2xhtml(data, self._cw.encoding)
        return data

    # entity cloning ##########################################################

    def copy_relations(self, ceid): # XXX cw_copy_relations
        """copy relations of the object with the given eid on this
        object (this method is called on the newly created copy, and
        ceid designates the original entity).

        By default meta and composite relations are skipped.
        Overrides this if you want another behaviour
        """
        assert self.has_eid()
        execute = self._cw.execute
        for rschema in self.e_schema.subject_relations():
            if rschema.final or rschema.meta:
                continue
            # skip already defined relations
            if getattr(self, rschema.type):
                continue
            if rschema.type in self.skip_copy_for:
                continue
            # skip composite relation
            rdef = self.e_schema.rdef(rschema)
            if rdef.composite:
                continue
            # skip relation with card in ?1 else we either change the copied
            # object (inlined relation) or inserting some inconsistency
            if rdef.cardinality[1] in '?1':
                continue
            rql = 'SET X %s V WHERE X eid %%(x)s, Y eid %%(y)s, Y %s V' % (
                rschema.type, rschema.type)
            execute(rql, {'x': self.eid, 'y': ceid})
            self.cw_clear_relation_cache(rschema.type, 'subject')
        for rschema in self.e_schema.object_relations():
            if rschema.meta:
                continue
            # skip already defined relations
            if self.related(rschema.type, 'object'):
                continue
            rdef = self.e_schema.rdef(rschema, 'object')
            # skip composite relation
            if rdef.composite:
                continue
            # skip relation with card in ?1 else we either change the copied
            # object (inlined relation) or inserting some inconsistency
            if rdef.cardinality[0] in '?1':
                continue
            rql = 'SET V %s X WHERE X eid %%(x)s, Y eid %%(y)s, V %s Y' % (
                rschema.type, rschema.type)
            execute(rql, {'x': self.eid, 'y': ceid})
            self.cw_clear_relation_cache(rschema.type, 'object')

    # data fetching methods ###################################################

    @cached
    def as_rset(self): # XXX .cw_as_rset
        """returns a resultset containing `self` information"""
        rset = ResultSet([(self.eid,)], 'Any X WHERE X eid %(x)s',
                         {'x': self.eid}, [(self.__regid__,)])
        rset.req = self._cw
        return rset

    def _cw_to_complete_relations(self):
        """by default complete final relations to when calling .complete()"""
        for rschema in self.e_schema.subject_relations():
            if rschema.final:
                continue
            targets = rschema.objects(self.e_schema)
            if rschema.inlined:
                matching_groups = self._cw.user.matching_groups
                if all(matching_groups(e.get_groups('read')) and
                       rschema.rdef(self.e_schema, e).get_groups('read')
                       for e in targets):
                    yield rschema, 'subject'

    def _cw_to_complete_attributes(self, skip_bytes=True, skip_pwd=True):
        for rschema, attrschema in self.e_schema.attribute_definitions():
            # skip binary data by default
            if skip_bytes and attrschema.type == 'Bytes':
                continue
            attr = rschema.type
            if attr == 'eid':
                continue
            # password retreival is blocked at the repository server level
            rdef = rschema.rdef(self.e_schema, attrschema)
            if not self._cw.user.matching_groups(rdef.get_groups('read')) \
                   or (attrschema.type == 'Password' and skip_pwd):
                self.cw_attr_cache[attr] = None
                continue
            yield attr

    _cw_completed = False
    def complete(self, attributes=None, skip_bytes=True, skip_pwd=True): # XXX cw_complete
        """complete this entity by adding missing attributes (i.e. query the
        repository to fill the entity)

        :type skip_bytes: bool
        :param skip_bytes:
          if true, attribute of type Bytes won't be considered
        """
        assert self.has_eid()
        if self._cw_completed:
            return
        if attributes is None:
            self._cw_completed = True
        varmaker = rqlvar_maker()
        V = varmaker.next()
        rql = ['WHERE %s eid %%(x)s' % V]
        selected = []
        for attr in (attributes or self._cw_to_complete_attributes(skip_bytes, skip_pwd)):
            # if attribute already in entity, nothing to do
            if self.cw_attr_cache.has_key(attr):
                continue
            # case where attribute must be completed, but is not yet in entity
            var = varmaker.next()
            rql.append('%s %s %s' % (V, attr, var))
            selected.append((attr, var))
        # +1 since this doen't include the main variable
        lastattr = len(selected) + 1
        # don't fetch extra relation if attributes specified or of the entity is
        # coming from an external source (may lead to error)
        if attributes is None and self.cw_metainformation()['source']['uri'] == 'system':
            # fetch additional relations (restricted to 0..1 relations)
            for rschema, role in self._cw_to_complete_relations():
                rtype = rschema.type
                if self.cw_relation_cached(rtype, role):
                    continue
                # at this point we suppose that:
                # * this is a inlined relation
                # * entity (self) is the subject
                # * user has read perm on the relation and on the target entity
                assert rschema.inlined
                assert role == 'subject'
                var = varmaker.next()
                # keep outer join anyway, we don't want .complete to crash on
                # missing mandatory relation (see #1058267)
                rql.append('%s %s %s?' % (V, rtype, var))
                selected.append(((rtype, role), var))
        if selected:
            # select V, we need it as the left most selected variable
            # if some outer join are included to fetch inlined relations
            rql = 'Any %s,%s %s' % (V, ','.join(var for attr, var in selected),
                                    ','.join(rql))
            try:
                rset = self._cw.execute(rql, {'x': self.eid}, build_descr=False)[0]
            except IndexError:
                raise Exception('unable to fetch attributes for entity with eid %s'
                                % self.eid)
            # handle attributes
            for i in xrange(1, lastattr):
                self.cw_attr_cache[str(selected[i-1][0])] = rset[i]
            # handle relations
            for i in xrange(lastattr, len(rset)):
                rtype, role = selected[i-1][0]
                value = rset[i]
                if value is None:
                    rrset = ResultSet([], rql, {'x': self.eid})
                    rrset.req = self._cw
                else:
                    rrset = self._cw.eid_rset(value)
                self.cw_set_relation_cache(rtype, role, rrset)

    def cw_attr_value(self, name):
        """get value for the attribute relation <name>, query the repository
        to get the value if necessary.

        :type name: str
        :param name: name of the attribute to get
        """
        try:
            return self.cw_attr_cache[name]
        except KeyError:
            if not self.cw_is_saved():
                return None
            rql = "Any A WHERE X eid %%(x)s, X %s A" % name
            try:
                rset = self._cw.execute(rql, {'x': self.eid})
            except Unauthorized:
                self.cw_attr_cache[name] = value = None
            else:
                assert rset.rowcount <= 1, (self, rql, rset.rowcount)
                try:
                    self.cw_attr_cache[name] = value = rset.rows[0][0]
                except IndexError:
                    # probably a multisource error
                    self.critical("can't get value for attribute %s of entity with eid %s",
                                  name, self.eid)
                    if self.e_schema.destination(name) == 'String':
                        self.cw_attr_cache[name] = value = self._cw._('unaccessible')
                    else:
                        self.cw_attr_cache[name] = value = None
            return value

    def related(self, rtype, role='subject', limit=None, entities=False): # XXX .cw_related
        """returns a resultset of related entities

        :param role: is the role played by 'self' in the relation ('subject' or 'object')
        :param limit: resultset's maximum size
        :param entities: if True, the entites are returned; if False, a result set is returned
        """
        try:
            return self._cw_relation_cache(rtype, role, entities, limit)
        except KeyError:
            pass
        if not self.has_eid():
            if entities:
                return []
            return self._cw.empty_rset()
        rql = self.cw_related_rql(rtype, role)
        rset = self._cw.execute(rql, {'x': self.eid})
        self.cw_set_relation_cache(rtype, role, rset)
        return self.related(rtype, role, limit, entities)

    def cw_related_rql(self, rtype, role='subject', targettypes=None):
        rschema = self._cw.vreg.schema[rtype]
        if role == 'subject':
            restriction = 'E eid %%(x)s, E %s X' % rtype
            if targettypes is None:
                targettypes = rschema.objects(self.e_schema)
            else:
                restriction += ', X is IN (%s)' % ','.join(targettypes)
            card = greater_card(rschema, (self.e_schema,), targettypes, 0)
        else:
            restriction = 'E eid %%(x)s, X %s E' % rtype
            if targettypes is None:
                targettypes = rschema.subjects(self.e_schema)
            else:
                restriction += ', X is IN (%s)' % ','.join(targettypes)
            card = greater_card(rschema, targettypes, (self.e_schema,), 1)
        etypecls = self._cw.vreg['etypes'].etype_class(targettypes[0])
        if len(targettypes) > 1:
            fetchattrs = self._cw.vreg['etypes'].fetch_attrs(targettypes)
            # XXX we should fetch ambiguous relation objects too but not
            # recurse on them in _fetch_restrictions; it is easier to remove
            # them completely for now, as it would require an deeper api rewrite
            remove_ambiguous_rels(fetchattrs, targettypes, self._cw.vreg.schema)
        else:
            fetchattrs = etypecls.fetch_attrs
        rql = etypecls.fetch_rql(self._cw.user, [restriction], fetchattrs,
                                 settype=False)
        # optimisation: remove ORDERBY if cardinality is 1 or ? (though
        # greater_card return 1 for those both cases)
        if card == '1':
            if ' ORDERBY ' in rql:
                rql = '%s WHERE %s' % (rql.split(' ORDERBY ', 1)[0],
                                       rql.split(' WHERE ', 1)[1])
        elif not ' ORDERBY ' in rql:
            args = rql.split(' WHERE ', 1)
            # if modification_date already retreived, we should use it instead
            # of adding another variable for sort. This should be be problematic
            # but it's actually with sqlserver, see ticket #694445
            if 'X modification_date ' in args[1]:
                var = args[1].split('X modification_date ', 1)[1].split(',', 1)[0]
                args.insert(1, var.strip())
                rql = '%s ORDERBY %s DESC WHERE %s' % tuple(args)
            else:
                rql = '%s ORDERBY Z DESC WHERE X modification_date Z, %s' % \
                      tuple(args)
        return rql

    # generic vocabulary methods ##############################################

    def cw_unrelated_rql(self, rtype, targettype, role, ordermethod=None,
                         vocabconstraints=True):
        """build a rql to fetch `targettype` entities unrelated to this entity
        using (rtype, role) relation.

        Consider relation permissions so that returned entities may be actually
        linked by `rtype`.
        """
        ordermethod = ordermethod or 'fetch_unrelated_order'
        if isinstance(rtype, basestring):
            rtype = self._cw.vreg.schema.rschema(rtype)
        rdef = rtype.role_rdef(self.e_schema, targettype, role)
        rewriter = RQLRewriter(self._cw)
        # initialize some variables according to the `role` of `self` in the
        # relation:
        # * variable for myself (`evar`) and searched entities (`searchvedvar`)
        # * entity type of the subject (`subjtype`) and of the object
        #   (`objtype`) of the relation
        if role == 'subject':
            evar, searchedvar = 'S', 'O'
            subjtype, objtype = self.e_schema, targettype
        else:
            searchedvar, evar = 'S', 'O'
            objtype, subjtype = self.e_schema, targettype
        # initialize some variables according to `self` existance
        if rdef.role_cardinality(neg_role(role)) in '?1':
            # if cardinality in '1?', we want a target entity which isn't
            # already linked using this relation
            if searchedvar == 'S':
                restriction = ['NOT S %s ZZ' % rtype]
            else:
                restriction = ['NOT ZZ %s O' % rtype]
        elif self.has_eid():
            # elif we have an eid, we don't want a target entity which is
            # already linked to ourself through this relation
            restriction = ['NOT S %s O' % rtype]
        else:
            restriction = []
        if self.has_eid():
            restriction += ['%s eid %%(x)s' % evar]
            args = {'x': self.eid}
            if role == 'subject':
                sec_check_args = {'fromeid': self.eid}
            else:
                sec_check_args = {'toeid': self.eid}
            existant = None # instead of 'SO', improve perfs
        else:
            args = {}
            sec_check_args = {}
            existant = searchedvar
        # retreive entity class for targettype to compute base rql
        etypecls = self._cw.vreg['etypes'].etype_class(targettype)
        rql = etypecls.fetch_rql(self._cw.user, restriction,
                                 mainvar=searchedvar, ordermethod=ordermethod)
        select = self._cw.vreg.parse(self._cw, rql, args).children[0]
        # insert RQL expressions for schema constraints into the rql syntax tree
        if vocabconstraints:
            # RQLConstraint is a subclass for RQLVocabularyConstraint, so they
            # will be included as well
            cstrcls = RQLVocabularyConstraint
        else:
            cstrcls = RQLConstraint
        for cstr in rdef.constraints:
            # consider constraint.mainvars to check if constraint apply
            if isinstance(cstr, cstrcls) and searchedvar in cstr.mainvars:
                if not self.has_eid() and evar in cstr.mainvars:
                    continue
                # compute a varmap suitable to RQLRewriter.rewrite argument
                varmap = dict((v, v) for v in 'SO' if v in select.defined_vars
                              and v in cstr.mainvars)
                # rewrite constraint by constraint since we want a AND between
                # expressions.
                rewriter.rewrite(select, [(varmap, (cstr,))], select.solutions,
                                 args, existant)
        # insert security RQL expressions granting the permission to 'add' the
        # relation into the rql syntax tree, if necessary
        rqlexprs = rdef.get_rqlexprs('add')
        if rqlexprs and not rdef.has_perm(self._cw, 'add', **sec_check_args):
            # compute a varmap suitable to RQLRewriter.rewrite argument
            varmap = dict((v, v) for v in 'SO' if v in select.defined_vars)
            # rewrite all expressions at once since we want a OR between them.
            rewriter.rewrite(select, [(varmap, rqlexprs)], select.solutions,
                             args, existant)
        # ensure we have an order defined
        if not select.orderby:
            select.add_sort_var(select.defined_vars[searchedvar])
        # we're done, turn the rql syntax tree as a string
        rql = select.as_string()
        return rql, args

    def unrelated(self, rtype, targettype, role='subject', limit=None,
                  ordermethod=None): # XXX .cw_unrelated
        """return a result set of target type objects that may be related
        by a given relation, with self as subject or object
        """
        try:
            rql, args = self.cw_unrelated_rql(rtype, targettype, role, ordermethod)
        except Unauthorized:
            return self._cw.empty_rset()
        # XXX should be set in unrelated rql when manipulating the AST
        if limit is not None:
            before, after = rql.split(' WHERE ', 1)
            rql = '%s LIMIT %s WHERE %s' % (before, limit, after)
        return self._cw.execute(rql, args)

    # relations cache handling #################################################

    def cw_relation_cached(self, rtype, role):
        """return None if the given relation isn't already cached on the
        instance, else the content of the cache (a 2-uple (rset, entities)).
        """
        return self._cw_related_cache.get('%s_%s' % (rtype, role))

    def _cw_relation_cache(self, rtype, role, entities=True, limit=None):
        """return values for the given relation if it's cached on the instance,
        else raise `KeyError`
        """
        res = self._cw_related_cache['%s_%s' % (rtype, role)][entities]
        if limit is not None and limit < len(res):
            if entities:
                res = res[:limit]
            else:
                res = res.limit(limit)
        return res

    def cw_set_relation_cache(self, rtype, role, rset):
        """set cached values for the given relation"""
        if rset:
            related = list(rset.entities(0))
            rschema = self._cw.vreg.schema.rschema(rtype)
            if role == 'subject':
                rcard = rschema.rdef(self.e_schema, related[0].e_schema).cardinality[1]
                target = 'object'
            else:
                rcard = rschema.rdef(related[0].e_schema, self.e_schema).cardinality[0]
                target = 'subject'
            if rcard in '?1':
                for rentity in related:
                    rentity._cw_related_cache['%s_%s' % (rtype, target)] = (
                        self.as_rset(), (self,))
        else:
            related = ()
        self._cw_related_cache['%s_%s' % (rtype, role)] = (rset, related)

    def cw_clear_relation_cache(self, rtype=None, role=None):
        """clear cached values for the given relation or the entire cache if
        no relation is given
        """
        if rtype is None:
            self._cw_related_cache = {}
            self._cw_adapters_cache = {}
        else:
            assert role
            self._cw_related_cache.pop('%s_%s' % (rtype, role), None)

    def clear_all_caches(self): # XXX cw_clear_all_caches
        """flush all caches on this entity. Further attributes/relations access
        will triggers new database queries to get back values.

        If you use custom caches on your entity class (take care to @cached!),
        you should override this method to clear them as well.
        """
        # clear attributes cache
        self._cw_completed = False
        self.cw_attr_cache.clear()
        # clear relations cache
        self.cw_clear_relation_cache()
        # rest path unique cache
        try:
            del self.__unique
        except AttributeError:
            pass

    # raw edition utilities ###################################################

    def set_attributes(self, **kwargs): # XXX cw_set_attributes
        _check_cw_unsafe(kwargs)
        assert kwargs
        assert self.cw_is_saved(), "should not call set_attributes while entity "\
               "hasn't been saved yet"
        relations = ['X %s %%(%s)s' % (key, key) for key in kwargs]
        # and now update the database
        kwargs['x'] = self.eid
        self._cw.execute('SET %s WHERE X eid %%(x)s' % ','.join(relations),
                         kwargs)
        kwargs.pop('x')
        # update current local object _after_ the rql query to avoid
        # interferences between the query execution itself and the cw_edited /
        # skip_security machinery
        self.cw_attr_cache.update(kwargs)

    def set_relations(self, **kwargs): # XXX cw_set_relations
        """add relations to the given object. To set a relation where this entity
        is the object of the relation, use 'reverse_'<relation> as argument name.

        Values may be an entity or eid, a list of entities or eids, or None
        (meaning that all relations of the given type from or to this object
        should be deleted).
        """
        # XXX update cache
        _check_cw_unsafe(kwargs)
        for attr, values in kwargs.iteritems():
            if attr.startswith('reverse_'):
                restr = 'Y %s X' % attr[len('reverse_'):]
            else:
                restr = 'X %s Y' % attr
            if values is None:
                self._cw.execute('DELETE %s WHERE X eid %%(x)s' % restr,
                                 {'x': self.eid})
                continue
            if not isinstance(values, (tuple, list, set, frozenset)):
                values = (values,)
            eids = []
            for val in values:
                try:
                    eids.append(str(val.eid))
                except AttributeError:
                    try:
                        eids.append(str(typed_eid(val)))
                    except (ValueError, TypeError):
                        raise Exception('expected an Entity or eid, got %s' % val)
            self._cw.execute('SET %s WHERE X eid %%(x)s, Y eid IN (%s)' % (
                    restr, ','.join(eids)), {'x': self.eid})

    def cw_delete(self, **kwargs):
        assert self.has_eid(), self.eid
        self._cw.execute('DELETE %s X WHERE X eid %%(x)s' % self.e_schema,
                         {'x': self.eid}, **kwargs)

    # server side utilities ####################################################

    def _cw_clear_local_perm_cache(self, action):
        for rqlexpr in self.e_schema.get_rqlexprs(action):
            self._cw.local_perm_cache.pop((rqlexpr.eid, (('x', self.eid),)), None)

    # deprecated stuff #########################################################

    @deprecated('[3.9] use entity.cw_attr_value(attr)')
    def get_value(self, name):
        return self.cw_attr_value(name)

    @deprecated('[3.9] use entity.cw_delete()')
    def delete(self, **kwargs):
        return self.cw_delete(**kwargs)

    @deprecated('[3.9] use entity.cw_attr_metadata(attr, metadata)')
    def attr_metadata(self, attr, metadata):
        return self.cw_attr_metadata(attr, metadata)

    @deprecated('[3.9] use entity.cw_has_perm(action)')
    def has_perm(self, action):
        return self.cw_has_perm(action)

    @deprecated('[3.9] use entity.cw_set_relation_cache(rtype, role, rset)')
    def set_related_cache(self, rtype, role, rset):
        self.cw_set_relation_cache(rtype, role, rset)

    @deprecated('[3.9] use entity.cw_clear_relation_cache(rtype, role)')
    def clear_related_cache(self, rtype=None, role=None):
        self.cw_clear_relation_cache(rtype, role)

    @deprecated('[3.9] use entity.cw_related_rql(rtype, [role, [targettypes]])')
    def related_rql(self, rtype, role='subject', targettypes=None):
        return self.cw_related_rql(rtype, role, targettypes)

    @property
    @deprecated('[3.10] use entity.cw_edited')
    def edited_attributes(self):
        return self.cw_edited

    @property
    @deprecated('[3.10] use entity.cw_edited.skip_security')
    def skip_security_attributes(self):
        return self.cw_edited.skip_security

    @property
    @deprecated('[3.10] use entity.cw_edited.skip_security')
    def _cw_skip_security_attributes(self):
        return self.cw_edited.skip_security

    @property
    @deprecated('[3.10] use entity.cw_edited.querier_pending_relations')
    def querier_pending_relations(self):
        return self.cw_edited.querier_pending_relations

    @deprecated('[3.10] use key in entity.cw_attr_cache')
    def __contains__(self, key):
        return key in self.cw_attr_cache

    @deprecated('[3.10] iter on entity.cw_attr_cache')
    def __iter__(self):
        return iter(self.cw_attr_cache)

    @deprecated('[3.10] use entity.cw_attr_cache[attr]')
    def __getitem__(self, key):
        if key == 'eid':
            warn('[3.7] entity["eid"] is deprecated, use entity.eid instead',
                 DeprecationWarning, stacklevel=2)
            return self.eid
        return self.cw_attr_cache[key]

    @deprecated('[3.10] use entity.cw_attr_cache.get(attr[, default])')
    def get(self, key, default=None):
        return self.cw_attr_cache.get(key, default)

    @deprecated('[3.10] use entity.cw_attr_cache.clear()')
    def clear(self):
        self.cw_attr_cache.clear()
        # XXX clear cw_edited ?

    @deprecated('[3.10] use entity.cw_edited[attr] = value or entity.cw_attr_cache[attr] = value')
    def __setitem__(self, attr, value):
        """override __setitem__ to update self.cw_edited.

        Typically, a before_[update|add]_hook could do::

            entity['generated_attr'] = generated_value

        and this way, cw_edited will be updated accordingly. Also, add
        the attribute to skip_security since we don't want to check security
        for such attributes set by hooks.
        """
        if attr == 'eid':
            warn('[3.7] entity["eid"] = value is deprecated, use entity.eid = value instead',
                 DeprecationWarning, stacklevel=2)
            self.eid = value
        else:
            try:
                self.cw_edited[attr] = value
            except AttributeError:
                self.cw_attr_cache[attr] = value

    @deprecated('[3.10] use del entity.cw_edited[attr]')
    def __delitem__(self, attr):
        """override __delitem__ to update self.cw_edited on cleanup of
        undesired changes introduced in the entity's dict. For example, see the
        code snippet below from the `forge` cube:

        .. sourcecode:: python

            edited = self.entity.cw_edited
            has_load_left = 'load_left' in edited
            if 'load' in edited and self.entity.load_left is None:
                self.entity.load_left = self.entity['load']
            elif not has_load_left and edited:
                # cleanup, this may cause undesired changes
                del self.entity['load_left']
        """
        del self.cw_edited[attr]

    @deprecated('[3.10] use entity.cw_edited.setdefault(attr, default)')
    def setdefault(self, attr, default):
        """override setdefault to update self.cw_edited"""
        return self.cw_edited.setdefault(attr, default)

    @deprecated('[3.10] use entity.cw_edited.pop(attr[, default])')
    def pop(self, attr, *args):
        """override pop to update self.cw_edited on cleanup of
        undesired changes introduced in the entity's dict. See `__delitem__`
        """
        return self.cw_edited.pop(attr, *args)

    @deprecated('[3.10] use entity.cw_edited.update(values)')
    def update(self, values):
        """override update to update self.cw_edited. See `__setitem__`
        """
        self.cw_edited.update(values)


# attribute and relation descriptors ##########################################

class Attribute(object):
    """descriptor that controls schema attribute access"""

    def __init__(self, attrname):
        assert attrname != 'eid'
        self._attrname = attrname

    def __get__(self, eobj, eclass):
        if eobj is None:
            return self
        return eobj.cw_attr_value(self._attrname)

    @deprecated('[3.10] assign to entity.cw_attr_cache[attr] or entity.cw_edited[attr]')
    def __set__(self, eobj, value):
        if hasattr(eobj, 'cw_edited') and not eobj.cw_edited.saved:
            eobj.cw_edited[self._attrname] = value
        else:
            eobj.cw_attr_cache[self._attrname] = value


class Relation(object):
    """descriptor that controls schema relation access"""

    def __init__(self, rschema, role):
        self._rtype = rschema.type
        self._role = role

    def __get__(self, eobj, eclass):
        if eobj is None:
            raise AttributeError('%s can only be accessed from instances'
                                 % self._rtype)
        return eobj.related(self._rtype, self._role, entities=True)

    def __set__(self, eobj, value):
        raise NotImplementedError


from logging import getLogger
from cubicweb import set_log_methods
set_log_methods(Entity, getLogger('cubicweb.entity'))
