from __future__ import absolute_import
from unittest import TestCase
import json
from chimenea.obsinfo import ObsInfo



class TestObsInfoSerialization(TestCase):
    def setUp(self):
        self.obs = ObsInfo(name='foo',
                           group='fooish',
                           metadata={'bar':'baz'})
        assert isinstance(self.obs, ObsInfo)
        self.obs.uv_ms='uv_data.ms'
        self.obs.maps_dirty.ms.image='image.ms'


    def test_round_trip(self):
        rep = json.dumps(self.obs, cls=ObsInfo.Encoder)
        obs2 = json.loads(rep, cls=ObsInfo.Decoder)
        # print obs2
