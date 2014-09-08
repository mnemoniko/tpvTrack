
import netCDF4
import matplotlib.pyplot as plt

import my_settings
import preProcess
import llMesh
import segment
import correspond
import tracks

def demo():
  #setup -----------------
  info = my_settings.info
  filesData = my_settings.filesData
  fMesh = filesData[0]  
  fMetr = my_settings.fDirSave+'fields_debug.nc'
  fSeg = my_settings.fDirSave+'seg_debug.nc'
  fCorr = my_settings.fDirSave+'correspond_debug.txt'
  fTrack = my_settings.fDirSave+'tracks_debug.txt'
  
  rEarth = my_settings.rEarth
  dRegion = my_settings.dFilter
  latThresh = my_settings.latThresh
  
  #pre-process ------------------------
  #mesh = preProcess.demo_eraI(fMesh, filesData, fMetr, my_settings.rEarth, dRegion, latThresh, info=info)
  mesh = preProcess.demo_eraI(fMesh, [], fMetr, my_settings.rEarth, dRegion, latThresh) #if already processed input data
  
  if (False):
    print mesh.lat; print mesh.nLat
    print mesh.lon; print mesh.nLon
  
  #segment --------------------------
  cell0 = llMesh.Cell(mesh,0)
  print 'index: ', cell0.ind, 'nbrs: ', cell0.get_nbrInds()
  
  dataMetr = netCDF4.Dataset(fMetr,'r')
  #segment.run_segment(fSeg, info, dataMetr, cell0, mesh)
  #segment.run_plotBasins(my_settings.fDirSave, dataMetr, fSeg, mesh)
  dataMetr.close()
  
  #spatial metrics ------------------------
  
  #time correspondence -----------------
  dataMetr = netCDF4.Dataset(fMetr,'r')
  dataSeg = netCDF4.Dataset(fSeg,'r')
  #correspond.run_correspond(fCorr, dataMetr, dataSeg, mesh, my_settings.deltaT, my_settings.trackMinMaxBoth, .2, 0, 19)
  #correspond.plot_correspondences(my_settings.fDirSave, fCorr, 19, mesh)
  dataMetr.close()
  dataSeg.close()
  
  #time tracks -------------------------
  #tracks.run_tracks(fTrack, fCorr, 6, 19-1)
  for iTime in xrange(19-1, -1, -1):
    tracks.run_tracks(fTrack, fCorr, iTime, 19-1)
  
  #time metrics ----------------------

if __name__=='__main__':
  demo()