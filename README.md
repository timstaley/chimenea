#chimenea#

Chimenea implements a simple but effective algorithm for automated imaging
of multi-epoch radio-synthesis data, developed as part of the 
[ALARRM programme](http://4pisky.org/projects/#ALARRM).

The chimenea pipeline is built upon NRAO [CASA](http://casa.nrao.edu) 
subroutines, interacting with the CASA environment via the 
[drive-casa](https://github.com/timstaley/drive-casa)
interface layer.

While chimenea has only been tested with data from AMI-LA to date, 
the algorithm is implemented in a telescope-agnostic fashion and could trivially
be adapted to other telescopes. You may want to take a look at the 
[amisurvey](https://github.com/timstaley/amisurvey) 
package to see how it has been integrated into our project-specific data-flow.

The key logic-flow is implemented in the 
[pipeline.py](chimenea/pipeline.py) module. 
An accompanying publication with a full description is in prep.

If you make use of chimenea in work leading to a publication, we ask that you
cite the relevant ASCL entry and accompanying paper (forthcoming).