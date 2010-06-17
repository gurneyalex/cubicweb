"""define default ui properties"""

# CSS stylesheets to include systematically in HTML headers
# use the following line if you *need* to keep the old stylesheet
#STYLESHEETS =       [data('cubicweb.old.css')]
STYLESHEETS =       [data('cubicweb.reset.css'),
                     data('cubicweb.css')]
STYLESHEETS_IE =    [data('cubicweb.ie.css')]
STYLESHEETS_PRINT = [data('cubicweb.print.css')]

# Javascripts files to include systematically in HTML headers
JAVASCRIPTS = [data('jquery.js'),
               data('jquery.corner.js'),
               data('jquery.json.js'),
               data('cubicweb.js'),
               data('cubicweb.compat.js'),
               data('cubicweb.python.js'),
               data('cubicweb.htmlhelpers.js')]

# where is installed fckeditor
FCKEDITOR_PATH = '/usr/share/fckeditor/'

# favicon and logo for the instance
FAVICON = data('favicon.ico')
LOGO = data('logo.png')

# rss logo (link to get the rss view of a selection)
RSS_LOGO = data('rss.png')
RSS_LOGO_16 = data('feed-icon16x16.png')
RSS_LOGO_32 = data('feed-icon32x32.png')

# XXX cleanup resources below, some of them are probably not used
# (at least entity types icons...)

# images
HELP = data('help.png')
SEARCH_GO = data('go.png')
PUCE_UP = data('puce_up.png')
PUCE_DOWN = data('puce_down.png')

# button icons
OK_ICON = data('ok.png')
CANCEL_ICON = data('cancel.png')
APPLY_ICON = data('plus.png')
TRASH_ICON = data('trash_can_small.png')

# icons for entity types
BOOKMARK_ICON = data('icon_bookmark.gif')
EMAILADDRESS_ICON = data('icon_emailaddress.gif')
EUSER_ICON = data('icon_euser.gif')
STATE_ICON = data('icon_state.gif')

# other icons
CALENDAR_ICON = data('calendar.gif')
CANCEL_EMAIL_ICON = data('sendcancel.png')
SEND_EMAIL_ICON = data('sendok.png')
DOWNLOAD_ICON = data('download.gif')
UPLOAD_ICON = data('upload.gif')
GMARKER_ICON = data('gmap_blue_marker.png')
UP_ICON = data('up.gif')

# colors, fonts, etc

# default (body, html)
defaultColor = '#000'
defaultFont = 'Verdana,sans-serif'
defaultSize = '12px'
defaultLineHeight = '1.5'
defaultLineHeightEm = defaultLineHeight + 'em'
baseRhythmBg = 'rhythm18.png'

# XXX
defaultLayoutMargin = '8px'

# header
headerBgColor = '#ff7700'

# h
h1FontSize = '1.5em'
h1BorderBottomStyle = '0.06em solid black'
h1Padding = '0 0 0.14em 0 '
h1Margin = '0.8em 0 0.5em'

h2FontSize = '1.33333em'
h2Padding = '0.4em 0 0.35em 0'
h2Margin = '0'

h3FontSize = '1.16667em'
h3Padding = '0.5em 0 0.57em 0'
h3Margin = '0'

# links
aColor = '#ff4500'
aActiveColor = aVisitedColor = aLinkColor = aColor

# page frame
pageContentBorderColor = '#ccc'
pageContentBgColor = '#fff'
pageContentPadding = '1em'
pageMinHeight = '800px'

# button
buttonBorderColor = '#edecd2'
buttonBgColor = '#fffff8'

# action, search, sideBoxes
actionBoxTitleBgColor = '#cfceb7'
sideBoxBodyBgColor = '#eeedd9'


# table listing
listingBorderColor = '#878787'
