# copyright 2003-2013 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
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
"""functions for schema / permissions (de)serialization using RQL"""

__docformat__ = "restructuredtext en"

import os
from itertools import chain
import json

from logilab.common.shellutils import ProgressBar

from yams import BadSchemaDefinition, schema as schemamod, buildobjs as ybo

from cubicweb import CW_SOFTWARE_ROOT, Binary
from cubicweb.schema import (KNOWN_RPROPERTIES, CONSTRAINTS, ETYPE_NAME_MAP,
                             VIRTUAL_RTYPES, PURE_VIRTUAL_RTYPES)
from cubicweb.server import sqlutils


def group_mapping(cursor, interactive=True):
    """create a group mapping from an rql cursor

    A group mapping has standard group names as key (managers, owners at least)
    and the actual CWGroup entity's eid as associated value.
    In interactive mode (the default), missing groups'eid will be prompted
    from the user.
    """
    res = {}
    for eid, name in cursor.execute('Any G, N WHERE G is CWGroup, G name N',
                                    build_descr=False):
        res[name] = eid
    if not interactive:
        return res
    missing = [g for g in ('owners', 'managers', 'users', 'guests') if not g in res]
    if missing:
        print 'some native groups are missing but the following groups have been found:'
        print '\n'.join('* %s (%s)' % (n, eid) for n, eid in res.items())
        print
        print 'enter the eid of a to group to map to each missing native group'
        print 'or just type enter to skip permissions granted to a group'
        for group in missing:
            while True:
                value = raw_input('eid for group %s: ' % group).strip()
                if not value:
                    continue
                try:
                    eid = int(value)
                except ValueError:
                    print 'eid should be an integer'
                    continue
                for eid_ in res.values():
                    if eid == eid_:
                        break
                else:
                    print 'eid is not a group eid'
                    continue
                res[name] = eid
                break
    return res

def cstrtype_mapping(cursor):
    """cached constraint types mapping"""
    map = dict(cursor.execute('Any T, X WHERE X is CWConstraintType, X name T'))
    return map

# schema / perms deserialization ##############################################

def deserialize_schema(schema, session):
    """return a schema according to information stored in an rql database
    as CWRType and CWEType entities
    """
    repo = session.repo
    dbhelper = repo.system_source.dbhelper
    # XXX bw compat (3.6 migration)
    sqlcu = session.cnxset['system']
    sqlcu.execute("SELECT * FROM cw_CWRType WHERE cw_name='symetric'")
    if sqlcu.fetchall():
        sql = dbhelper.sql_rename_col('cw_CWRType', 'cw_symetric', 'cw_symmetric',
                                      dbhelper.TYPE_MAPPING['Boolean'], True)
        sqlcu.execute(sql)
        sqlcu.execute("UPDATE cw_CWRType SET cw_name='symmetric' WHERE cw_name='symetric'")
        session.commit(False)
    ertidx = {}
    copiedeids = set()
    permsidx = deserialize_ertype_permissions(session)
    schema.reading_from_database = True
    for eid, etype, desc in session.execute(
        'Any X, N, D WHERE X is CWEType, X name N, X description D',
        build_descr=False):
        # base types are already in the schema, skip them
        if etype in schemamod.BASE_TYPES:
            # just set the eid
            eschema = schema.eschema(etype)
            eschema.eid = eid
            ertidx[eid] = etype
            continue
        if etype in ETYPE_NAME_MAP:
            needcopy = False
            netype = ETYPE_NAME_MAP[etype]
            # can't use write rql queries at this point, use raw sql
            sqlexec = session.system_sql
            if sqlexec('SELECT 1 FROM %(p)sCWEType WHERE %(p)sname=%%(n)s'
                       % {'p': sqlutils.SQL_PREFIX}, {'n': netype}).fetchone():
                # the new type already exists, we should copy (eg make existing
                # instances of the old type instances of the new type)
                assert etype.lower() != netype.lower()
                needcopy = True
            else:
                # the new type doesn't exist, we should rename
                sqlexec('UPDATE %(p)sCWEType SET %(p)sname=%%(n)s WHERE %(p)seid=%%(x)s'
                        % {'p': sqlutils.SQL_PREFIX}, {'x': eid, 'n': netype})
                if etype.lower() != netype.lower():
                    alter_table_sql = dbhelper.sql_rename_table(sqlutils.SQL_PREFIX+etype,
                                                                sqlutils.SQL_PREFIX+netype)
                    sqlexec(alter_table_sql)
            sqlexec('UPDATE entities SET type=%(n)s WHERE type=%(x)s',
                    {'x': etype, 'n': netype})
            session.commit(False)
            try:
                sqlexec('UPDATE deleted_entities SET type=%(n)s WHERE type=%(x)s',
                        {'x': etype, 'n': netype})
            except Exception:
                pass
            tocleanup = [eid]
            tocleanup += (eid for eid, cached in repo._type_source_cache.iteritems()
                          if etype == cached[0])
            repo.clear_caches(tocleanup)
            session.commit(False)
            if needcopy:
                ertidx[eid] = netype
                copiedeids.add(eid)
                # copy / CWEType entity removal expected to be done through
                # rename_entity_type in a migration script
                continue
            etype = netype
        ertidx[eid] = etype
        eschema = schema.add_entity_type(
            ybo.EntityType(name=etype, description=desc, eid=eid))
        set_perms(eschema, permsidx)
    for etype, stype in session.execute(
        'Any XN, ETN WHERE X is CWEType, X name XN, X specializes ET, ET name ETN',
        build_descr=False):
        etype = ETYPE_NAME_MAP.get(etype, etype)
        stype = ETYPE_NAME_MAP.get(stype, stype)
        schema.eschema(etype)._specialized_type = stype
        schema.eschema(stype)._specialized_by.append(etype)
    for eid, rtype, desc, sym, il, ftc in session.execute(
        'Any X,N,D,S,I,FTC WHERE X is CWRType, X name N, X description D, '
        'X symmetric S, X inlined I, X fulltext_container FTC', build_descr=False):
        ertidx[eid] = rtype
        rschema = schema.add_relation_type(
            ybo.RelationType(name=rtype, description=desc,
                             symmetric=bool(sym), inlined=bool(il),
                             fulltext_container=ftc, eid=eid))
    cstrsidx = deserialize_rdef_constraints(session)
    pendingrdefs = []
    # closure to factorize common code of attribute/relation rdef addition
    def _add_rdef(rdefeid, seid, reid, oeid, **kwargs):
        rdef = ybo.RelationDefinition(ertidx[seid], ertidx[reid], ertidx[oeid],
                                      constraints=cstrsidx.get(rdefeid, ()),
                                      eid=rdefeid, **kwargs)
        if seid in copiedeids or oeid in copiedeids:
            # delay addition of this rdef. We'll insert them later if needed. We
            # have to do this because:
            #
            # * on etype renaming, we want relation of the old entity type being
            #   redirected to the new type during migration
            #
            # * in the case of a copy, we've to take care that rdef already
            #   existing in the schema are not overwritten by a redirected one,
            #   since we want correct eid on them (redirected rdef will be
            #   removed in rename_entity_type)
            pendingrdefs.append(rdef)
        else:
            # add_relation_def return a RelationDefinitionSchema if it has been
            # actually added (can be None on duplicated relation definitions,
            # e.g. if the relation type is marked as beeing symmetric)
            rdefs = schema.add_relation_def(rdef)
            if rdefs is not None:
                ertidx[rdefeid] = rdefs
                set_perms(rdefs, permsidx)
    # Get the type parameters for additional base types.
    try:
        extra_props = dict(session.execute('Any X, XTP WHERE X is CWAttribute, '
                                           'X extra_props XTP'))
    except Exception:
        session.critical('Previous CRITICAL notification about extra_props is not '
                         'a problem if you are migrating to cubicweb 3.17')
        extra_props = {} # not yet in the schema (introduced by 3.17 migration)
    for values in session.execute(
        'Any X,SE,RT,OE,CARD,ORD,DESC,IDX,FTIDX,I18N,DFLT WHERE X is CWAttribute,'
        'X relation_type RT, X cardinality CARD, X ordernum ORD, X indexed IDX,'
        'X description DESC, X internationalizable I18N, X defaultval DFLT,'
        'X fulltextindexed FTIDX, X from_entity SE, X to_entity OE',
        build_descr=False):
        rdefeid, seid, reid, oeid, card, ord, desc, idx, ftidx, i18n, default = values
        typeparams = extra_props.get(rdefeid)
        typeparams = json.load(typeparams) if typeparams else {}
        _add_rdef(rdefeid, seid, reid, oeid,
                  cardinality=card, description=desc, order=ord,
                  indexed=idx, fulltextindexed=ftidx, internationalizable=i18n,
                  default=default, **typeparams)
    for values in session.execute(
        'Any X,SE,RT,OE,CARD,ORD,DESC,C WHERE X is CWRelation, X relation_type RT,'
        'X cardinality CARD, X ordernum ORD, X description DESC, '
        'X from_entity SE, X to_entity OE, X composite C', build_descr=False):
        rdefeid, seid, reid, oeid, card, ord, desc, comp = values
        _add_rdef(rdefeid, seid, reid, oeid,
                  cardinality=card, description=desc, order=ord,
                  composite=comp)
    for rdef in pendingrdefs:
        try:
            rdefs = schema.add_relation_def(rdef)
        except BadSchemaDefinition:
            continue
        if rdefs is not None:
            set_perms(rdefs, permsidx)
    unique_togethers = {}
    try:
        rset = session.execute(
        'Any X,E,R WHERE '
        'X is CWUniqueTogetherConstraint, '
        'X constraint_of E, X relations R', build_descr=False)
    except Exception:
        session.rollback() # first migration introducing CWUniqueTogetherConstraint cw 3.9.6
    else:
        for values in rset:
            uniquecstreid, eeid, releid = values
            eschema = schema.schema_by_eid(eeid)
            relations = unique_togethers.setdefault(uniquecstreid, (eschema, []))
            rel = ertidx[releid]
            if isinstance(rel, schemamod.RelationDefinitionSchema):
                # not yet migrated 3.9 database ('relations' target type changed
                # to CWRType in 3.10)
                rtype = rel.rtype.type
            else:
                rtype = str(rel)
            relations[1].append(rtype)
        for eschema, unique_together in unique_togethers.itervalues():
            eschema._unique_together.append(tuple(sorted(unique_together)))
    schema.infer_specialization_rules()
    session.commit()
    schema.reading_from_database = False


def deserialize_ertype_permissions(session):
    """return sect action:groups associations for the given
    entity or relation schema with its eid, according to schema's
    permissions stored in the database as [read|add|delete|update]_permission
    relations between CWEType/CWRType and CWGroup entities
    """
    res = {}
    for action in ('read', 'add', 'update', 'delete'):
        rql = 'Any E,N WHERE G is CWGroup, G name N, E %s_permission G' % action
        for eid, gname in session.execute(rql, build_descr=False):
            res.setdefault(eid, {}).setdefault(action, []).append(gname)
        rql = ('Any E,X,EXPR,V WHERE X is RQLExpression, X expression EXPR, '
               'E %s_permission X, X mainvars V' % action)
        for eid, expreid, expr, mainvars in session.execute(rql, build_descr=False):
            # we don't know yet if it's a rql expr for an entity or a relation,
            # so append a tuple to differentiate from groups and so we'll be
            # able to instantiate it later
            res.setdefault(eid, {}).setdefault(action, []).append( (expr, mainvars, expreid) )
    return res

def deserialize_rdef_constraints(session):
    """return the list of relation definition's constraints as instances"""
    res = {}
    for rdefeid, ceid, ct, val in session.execute(
        'Any E, X,TN,V WHERE E constrained_by X, X is CWConstraint, '
        'X cstrtype T, T name TN, X value V', build_descr=False):
        cstr = CONSTRAINTS[ct].deserialize(val)
        cstr.eid = ceid
        res.setdefault(rdefeid, []).append(cstr)
    return res

def set_perms(erschema, permsidx):
    """set permissions on the given erschema according to the permission
    definition dictionary as built by deserialize_ertype_permissions for a
    given erschema's eid
    """
    # reset erschema permissions here to avoid getting yams default anyway
    erschema.permissions = dict((action, ()) for action in erschema.ACTIONS)
    try:
        thispermsdict = permsidx[erschema.eid]
    except KeyError:
        return
    for action, somethings in thispermsdict.iteritems():
        # XXX cw < 3.6.1 bw compat
        if isinstance(erschema, schemamod.RelationDefinitionSchema) and erschema.final and action == 'add':
            action = 'update'
        erschema.permissions[action] = tuple(
            isinstance(p, tuple) and erschema.rql_expression(*p) or p
            for p in somethings)


# schema / perms serialization ################################################

def serialize_schema(cursor, schema):
    """synchronize schema and permissions in the database according to
    current schema
    """
    quiet = os.environ.get('APYCOT_ROOT')
    if not quiet:
        _title = '-> storing the schema in the database '
        print _title,
    execute = cursor.execute
    eschemas = schema.entities()
    if not quiet:
        pb_size = (len(eschemas + schema.relations())
                   + len(CONSTRAINTS)
                   + len([x for x in eschemas if x.specializes()]))
        pb = ProgressBar(pb_size, title=_title)
    else:
        pb = None
    groupmap = group_mapping(cursor, interactive=False)
    # serialize all entity types, assuring CWEType is serialized first for proper
    # is / is_instance_of insertion
    eschemas.remove(schema.eschema('CWEType'))
    eschemas.insert(0, schema.eschema('CWEType'))
    for eschema in eschemas:
        execschemarql(execute, eschema, eschema2rql(eschema, groupmap))
        if pb is not None:
            pb.update()
    # serialize constraint types
    cstrtypemap = {}
    rql = 'INSERT CWConstraintType X: X name %(ct)s'
    for cstrtype in CONSTRAINTS:
        cstrtypemap[cstrtype] = execute(rql, {'ct': unicode(cstrtype)},
                                        build_descr=False)[0][0]
        if pb is not None:
            pb.update()
    # serialize relations
    for rschema in schema.relations():
        # skip virtual relations such as eid, has_text and identity
        if rschema in VIRTUAL_RTYPES:
            if pb is not None:
                pb.update()
            continue
        execschemarql(execute, rschema, rschema2rql(rschema, addrdef=False))
        if rschema.symmetric:
            rdefs = [rdef for k, rdef in rschema.rdefs.iteritems()
                     if (rdef.subject, rdef.object) == k]
        else:
            rdefs = rschema.rdefs.itervalues()
        for rdef in rdefs:
            execschemarql(execute, rdef,
                          rdef2rql(rdef, cstrtypemap, groupmap))
        if pb is not None:
            pb.update()
    # serialize unique_together constraints
    for eschema in eschemas:
        for unique_together in eschema._unique_together:
            execschemarql(execute, eschema, [uniquetogether2rql(eschema, unique_together)])
    # serialize yams inheritance relationships
    for rql, kwargs in specialize2rql(schema):
        execute(rql, kwargs, build_descr=False)
        if pb is not None:
            pb.update()
    if not quiet:
        print


# high level serialization functions

def execschemarql(execute, schema, rqls):
    for rql, kwargs in rqls:
        kwargs['x'] = schema.eid
        rset = execute(rql, kwargs, build_descr=False)
        if schema.eid is None:
            schema.eid = rset[0][0]
        else:
            assert rset

def erschema2rql(erschema, groupmap):
    if isinstance(erschema, schemamod.EntitySchema):
        return eschema2rql(erschema, groupmap=groupmap)
    return rschema2rql(erschema, groupmap=groupmap)

def specialize2rql(schema):
    for eschema in schema.entities():
        if eschema.final:
            continue
        for rql, kwargs in eschemaspecialize2rql(eschema):
            yield rql, kwargs

# etype serialization

def eschema2rql(eschema, groupmap=None):
    """return a list of rql insert statements to enter an entity schema
    in the database as an CWEType entity
    """
    relations, values = eschema_relations_values(eschema)
    # NOTE: 'specializes' relation can't be inserted here since there's no
    # way to make sure the parent type is inserted before the child type
    yield 'INSERT CWEType X: %s' % ','.join(relations) , values
    # entity permissions
    if groupmap is not None:
        for rql, args in _erperms2rql(eschema, groupmap):
            yield rql, args

def eschema_relations_values(eschema):
    values = _ervalues(eschema)
    relations = ['X %s %%(%s)s' % (attr, attr) for attr in sorted(values)]
    return relations, values

def eschemaspecialize2rql(eschema):
    specialized_type = eschema.specializes()
    if specialized_type:
        values = {'x': eschema.eid, 'et': specialized_type.eid}
        yield 'SET X specializes ET WHERE X eid %(x)s, ET eid %(et)s', values

def uniquetogether2rql(eschema, unique_together):
    relations = []
    restrictions = []
    substs = {}
    for i, name in enumerate(unique_together):
        rschema = eschema.schema.rschema(name)
        rtype = 'T%d' % i
        substs[rtype] = rschema.type
        relations.append('C relations %s' % rtype)
        restrictions.append('%(rtype)s name %%(%(rtype)s)s' % {'rtype': rtype})
    relations = ', '.join(relations)
    restrictions = ', '.join(restrictions)
    rql = ('INSERT CWUniqueTogetherConstraint C: '
           '    C constraint_of X, %s  '
           'WHERE '
           '    X eid %%(x)s, %s')
    return rql % (relations, restrictions), substs


def _ervalues(erschema):
    try:
        type_ = unicode(erschema.type)
    except UnicodeDecodeError as e:
        raise Exception("can't decode %s [was %s]" % (erschema.type, e))
    try:
        desc = unicode(erschema.description) or u''
    except UnicodeDecodeError as e:
        raise Exception("can't decode %s [was %s]" % (erschema.description, e))
    return {
        'name': type_,
        'final': erschema.final,
        'description': desc,
        }

# rtype serialization

def rschema2rql(rschema, cstrtypemap=None, addrdef=True, groupmap=None):
    """return a list of rql insert statements to enter a relation schema
    in the database as an CWRType entity
    """
    if rschema.type == 'has_text':
        return
    relations, values = rschema_relations_values(rschema)
    yield 'INSERT CWRType X: %s' % ','.join(relations), values
    if addrdef:
        assert cstrtypemap
        # sort for testing purpose
        for rdef in sorted(rschema.rdefs.itervalues(),
                           key=lambda x: (x.subject, x.object)):
            for rql, values in rdef2rql(rdef, cstrtypemap, groupmap):
                yield rql, values

def rschema_relations_values(rschema):
    values = _ervalues(rschema)
    values['final'] = rschema.final
    values['symmetric'] = rschema.symmetric
    values['inlined'] = rschema.inlined
    if isinstance(rschema.fulltext_container, str):
        values['fulltext_container'] = unicode(rschema.fulltext_container)
    else:
        values['fulltext_container'] = rschema.fulltext_container
    relations = ['X %s %%(%s)s' % (attr, attr) for attr in sorted(values)]
    return relations, values

# rdef serialization

def rdef2rql(rdef, cstrtypemap, groupmap=None):
    # don't serialize infered relations
    if rdef.infered:
        return
    relations, values = _rdef_values(rdef)
    relations.append('X relation_type ER,X from_entity SE,X to_entity OE')
    values.update({'se': rdef.subject.eid, 'rt': rdef.rtype.eid, 'oe': rdef.object.eid})
    if rdef.final:
        etype = 'CWAttribute'
    else:
        etype = 'CWRelation'
    yield 'INSERT %s X: %s WHERE SE eid %%(se)s,ER eid %%(rt)s,OE eid %%(oe)s' % (
        etype, ','.join(relations), ), values
    for rql, values in constraints2rql(cstrtypemap, rdef.constraints):
        yield rql, values
    # no groupmap means "no security insertion"
    if groupmap:
        for rql, args in _erperms2rql(rdef, groupmap):
            yield rql, args

def _rdef_values(rdef):
    amap = {'order': 'ordernum', 'default': 'defaultval'}
    values = {}
    extra = {}
    for prop in rdef.rproperty_defs(rdef.object):
        if prop in ('eid', 'constraints', 'uid', 'infered', 'permissions'):
            continue
        value = getattr(rdef, prop)
        if prop not in KNOWN_RPROPERTIES:
            extra[prop] = value
            continue
        # XXX type cast really necessary?
        if prop in ('indexed', 'fulltextindexed', 'internationalizable'):
            value = bool(value)
        elif prop == 'ordernum':
            value = int(value)
        elif isinstance(value, str):
            value = unicode(value)
        if value is not None and prop == 'default':
            if value is False:
                value = u''
            if not isinstance(value, unicode):
                value = unicode(value)
        values[amap.get(prop, prop)] = value
    if extra:
        values['extra_props'] = Binary(json.dumps(extra))
    relations = ['X %s %%(%s)s' % (attr, attr) for attr in sorted(values)]
    return relations, values

def constraints2rql(cstrtypemap, constraints, rdefeid=None):
    for constraint in constraints:
        values = {'ct': cstrtypemap[constraint.type()],
                  'value': unicode(constraint.serialize()),
                  'x': rdefeid} # when not specified, will have to be set by the caller
        yield 'INSERT CWConstraint X: X value %(value)s, X cstrtype CT, EDEF constrained_by X WHERE \
CT eid %(ct)s, EDEF eid %(x)s', values


def _erperms2rql(erschema, groupmap):
    """return rql insert statements to enter the entity or relation
    schema's permissions in the database as
    [read|add|delete|update]_permission relations between CWEType/CWRType
    and CWGroup entities
    """
    for action in erschema.ACTIONS:
        try:
            grantedto = erschema.action_permissions(action)
        except KeyError:
            # may occurs when modifying persistent schema
            continue
        for group_or_rqlexpr in grantedto:
            if isinstance(group_or_rqlexpr, basestring):
                # group
                try:
                    yield ('SET X %s_permission Y WHERE Y eid %%(g)s, X eid %%(x)s' % action,
                           {'g': groupmap[group_or_rqlexpr]})
                except KeyError:
                    print ("WARNING: group %s used in permissions for %s was ignored because it doesn't exist."
                           " You may want to add it into a precreate.py file" % (group_or_rqlexpr, erschema))
                    continue
            else:
                # rqlexpr
                rqlexpr = group_or_rqlexpr
                yield ('INSERT RQLExpression E: E expression %%(e)s, E exprtype %%(t)s, '
                       'E mainvars %%(v)s, X %s_permission E WHERE X eid %%(x)s' % action,
                       {'e': unicode(rqlexpr.expression),
                        'v': unicode(','.join(sorted(rqlexpr.mainvars))),
                        't': unicode(rqlexpr.__class__.__name__)})

# update functions

def updateeschema2rql(eschema, eid):
    relations, values = eschema_relations_values(eschema)
    values['x'] = eid
    yield 'SET %s WHERE X eid %%(x)s' % ','.join(relations), values

def updaterschema2rql(rschema, eid):
    relations, values = rschema_relations_values(rschema)
    values['x'] = eid
    yield 'SET %s WHERE X eid %%(x)s' % ','.join(relations), values

def updaterdef2rql(rdef, eid):
    relations, values = _rdef_values(rdef)
    values['x'] = eid
    yield 'SET %s WHERE X eid %%(x)s' % ','.join(relations), values
