"""YouTube author-description identity and canonical-link regressions."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('youtube_metadata', ROOT/'plugins/deepmodebot/skills/deepmodebot/assets/scrape/yt_meta.py')
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)


class AuthorDescriptionTests(unittest.TestCase):
    def html(self, player=True, player_id='video-id', description='Repo https://github.com/microsoft/TokenEconomizer'):
        data={'contents':{'twoColumnWatchNextResults':{'results':{'results':{'contents':[
            {'videoPrimaryInfoRenderer':{'title':{'simpleText':'Source video'}}},
            {'videoSecondaryInfoRenderer':{'attributedDescription':{'content':'Repo https://github.com/microsoft/TokenEco...'}}}
        ]}}}}}
        document='var ytInitialData = '+json.dumps(data)+';'
        if player:
            document+='var ytInitialPlayerResponse = '+json.dumps({'videoDetails':{'videoId':player_id,'shortDescription':description}})+';'
        return document

    def test_complete_author_description_preserves_the_actual_repository_url(self):
        result=metadata.parse('video-id',self.html())
        self.assertIn('https://github.com/microsoft/TokenEconomizer',result['description'])
        self.assertNotIn('TokenEco...',result['description'])
        self.assertTrue(result['description_complete'])

    def test_displayed_description_without_matched_player_is_explicitly_partial(self):
        result=metadata.parse('video-id',self.html(player=False))
        self.assertFalse(result['description_complete'])
        self.assertIn('TokenEco...',result['description'])

    def test_empty_author_description_is_not_replaced_with_displayed_stale_text(self):
        result=metadata.parse('video-id',self.html(description=''))
        self.assertEqual(result['description'],'')
        self.assertTrue(result['description_complete'])

    def test_another_video_player_cannot_be_attributed_to_requested_video(self):
        with self.assertRaises(ValueError):
            metadata.parse('video-id',self.html(player_id='different-video'))


if __name__=='__main__':
    unittest.main()
