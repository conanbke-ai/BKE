import unittest

from quality import lint_text, replace_bad_text


class QualityTest(unittest.TestCase):
    def test_dummy_sentence_detected(self):
        self.assertTrue(lint_text('이 문장은 수정이 필요하겠습니다.'))

    def test_broken_sentence_detected(self):
        self.assertTrue(lint_text('바람기를 뜻하지 않습니다보다 친밀감입니다.'))

    def test_bad_sentence_is_replaced_whole(self):
        self.assertEqual(replace_bad_text('수정이 필요하겠습니다.', 'fallback'), 'fallback')


if __name__ == '__main__':
    unittest.main()
