from __future__ import absolute_import
from unittest import TestCase
import numpy as np
import amisurvey.pbcor as pbcor

class TestRadiusMap(TestCase):
    def test_radius_from_origin(self):
        shape = (3,3)
        centre = (0,0)
        map = pbcor._pixel_radius_map(shape,centre)
        self.assertEqual(map[0][0],0)
        self.assertEqual(map[0][1],1)
        self.assertEqual(map[1][1],np.sqrt(2))
        self.assertEqual(map[2][2],np.sqrt(8))
        # print
        # print map
    def test_radius_from_centre_odd_dims(self):
        shape = (5,5)
        centre = pbcor._central_position(shape)
        map = pbcor._pixel_radius_map(shape,centre)
        self.assertEqual(map[(2,2)], 0.)

    def test_radius_from_centre_even_dims(self):
        shape = (6,6)
        centre = pbcor._central_position(shape)
        map = pbcor._pixel_radius_map(shape,centre)
        self.assertEqual(map[(2,2)], np.sqrt(0.5))

class TestCorrectionMap(TestCase):
    def test_gaussian(self):
        # shape = (13,13)
        # centre = (6,6)
        shape = (3,3)
        centre = (1,1)
        curve = pbcor.GaussianCurve(sigma=1.)
        map = pbcor._correction_map(curve.correction,
                                    shape,centre)

        self.assertEqual(map[centre], 1.0)
        self.assertEqual(map[0][centre[1]], curve.correction(1))

class TestMask(TestCase):
    def test_gaussian(self):
        shape = (13,13)
        centre = (6,6)

        mask = pbcor.make_mask(shape,centre,radius_pix=1)
        print "MASK:"
        print mask
