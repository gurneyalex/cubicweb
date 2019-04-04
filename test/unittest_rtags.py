from logilab.common.testlib import TestCase, unittest_main
from cubicweb.rtags import RelationTags, RelationTagsSet

class RelationTagsTC(TestCase):

    def test_rtags_expansion(self):
        rtags = RelationTags()
        rtags.tag_subject_of(('Societe', 'travaille', '*'), 'primary')
        rtags.tag_subject_of(('*', 'evaluee', '*'), 'secondary')
        rtags.tag_object_of(('*', 'tags', '*'), 'generated')
        self.assertEquals(rtags.get('Note', 'evaluee', '*', 'subject'),
                          'secondary')
        self.assertEquals(rtags.get('Societe', 'travaille', '*', 'subject'),
                          'primary')
        self.assertEquals(rtags.get('Note', 'travaille', '*', 'subject'),
                          None)
        self.assertEquals(rtags.get('Note', 'tags', '*', 'subject'),
                          None)
        self.assertEquals(rtags.get('*', 'tags', 'Note', 'object'),
                          'generated')
        self.assertEquals(rtags.get('Tag', 'tags', '*', 'object'),
                          'generated')

#         self.assertEquals(rtags.rtag('evaluee', 'Note', 'subject'), set(('secondary', 'link')))
#         self.assertEquals(rtags.is_inlined('evaluee', 'Note', 'subject'), False)
#         self.assertEquals(rtags.rtag('evaluee', 'Personne', 'subject'), set(('secondary', 'link')))
#         self.assertEquals(rtags.is_inlined('evaluee', 'Personne', 'subject'), False)
#         self.assertEquals(rtags.rtag('ecrit_par', 'Note', 'object'), set(('inlineview', 'link')))
#         self.assertEquals(rtags.is_inlined('ecrit_par', 'Note', 'object'), True)
#         class Personne2(Personne):
#             id = 'Personne'
#             __rtags__ = {
#                 ('evaluee', 'Note', 'subject') : set(('inlineview',)),
#                 }
#         self.vreg.register_vobject_class(Personne2)
#         rtags = Personne2.rtags
#         self.assertEquals(rtags.rtag('evaluee', 'Note', 'subject'), set(('inlineview', 'link')))
#         self.assertEquals(rtags.is_inlined('evaluee', 'Note', 'subject'), True)
#         self.assertEquals(rtags.rtag('evaluee', 'Personne', 'subject'), set(('secondary', 'link')))
#         self.assertEquals(rtags.is_inlined('evaluee', 'Personne', 'subject'), False)


    def test_rtagset_expansion(self):
        rtags = RelationTagsSet()
        rtags.tag_subject_of(('Societe', 'travaille', '*'), 'primary')
        rtags.tag_subject_of(('*', 'travaille', '*'), 'secondary')
        self.assertEquals(rtags.get('Societe', 'travaille', '*', 'subject'),
                          set(('primary', 'secondary')))
        self.assertEquals(rtags.get('Societe', 'travaille', '*', 'subject'),
                          set(('primary', 'secondary')))
        self.assertEquals(rtags.get('Note', 'travaille', '*', 'subject'),
                          set(('secondary',)))
        self.assertEquals(rtags.get('Note', 'tags', "*", 'subject'),
                          set())

if __name__ == '__main__':
    unittest_main()