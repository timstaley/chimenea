"""Subroutines used in the reduction of AMI survey data"""

from utils import load_casa_imagedata
import sigmaclip

default_ami_clean_args = {   "spw": '0:0~5',
          "imsize": [512, 512],
          "cell": ['5.0arcsec'],
          "pbcor": False,
#           "weighting": 'natural',
             "weighting": 'briggs',
             "robust": 0.5,
#          "weighting":'uniform',
          "psfmode": 'clark',
          "imagermode": 'csclean',
          }

