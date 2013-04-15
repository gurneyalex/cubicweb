# copyright 2010-2012 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
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
"""datafeed parser for xml generated by cubicweb

Example of mapping for CWEntityXMLParser::

  {u'CWUser': {                                        # EntityType
      (u'in_group', u'subject', u'link'): [            # (rtype, role, action)
          (u'CWGroup', {u'linkattr': u'name'})],       #   -> rules = [(EntityType, options), ...]
      (u'tags', u'object', u'link-or-create'): [       # (...)
          (u'Tag', {u'linkattr': u'name'})],           #   -> ...
      (u'use_email', u'subject', u'copy'): [           # (...)
          (u'EmailAddress', {})]                       #   -> ...
      }
   }

"""

from datetime import datetime, timedelta, time
from urllib import urlencode
from cgi import parse_qs # in urlparse with python >= 2.6

from logilab.common.date import todate, totime
from logilab.common.textutils import splitstrip, text_to_dict
from logilab.common.decorators import classproperty

from yams.constraints import BASE_CONVERTERS
from yams.schema import role_name as rn

from cubicweb import ValidationError, RegistryException
from cubicweb.view import Component
from cubicweb.server.sources import datafeed
from cubicweb.server.hook import match_rtype

# XXX see cubicweb.cwvreg.YAMS_TO_PY
# XXX see cubicweb.web.views.xmlrss.SERIALIZERS
DEFAULT_CONVERTERS = BASE_CONVERTERS.copy()
DEFAULT_CONVERTERS['String'] = unicode
DEFAULT_CONVERTERS['Password'] = lambda x: x.encode('utf8')
def convert_date(ustr):
    return todate(datetime.strptime(ustr, '%Y-%m-%d'))
DEFAULT_CONVERTERS['Date'] = convert_date
def convert_datetime(ustr):
    if '.' in ustr: # assume %Y-%m-%d %H:%M:%S.mmmmmm
        ustr = ustr.split('.',1)[0]
    return datetime.strptime(ustr, '%Y-%m-%d %H:%M:%S')
DEFAULT_CONVERTERS['Datetime'] = convert_datetime
# XXX handle timezone, though this will be enough as TZDatetime are
# serialized without time zone by default (UTC time). See
# cw.web.views.xmlrss.SERIALIZERS.
DEFAULT_CONVERTERS['TZDatetime'] = convert_datetime
def convert_time(ustr):
    return totime(datetime.strptime(ustr, '%H:%M:%S'))
DEFAULT_CONVERTERS['Time'] = convert_time
DEFAULT_CONVERTERS['TZTime'] = convert_time
def convert_interval(ustr):
    return time(seconds=int(ustr))
DEFAULT_CONVERTERS['Interval'] = convert_interval

def extract_typed_attrs(eschema, stringdict, converters=DEFAULT_CONVERTERS):
    typeddict = {}
    for rschema in eschema.subject_relations():
        if rschema.final and rschema in stringdict:
            if rschema in ('eid', 'cwuri', 'cwtype', 'cwsource'):
                continue
            attrtype = eschema.destination(rschema)
            value = stringdict[rschema]
            if value is not None:
                value = converters[attrtype](value)
            typeddict[rschema.type] = value
    return typeddict

def rtype_role_rql(rtype, role):
    if role == 'object':
        return 'Y %s X WHERE X eid %%(x)s' % rtype
    else:
        return 'X %s Y WHERE X eid %%(x)s' % rtype


class CWEntityXMLParser(datafeed.DataFeedXMLParser):
    """datafeed parser for the 'xml' entity view

    Most of the logic is delegated to the following components:

    * an "item builder" component, turning an etree xml node into a specific
      python dictionary representing an entity

    * "action" components, selected given an entity, a relation and its role in
      the relation, and responsible to link the entity to given related items
      (eg dictionary)

    So the parser is only doing the gluing service and the connection to the
    source.
    """
    __regid__ = 'cw.entityxml'

    def __init__(self, *args, **kwargs):
        super(CWEntityXMLParser, self).__init__(*args, **kwargs)
        self._parsed_urls = {}
        self._processed_entities = set()

    def select_linker(self, action, rtype, role, entity=None):
        try:
            return self._cw.vreg['components'].select(
                'cw.entityxml.action.%s' % action, self._cw, entity=entity,
                rtype=rtype, role=role, parser=self)
        except RegistryException:
            raise RegistryException('Unknown action %s' % action)

    def list_actions(self):
        reg = self._cw.vreg['components']
        return sorted(clss[0].action for rid, clss in reg.iteritems()
                      if rid.startswith('cw.entityxml.action.'))

    # mapping handling #########################################################

    def add_schema_config(self, schemacfg, checkonly=False):
        """added CWSourceSchemaConfig, modify mapping accordingly"""
        _ = self._cw._
        try:
            rtype = schemacfg.schema.rtype.name
        except AttributeError:
            msg = _("entity and relation types can't be mapped, only attributes "
                    "or relations")
            raise ValidationError(schemacfg.eid, {rn('cw_for_schema', 'subject'): msg})
        if schemacfg.options:
            options = text_to_dict(schemacfg.options)
        else:
            options = {}
        try:
            role = options.pop('role')
            if role not in ('subject', 'object'):
                raise KeyError
        except KeyError:
            msg = _('"role=subject" or "role=object" must be specified in options')
            raise ValidationError(schemacfg.eid, {rn('options', 'subject'): msg})
        try:
            action = options.pop('action')
            linker = self.select_linker(action, rtype, role)
            linker.check_options(options, schemacfg.eid)
        except KeyError:
            msg = _('"action" must be specified in options; allowed values are '
                    '%s') % ', '.join(self.list_actions())
            raise ValidationError(schemacfg.eid, {rn('options', 'subject'): msg})
        except RegistryException:
            msg = _('allowed values for "action" are %s') % ', '.join(self.list_actions())
            raise ValidationError(schemacfg.eid, {rn('options', 'subject'): msg})
        if not checkonly:
            if role == 'subject':
                etype = schemacfg.schema.stype.name
                ttype = schemacfg.schema.otype.name
            else:
                etype = schemacfg.schema.otype.name
                ttype = schemacfg.schema.stype.name
            etyperules = self.source.mapping.setdefault(etype, {})
            etyperules.setdefault((rtype, role, action), []).append(
                (ttype, options) )
            self.source.mapping_idx[schemacfg.eid] = (
                etype, rtype, role, action, ttype)

    def del_schema_config(self, schemacfg, checkonly=False):
        """deleted CWSourceSchemaConfig, modify mapping accordingly"""
        etype, rtype, role, action, ttype = self.source.mapping_idx[schemacfg.eid]
        rules = self.source.mapping[etype][(rtype, role, action)]
        rules = [x for x in rules if not x[0] == ttype]
        if not rules:
            del self.source.mapping[etype][(rtype, role, action)]

    # import handling ##########################################################

    def process(self, url, raise_on_error=False):
        """IDataFeedParser main entry point"""
        if url.startswith('http'): # XXX similar loose test as in parse of sources.datafeed
            url = self.complete_url(url)
        super(CWEntityXMLParser, self).process(url, raise_on_error)

    def parse_etree(self, parent):
        for node in list(parent):
            builder = self._cw.vreg['components'].select(
                'cw.entityxml.item-builder', self._cw, node=node,
                parser=self)
            yield builder.build_item()

    def process_item(self, item, rels):
        """
        item and rels are what's returned by the item builder `build_item` method:

        * `item` is an {attribute: value} dictionary
        * `rels` is for relations and structured as
           {role: {relation: [(related item, related rels)...]}
        """
        entity = self.extid2entity(str(item['cwuri']),  item['cwtype'],
                                   cwsource=item['cwsource'], item=item)
        if entity is None:
            return None
        if entity.eid in self._processed_entities:
            return entity
        self._processed_entities.add(entity.eid)
        if not (self.created_during_pull(entity) or self.updated_during_pull(entity)):
            attrs = extract_typed_attrs(entity.e_schema, item)
            self.update_if_necessary(entity, attrs)
        self.process_relations(entity, rels)
        return entity

    def process_relations(self, entity, rels):
        etype = entity.__regid__
        for (rtype, role, action), rules in self.source.mapping.get(etype, {}).iteritems():
            try:
                related_items = rels[role][rtype]
            except KeyError:
                self.import_log.record_error('relation %s-%s not found in xml export of %s'
                                             % (rtype, role, etype))
                continue
            try:
                linker = self.select_linker(action, rtype, role, entity)
            except RegistryException:
                self.import_log.record_error('no linker for action %s' % action)
            else:
                linker.link_items(related_items, rules)

    def before_entity_copy(self, entity, sourceparams):
        """IDataFeedParser callback"""
        attrs = extract_typed_attrs(entity.e_schema, sourceparams['item'])
        entity.cw_edited.update(attrs)


    def normalize_url(self, url):
        """overriden to add vid=xml"""
        url = super(CWEntityXMLParser, self).normalize_url(url)
        if url.startswith('http'):
            try:
                url, qs = url.split('?', 1)
            except ValueError:
                params = {}
            else:
                params = parse_qs(qs)
            if not 'vid' in params:
                params['vid'] = ['xml']
            return url + '?' + self._cw.build_url_params(**params)
        return url

    def complete_url(self, url, etype=None, known_relations=None):
        """append to the url's query string information about relation that should
        be included in the resulting xml, according to source mapping.

        If etype is not specified, try to guess it using the last path part of
        the url, i.e. the format used by default in cubicweb to map all entities
        of a given type as in 'http://mysite.org/EntityType'.

        If `known_relations` is given, it should be a dictionary of already
        known relations, so they don't get queried again.
        """
        try:
            url, qs = url.split('?', 1)
        except ValueError:
            qs = ''
        # XXX vid will be added by later call to normalize_url (in parent class)
        params = parse_qs(qs)
        if etype is None:
            try:
                etype = url.rsplit('/', 1)[1]
            except ValueError:
                return url + '?' + self._cw.build_url_params(**params)
            try:
                etype = self._cw.vreg.case_insensitive_etypes[etype.lower()]
            except KeyError:
                return url + '?' + self._cw.build_url_params(**params)
        relations = params.setdefault('relation', [])
        for rtype, role, _ in self.source.mapping.get(etype, ()):
            if known_relations and rtype in known_relations.get('role', ()):
                continue
            reldef = '%s-%s' % (rtype, role)
            if not reldef in relations:
                relations.append(reldef)
        return url + '?' + self._cw.build_url_params(**params)

    def complete_item(self, item, rels):
        try:
            return self._parsed_urls[item['cwuri']]
        except KeyError:
            itemurl = self.complete_url(item['cwuri'], item['cwtype'], rels)
            item_rels = list(self.parse(itemurl))
            assert len(item_rels) == 1, 'url %s expected to bring back one '\
                   'and only one entity, got %s' % (itemurl, len(item_rels))
            self._parsed_urls[item['cwuri']] = item_rels[0]
            if rels:
                # XXX (do it better) merge relations
                new_rels = item_rels[0][1]
                new_rels.get('subject', {}).update(rels.get('subject', {}))
                new_rels.get('object', {}).update(rels.get('object', {}))
            return item_rels[0]


class CWEntityXMLItemBuilder(Component):
    __regid__ = 'cw.entityxml.item-builder'

    def __init__(self, _cw, parser, node, **kwargs):
        super(CWEntityXMLItemBuilder, self).__init__(_cw, **kwargs)
        self.parser = parser
        self.node = node

    def build_item(self):
        """parse a XML document node and return two dictionaries defining (part
        of) an entity:

        - {attribute: value}
        - {role: {relation: [(related item, related rels)...]}
        """
        node = self.node
        item = dict(node.attrib.items())
        item['cwtype'] = unicode(node.tag)
        item.setdefault('cwsource', None)
        try:
            item['eid'] = int(item['eid'])
        except KeyError:
            # cw < 3.11 compat mode XXX
            item['eid'] = int(node.find('eid').text)
            item['cwuri'] = node.find('cwuri').text
        rels = {}
        for child in node:
            role = child.get('role')
            if role:
                # relation
                related = rels.setdefault(role, {}).setdefault(child.tag, [])
                related += self.parser.parse_etree(child)
            elif child.text:
                # attribute
                item[child.tag] = unicode(child.text)
            else:
                # None attribute (empty tag)
                item[child.tag] = None
        return item, rels


class CWEntityXMLActionCopy(Component):
    """implementation of cubicweb entity xml parser's'copy' action

    Takes no option.
    """
    __regid__ = 'cw.entityxml.action.copy'

    def __init__(self, _cw, parser, rtype, role, entity=None, **kwargs):
        super(CWEntityXMLActionCopy, self).__init__(_cw, **kwargs)
        self.parser = parser
        self.rtype = rtype
        self.role = role
        self.entity = entity

    @classproperty
    def action(cls):
        return cls.__regid__.rsplit('.', 1)[-1]

    def check_options(self, options, eid):
        self._check_no_options(options, eid)

    def _check_no_options(self, options, eid, msg=None):
        if options:
            if msg is None:
                msg = self._cw._("'%s' action doesn't take any options") % self.action
            raise ValidationError(eid, {rn('options', 'subject'): msg})

    def link_items(self, others, rules):
        assert not any(x[1] for x in rules), "'copy' action takes no option"
        ttypes = frozenset([x[0] for x in rules])
        eids = [] # local eids
        for item, rels in others:
            if item['cwtype'] in ttypes:
                item, rels = self.parser.complete_item(item, rels)
                other_entity = self.parser.process_item(item, rels)
                if other_entity is not None:
                    eids.append(other_entity.eid)
        if eids:
            self._set_relation(eids)
        else:
            self._clear_relation(ttypes)

    def _clear_relation(self, ttypes):
        if not self.parser.created_during_pull(self.entity):
            if len(ttypes) > 1:
                typerestr = ', Y is IN(%s)' % ','.join(ttypes)
            else:
                typerestr = ', Y is %s' % ','.join(ttypes)
            self._cw.execute('DELETE ' + rtype_role_rql(self.rtype, self.role) + typerestr,
                             {'x': self.entity.eid})

    def _set_relation(self, eids):
        assert eids
        rtype = self.rtype
        rqlbase = rtype_role_rql(rtype, self.role)
        eidstr = ','.join(str(eid) for eid in eids)
        self._cw.execute('DELETE %s, NOT Y eid IN (%s)' % (rqlbase, eidstr),
                         {'x': self.entity.eid})
        if self.role == 'object':
            rql = 'SET %s, Y eid IN (%s), NOT Y %s X' % (rqlbase, eidstr, rtype)
        else:
            rql = 'SET %s, Y eid IN (%s), NOT X %s Y' % (rqlbase, eidstr, rtype)
        self._cw.execute(rql, {'x': self.entity.eid})


class CWEntityXMLActionLink(CWEntityXMLActionCopy):
    """implementation of cubicweb entity xml parser's'link' action

    requires a 'linkattr' option to control search of the linked entity.
    """
    __regid__ = 'cw.entityxml.action.link'

    def check_options(self, options, eid):
        if not 'linkattr' in options:
            msg = self._cw._("'%s' action requires 'linkattr' option") % self.action
            raise ValidationError(eid, {rn('options', 'subject'): msg})

    create_when_not_found = False

    def link_items(self, others, rules):
        for ttype, options in rules:
            searchattrs = splitstrip(options.get('linkattr', ''))
            self._related_link(ttype, others, searchattrs)

    def _related_link(self, ttype, others, searchattrs):
        def issubset(x,y):
            return all(z in y for z in x)
        eids = [] # local eids
        log = self.parser.import_log
        for item, rels in others:
            if item['cwtype'] != ttype:
                continue
            if not issubset(searchattrs, item):
                item, rels = self.parser.complete_item(item, rels)
                if not issubset(searchattrs, item):
                    log.record_error('missing attribute, got %s expected keys %s'
                                     % (item, searchattrs))
                    continue
            # XXX str() needed with python < 2.6
            kwargs = dict((str(attr), item[attr]) for attr in searchattrs)
            targets = self._find_entities(item, kwargs)
            if len(targets) == 1:
                entity = targets[0]
            elif not targets and self.create_when_not_found:
                entity = self._cw.create_entity(item['cwtype'], **kwargs)
            else:
                if len(targets) > 1:
                    log.record_error('ambiguous link: found %s entity %s with attributes %s'
                                     % (len(targets), item['cwtype'], kwargs))
                else:
                    log.record_error('can not find %s entity with attributes %s'
                                     % (item['cwtype'], kwargs))
                continue
            eids.append(entity.eid)
            self.parser.process_relations(entity, rels)
        if eids:
            self._set_relation(eids)
        else:
            self._clear_relation((ttype,))

    def _find_entities(self, item, kwargs):
        return tuple(self._cw.find_entities(item['cwtype'], **kwargs))


class CWEntityXMLActionLinkInState(CWEntityXMLActionLink):
    """custom implementation of cubicweb entity xml parser's'link' action for
    in_state relation
    """
    __select__ = match_rtype('in_state')

    def check_options(self, options, eid):
        super(CWEntityXMLActionLinkInState, self).check_options(options, eid)
        if not 'name' in options['linkattr']:
            msg = self._cw._("'%s' action for in_state relation should at least have 'linkattr=name' option") % self.action
            raise ValidationError(eid, {rn('options', 'subject'): msg})

    def _find_entities(self, item, kwargs):
        assert 'name' in item # XXX else, complete_item
        state_name = item['name']
        wf = self.entity.cw_adapt_to('IWorkflowable').current_workflow
        state = wf.state_by_name(state_name)
        if state is None:
            return ()
        return (state,)


class CWEntityXMLActionLinkOrCreate(CWEntityXMLActionLink):
    """implementation of cubicweb entity xml parser's'link-or-create' action

    requires a 'linkattr' option to control search of the linked entity.
    """
    __regid__ = 'cw.entityxml.action.link-or-create'
    create_when_not_found = True
