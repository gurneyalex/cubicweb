"""basic plot views

:organization: Logilab
:copyright: 2007-2009 LOGILAB S.A. (Paris, FRANCE), license is LGPL.
:contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
"""
__docformat__ = "restructuredtext en"

import os

from logilab.common import flatten
from logilab.mtconverter import html_escape

from cubicweb.vregistry import objectify_selector
from cubicweb.web.views import baseviews

@objectify_selector
def plot_selector(cls, req, rset, *args, **kwargs):
    """accept result set with at least one line and two columns of result
    all columns after second must be of numerical types"""
    if not rset:
        return 0
    if len(rset.rows[0]) < 2:
        return 0
    for etype in rset.description[0]:
        if etype not in ('Int', 'Float'):
            return 0
    return 1

@objectify_selector
def piechart_selector(cls, req, rset, *args, **kwargs):
    if not rset:
        return 0
    if len(rset.rows[0]) < 2:
        return 0
    etype = rset.description[0][1]
    if etype not  in ('Int', 'Float'):
        return 0
    return 1

try:
    import matplotlib
    import sys
    if 'matplotlib.backends' not in sys.modules:
        matplotlib.use('Agg')
    from pylab import figure
except ImportError:
    pass
else:
    class PlotView(baseviews.AnyRsetView):
        id = 'plot'
        title = _('generic plot')
        binary = True
        content_type = 'image/png'
        _plot_count = 0
        __select__ = plot_selector()

        def call(self, width=None, height=None):
            # compute dimensions
            if width is None:
                if 'width' in self.req.form:
                    width = int(self.req.form['width'])
                else:
                    width = 500

            if height is None:
                if 'height' in self.req.form:
                    height = int(self.req.form['height'])
                else:
                    height = 400
            dpi = 100.

            # compute data
            abscisses = [row[0] for row in self.rset]
            courbes = []
            nbcols = len(self.rset.rows[0])
            for col in xrange(1, nbcols):
                courbe = [row[col] for row in self.rset]
                courbes.append(courbe)
            if not courbes:
                raise Exception('no data')
            # plot data
            fig = figure(figsize=(width/dpi, height/dpi), dpi=dpi)
            ax = fig.add_subplot(111)
            colors = 'brgybrgy'
            try:
                float(abscisses[0])
                xlabels = None
            except ValueError:
                xlabels = abscisses
                abscisses = range(len(xlabels))
            for idx, courbe in enumerate(courbes):
                ax.plot(abscisses, courbe, '%sv-' % colors[idx], label=self.rset.description[0][idx+1])
            ax.autoscale_view()
            alldata = flatten(courbes)
            m, M = min(alldata or [0]), max(alldata or [1])
            if m is None: m = 0
            if M is None: M = 0
            margin = float(M-m)/10
            ax.set_ylim(m-margin, M+margin)
            ax.grid(True)
            ax.legend(loc='best')
            if xlabels is not None:
                ax.set_xticks(abscisses)
                ax.set_xticklabels(xlabels)
            try:
                fig.autofmt_xdate()
            except AttributeError:
                # XXX too old version of matplotlib. Ignore safely.
                pass

            # save plot
            filename = self.build_figname()
            fig.savefig(filename, dpi=100)
            img = open(filename, 'rb')
            self.w(img.read())
            img.close()
            os.remove(filename)

        def build_figname(self):
            self.__class__._plot_count += 1
            return '/tmp/burndown_chart_%s_%d.png' % (self.config.appid,
                                                      self.__class__._plot_count)

try:
    from GChartWrapper import Pie, Pie3D
except ImportError:
    pass
else:
    class PieChartView(baseviews.AnyRsetView):
        id = 'piechart'
        pieclass = Pie
        __select__ = piechart_selector()

        def call(self, title=None, width=None, height=None):
            piechart = self.pieclass([(row[1] or 0) for row in self.rset])
            labels = ['%s: %s' % (row[0].encode(self.req.encoding), row[1])
                      for row in self.rset]
            piechart.label(*labels)
            if width is not None:
                height = height or width
                piechart.size(width, height)
            if title:
                piechart.title(title)
            self.w(u'<img src="%s" />' % html_escape(piechart.url))


    class PieChart3DView(PieChartView):
        id = 'piechart3D'
        pieclass = Pie3D
