rql('SET X value "main-template" WHERE X is CWProperty, '
    'X pkey "ui.main-template", X value "main"')
checkpoint()

add_cube('card', update_database=False)
