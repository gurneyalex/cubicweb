"""helper classes to generate simple (X)HTML tags

:organization: Logilab
:copyright: 2009 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
:contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
"""
__docformat__ = "restructuredtext en"

from cubicweb.common.uilib import simple_sgml_tag

class tag(object):
    def __init__(self, name, escapecontent=True):
        self.name = name
        self.escapecontent = escapecontent

    def __call__(self, __content=None, **attrs):
        attrs.setdefault('escapecontent', self.escapecontent)
        return simple_sgml_tag(self.name, __content, **attrs)

input = tag('input')
textarea = tag('textarea')
a = tag('a')
span = tag('span')
div = tag('div', False)
img = tag('img')
label = tag('label')
option = tag('option')
h1 = tag('h1')
h2 = tag('h2')
h3 = tag('h3')
h4 = tag('h4')
h5 = tag('h5')

def select(name, id=None, multiple=False, options=[], **attrs):
    if multiple:
        attrs['multiple'] = 'multiple'
    if id:
        attrs['id'] = id
    attrs['name'] = name
    html = [u'<select %s>' % ' '.join('%s="%s"' % kv
                                      for kv in sorted(attrs.items()))]
    html += options
    html.append(u'</select>')
    return u'\n'.join(html)
