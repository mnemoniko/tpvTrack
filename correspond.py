import numpy as np
import netCDF4
from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt
import cPickle as pickle; pickleProtocol = 2

import basinMetrics

def advect_LatLon(u, v, latIn, lonIn, dt, r ):
  #return new lat/lon coordinates based on:
  #u,v in m/s, lat/lon in radians, dt in s, rSphere in m
  
  #u = r cos(lat) dLon/dt, v = r dLat/dt
  #constrain latitudes to be in [-pi/2, pi/2] and longitudes in [0, 2pi)
  
  dLon_dt = u/(r*np.cos(latIn)) #if lat=+- pi/2, this will be big
  dLat_dt = v/r
  
  lat = latIn+ dLat_dt*dt; lon = lonIn+ dLon_dt*dt
  #want to bound lat/lon. Note that for silly big meridional velocities, the following
  #can adjust to outside of poles, but then the whole tracking idea is screwed anyway.
  
  #bound lat. 
  #imagine crossing north pole so 89->93 is really 89->87N and 180degree switch in longitude
  crossedN = lat>np.pi/2
  lat[crossedN] = np.pi-lat[crossedN]; #pi/2 - (lat-pi/2)
  lon[crossedN] += np.pi #other half of hemisphere
  crossedS = lat<-np.pi/2
  lat[crossedS] = -np.pi-lat[crossedS]; #-pi/2 - (lat-(-pi/2))
  lon[crossedS] += np.pi #other half of hemisphere
  #bound lon
  lon = lon%(2.*np.pi) #[0,2pi)
  
  return (lat, lon)

def advect_feature(siteInd, cell2Site, mesh, u, v, dt):
  #return advected lat, lon points of feature cells
  
  nCells = len(cell2Site)
  inFeature = cell2Site==siteInd
  cellInds = np.arange(nCells)[inFeature]
  
  latFeature, lonFeature = mesh.get_latLon_inds(cellInds)
  uFeature = u[cellInds]; vFeature = v[cellInds]
  
  newLat, newLon = advect_LatLon(uFeature, vFeature, latFeature, lonFeature, dt, mesh.r )
  
  if (False):
    #plot the original points and the advected
    print latFeature; print lonFeature;
    print newLat; print newLon
    
    m = Basemap(projection='ortho',lon_0=0,lat_0=89.5, resolution='l')
    r2d = 180./np.pi
    plt.figure()
    m.drawcoastlines()
    x0,y0 = m(lonFeature*r2d, latFeature*r2d)
    x1,y1 = m(newLon*r2d, newLat*r2d)
    m.scatter(x0,y0,color='b')
    m.scatter(x1,y1,color='r')
    plt.show()
  
  return (newLat, newLon)

def advect_basin(siteInd, cell2Site, mesh, u, v, dt):
  #return cells inds of cells that basin advects to next time (+ or - dt)
  
  #coordinates of advected cell centers. 
  #so, we're assuming that mesh is dense enough wrt feature size that cell centers are sufficient?
  #or, overlap is sufficient that this will id it
  latPts, lonPts = advect_feature(siteInd, cell2Site, mesh, u, v, dt)
  
  #cells corresponding to those coordinates
  nPts = len(latPts);
  advCells = np.empty(nPts, dtype=int)
  guessCell = siteInd #used for mpas and wrf meshes
  inDomain = [] #used for LAM meshes
  if ('wrf' in mesh.info):
    inDomain = np.ones(nPts,dtype=int)
    
  for iPt in xrange(nPts):
    if (mesh.info == 'mpas'):
      advCells[iPt] = mesh.get_closestCell2Pt(latPts[iPt], lonPts[iPt], guessCell=guessCell)
      guessCell = advCells[iPt]
    elif ('wrf' in mesh.info):
      advCells[iPt] = mesh.get_closestCell2Pt(latPts[iPt], lonPts[iPt], guessCell=guessCell)
      guessCell = advCells[iPt]
      inDomain[iPt] = mesh.isPointInDomain(latPts[iPt], lonPts[iPt], advCells[iPt])
    else:
      advCells[iPt] = mesh.get_closestCell2Pt(latPts[iPt], lonPts[iPt])
  
  if ('wrf' in mesh.info):
    #we'll just ignore points that advect outside the domain
    #print "Number of points advected outside of domain: ", np.sum(inDomain==0)
    advCells = advCells[inDomain>0]
  
  if (False):
    latCell, lonCell = mesh.get_latLon_inds(advCells)
    print latPts; print lonPts
    print latCell; print lonCell
    print advCells
    m = Basemap(projection='ortho',lon_0=0,lat_0=89.5, resolution='l')
    r2d = 180./np.pi
    plt.figure()
    m.drawcoastlines()
    x0,y0 = m(lonPts*r2d, latPts*r2d)
    x1,y1 = m(lonCell*r2d, latCell*r2d)
    m.scatter(x0,y0,color='b')
    m.scatter(x1,y1,color='r')
    plt.show()
  
  #multiple cells can advect into the same cell
  basinCells = np.unique(advCells) #apparently there's a sorting bug fixed in numpy 1.6.2...
  #basinCells = np.array( list(set(advCells)), dtype=int )
  
  return basinCells

def getCommon_1dInd(inds0, inds1):
  #return common values between lists with unique values
  return np.intersect1d(inds0, inds1, assume_unique=True)
  
def calc_fracOverlap_advection(sites0, cell2Site0, u0, v0, dt,
                               sites1, cell2Site1, u1, v1, mesh):
  #Given fields+basins at t0 and t0+dt,
  #-create candidate matches by overlapping advection
  #in principle, overlap could mean: 
  #-# of common cells, min threshold for common area, min threshold for convex hulls overlapping area,...
  #return matrix with fraction of overlap by area(nCellsMatch)/area(nCellsPossible)
  
  nSites0 = len(sites0); nSites1 = len(sites1)
  fracOverlap = np.zeros((nSites0, nSites1), dtype=float)
  
  #store advection of t1 sites -dt/2
  sites2Cells_t1 = [None]*nSites1
  areaBasin1 = np.empty(nSites1,dtype=float)
  for iSite1 in xrange(nSites1):
    siteInd = sites1[iSite1]
    #advect basin -dt/2
    sites2Cells_t1[iSite1] = advect_basin(siteInd, cell2Site1, mesh, u1, v1, -.5*dt)
    areaBasin1[iSite1] = np.sum( mesh.get_area_inds(sites2Cells_t1[iSite1]) )
  #print areaBasin1
    
  #see which t0 sites advected dt/2 overlap with future sites advected back
  for iSite0 in xrange(nSites0):
    siteInd = sites0[iSite0]
    #advect basin +dt/2
    site2Cells_t0 = advect_basin(siteInd, cell2Site0, mesh, u0, v0, .5*dt)
    areaBasin0 = np.sum( mesh.get_area_inds(site2Cells_t0) )
    #print areaBasin0
    
    for iSite1 in xrange(nSites1):
      #for frac overlap, there's a choice for what cells to use.
      #consider candidate big t0 and small t1.
      #-for min(cellsInBasin), fraction will be high w/ few cells from big needed
      #-for max(cellsInBasin), fraction will be low even if lots of small covered
      commonCells = getCommon_1dInd(site2Cells_t0, sites2Cells_t1[iSite1])
      areaCommon = np.sum( mesh.get_area_inds(commonCells) )
      
      #Note that areas can be zero for LAM where point advects out of domain.
      potentialArea = min(areaBasin0, areaBasin1[iSite1])
      #Avoid divide by 0
      frac = 0
      if (potentialArea>0):
        frac = areaCommon/potentialArea
      fracOverlap[iSite0, iSite1] = frac
  
  if (True):
    #print out some quick diagnostics
    print "Fractional area of overlapping advection\n", fracOverlap
  
  return fracOverlap

def check_overlap_PT(isMatch, sites0, sites1, cell2Site0, cell2Site1, theta0, theta1):
  #If the "air mass" persists, the PT range should overlap between corresponding TPVs.
  #If not, do not correspond.
  
  #calculate bounds for each tpv that potentially matches another
  nSites0 = len(sites0); nSites1 = len(sites1)
  min0 = np.empty(nSites0, dtype=float); max0 = np.empty(nSites0, dtype=float);
  min1 = np.empty(nSites1, dtype=float); max1 = np.empty(nSites1, dtype=float);
  sitesCheck0, sitesCheck1 = np.nonzero(isMatch)
  for ind in np.unique(sitesCheck0):
    site = sites0[ind]
    minVal, maxVal = basinMetrics.get_minMax_cell2Site(site, cell2Site0, theta0)
    min0[ind] = minVal; max0[ind] = maxVal;
  for ind in np.unique(sitesCheck1):
    site = sites1[ind]
    minVal, maxVal = basinMetrics.get_minMax_cell2Site(site, cell2Site1, theta1)
    min1[ind] = minVal; max1[ind] = maxVal;
    
  #check to see if those bounds overlap
  for iCheck in xrange(len(sitesCheck0)):
    ind0 = sitesCheck0[iCheck]; ind1 = sitesCheck1[iCheck];
    #essentially the intersection of 2 ordered line segments
    rangeTop = min(max0[ind0],max1[ind1])
    rangeBottom = max(min0[ind0],min1[ind1])
    if (rangeTop<rangeBottom): #no overlap
      isMatch[ind0,ind1] = 0
  
  return isMatch

def get_correspondMetrics(dataMetrics, sitesOut, iTime):
  #It's slow to load 1 value at a time from file.
  #So, we can get (load,calculate?) values for all sites at a given time.
  
  #"extremum" metrics may not be too robust:
  #-thetaExtr: value jumps if, say, TPV goes to surface
  #-latExtr: seems okay, right?
  
  #area of non-overlap of advected tpvs would be useful if the "outer" filaments/chunks didn't break off and join willy-nilly
  #(see http://docs.scipy.org/doc/numpy/reference/routines.set.html)
  diffKeys = ['thetaExtr', 'latExtr']; nKeys = len(diffKeys)
  refDiffs = [1.0, 2.0]
  
  nSites = dataMetrics.variables['nSites'][iTime]
  allSites = dataMetrics.variables['sites'][iTime,:]; allSites = allSites[0:nSites]
  #isSiteReq = np.array([i in sitesOut for i in allSites], dtype=bool)
  isSiteReq = np.in1d(allSites, sitesOut, assume_unique=True)
  
  nSitesOut = len(sitesOut)
  valsOut = np.empty((nKeys,nSitesOut),dtype=float)
  for iKey in xrange(nKeys):
    key = diffKeys[iKey]
    vals = dataMetrics.variables[key][iTime,:]
    vals = vals[0:nSites]
    
    valsOut[iKey,:] = vals[isSiteReq]
    
  return (valsOut, refDiffs)
  
def calc_basinSimilarity(vals0, vals1, refDiffs):
  #Input vals[variable,sites]
  
  nKeys, nSites1 = vals1.shape
  d = np.zeros(nSites1,dtype=float)
  for iKey in xrange(nKeys):
    diffs = np.absolute( vals1[iKey,:]-vals0[iKey] )
    d += diffs/refDiffs[iKey]
  
  return d
  
def correspond(sites0, cell2Site0, u0, v0, dt, 
               sites1, cell2Site1, u1, v1, mesh,
               trackMinMaxBoth, fracOverlapThresh,
               iTime0, dataMetrics, theta0, theta1):
  
  #additional filters ---------------------
  #(1) feature properties a la cost function:
  #reasonable changes over "short" time in 
  #-thetaMin, circulation, feature velocity, location,...
  #(2) event consistency:
  #propagate, split, merge, genesis, lysis should have characteristics
  #-propagate: similar intensity and area
  #-split: similar sumArea
  #-merge:
  
  #these really end up needing to include matches not found in fracOverlap
  #when consider cases like small TPVs breaking off of a large one
  
  #decide whether sites correspond --------------------------
  #area overlap
  fracOverlap = calc_fracOverlap_advection(sites0, cell2Site0, u0, v0, dt, sites1, cell2Site1, u1, v1, mesh)
  isMatch = fracOverlap>fracOverlapThresh
  print "Number of matches after horizontal overlap: {0}".format(np.sum(isMatch))
  
  #potential temperature overlap
  if (False):
    isMatch = check_overlap_PT(isMatch, sites0, sites1, cell2Site0, cell2Site1, theta0, theta1)
    print "Number of matches after vertical overlap: {0}".format(np.sum(isMatch))
  
  #decide type of site correspondence (major vs. minor) ------------------
  #0-noMatch, 1-minor, 2-major
  nSites0 = len(sites0); nSites1 = len(sites1);
  
  metrics0, refDiffs = get_correspondMetrics(dataMetrics, sites0, iTime0); #print metrics0
  metrics1, refDiffs = get_correspondMetrics(dataMetrics, sites1, iTime0+1); #print metrics1
  
  #major time0->time1
  typeMatch01 = isMatch.copy().astype(int)
  for iSite0 in xrange(nSites0):
    site0 = sites0[iSite0]
    corrSites = sites1[isMatch[iSite0,:]>0]
    
    if (len(corrSites)<1):
      continue
    if (len(corrSites)==1):
      site1 = corrSites[0]
      typeMatch01[iSite0,sites1==site1] = 2
    else:
      vals0 = metrics0[:,iSite0]
      vals1 = metrics1[:,isMatch[iSite0,:]>0]
      d = calc_basinSimilarity(vals0, vals1, refDiffs); #print d
      
      minInd = np.argmin(d)
      similarSite = corrSites[minInd]
      typeMatch01[iSite0,sites1==similarSite] = 2
  
  #major time1<-time0 
  typeMatch10 = isMatch.copy().astype(int)
  for iSite1 in xrange(nSites1):
    site1 = sites1[iSite1]
    corrSites = sites0[isMatch[:,iSite1]>0]
    
    if (len(corrSites)<1):
      continue
    if (len(corrSites)==1):
      site0 = corrSites[0]
      typeMatch10[sites0==site0,iSite1] = 2
    else:
      vals0 = metrics1[:,iSite1]
      vals1 = metrics0[:,isMatch[:,iSite1]>0]
      d = calc_basinSimilarity(vals0, vals1, refDiffs);
      
      minInd = np.argmin(d)
      similarSite = corrSites[minInd]
      typeMatch10[sites0==similarSite,iSite1] = 2
  
  typeMatch = np.minimum(typeMatch01, typeMatch10) #e.g., site0.a-site1 not major if site0.a splits from site0 into site1 but site0.b more similar to site1
  print "Number of {0}s in 0->1 and 1<-0: {1}, {2}".format(2, np.sum(typeMatch01==2), np.sum(typeMatch10==2))
  print "Number of -major- correspondences: {0}".format(np.sum(typeMatch==2))
  return typeMatch

def run_correspond(fNameOut, dataMetr, dataSeg, mesh, dt, 
                   trackMinMaxBoth, fracOverlapThresh, iTimeStart, iTimeEnd, dataMetrics):
  
  #file for correspondences
  fCorr = open(fNameOut,'wb')
  
  for iTime in xrange(iTimeStart,iTimeEnd): #iTimeEnd will be the end of the correspondences
    #segmentation data
    cell2Site0 = dataSeg.variables['cell2Site'][iTime,:]
    sitesMin0 = dataSeg.variables['sitesMin'][iTime,:];
    nMin0 = dataSeg.variables['nSitesMin'][iTime]; sitesMin0 = sitesMin0[0:nMin0]
    sitesMax0 = dataSeg.variables['sitesMax'][iTime,:]; 
    nMax0 = dataSeg.variables['nSitesMax'][iTime]; sitesMax0 = sitesMax0[0:nMax0]
    
    cell2Site1 = dataSeg.variables['cell2Site'][iTime+1,:]
    sitesMin1 = dataSeg.variables['sitesMin'][iTime+1,:];
    nMin1 = dataSeg.variables['nSitesMin'][iTime+1]; sitesMin1 = sitesMin1[0:nMin1]
    sitesMax1 = dataSeg.variables['sitesMax'][iTime+1,:]; 
    nMax1 = dataSeg.variables['nSitesMax'][iTime+1]; sitesMax1 = sitesMax1[0:nMax1]
    
    #metr data
    u0 = dataMetr.variables['u'][iTime,:]; v0 = dataMetr.variables['v'][iTime,:]
    theta0 = dataMetr.variables['theta'][iTime,:]
    u1 = dataMetr.variables['u'][iTime+1,:]; v1 = dataMetr.variables['v'][iTime+1,:]
    theta1 = dataMetr.variables['theta'][iTime+1,:]
    
    #which basins we want to track ----------------------------
    sites0 = []; sites1 = []
    if (trackMinMaxBoth == 0): #just minima
      sites0 = sitesMin0
      sites1 = sitesMin1
    elif (trackMinMaxBoth == 1): #just maxima
      sites0 = sitesMax0
      sites1 = sitesMax1
    else: #track min+max
      print "Do you really want minima to be able to correspond to maxima?"
      sites0 = np.concatenate((sitesMin0,sitesMax0))
      sites1 = np.concatenate((sitesMin1,sitesMax1))
      
    #time correspondence ------------------
    typeMatch = correspond(sites0, cell2Site0, u0, v0, dt,
                         sites1, cell2Site1, u1, v1, mesh,
                         trackMinMaxBoth, fracOverlapThresh,
                         iTime, dataMetrics, theta0, theta1)
                         
    write_corr_iTime(fCorr, iTime, sites0, sites1, typeMatch)
  
  fCorr.close()
  
def write_corr_iTime(f, iTime, sites0, sites1, typeMatch):
  '''
  format is:
  Time0 object
  Time1 object
  ...
  
  where each Timei object is
  {iTime, sites0, correspondingSites1[iSite0][iCorrespondingSites1], correspondenceType[iSite0][iCorrespondingSites1]}
  
  according to http://stackoverflow.com/questions/12761991/how-to-use-append-with-pickle-in-python ,
  pickle can work like:
  >>> f=open('a.p', 'wb')
  >>> pickle.dump({1:2}, f)
  >>> pickle.dump({3:4}, f)
  >>> f.close()
  >>> 
  >>> f=open('a.p', 'rb')
  >>> pickle.load(f)
  {1: 2}
  >>> pickle.load(f)
  {3: 4}
  >>> pickle.load(f)
  Traceback (most recent call last):
    File "<stdin>", line 1, in <module>
  EOFError
  '''
  
  nSites0 = len(sites0); nSites1 = len(sites1)
  
  obj = {'iTime':iTime, 'sites0':sites0}
  allCorrSites = []
  allCorrTypes = []
  
  for iSite0 in xrange(nSites0):
    corr1 = typeMatch[iSite0,:]
    corrSites = sites1[corr1>0]; nCorr = len(corrSites)
    typeCorr = corr1[corr1>0]
    
    allCorrSites.append(corrSites)
    allCorrTypes.append(typeCorr)
  
  obj['corrSites'] = allCorrSites
  obj['corrTypes'] = allCorrTypes
  
  pickle.dump(obj,f,protocol=pickleProtocol)
    
def plot_correspondences(fDirSave, fCorr, nTimes, mesh):
  
  m = Basemap(projection='ortho',lon_0=0,lat_0=89.5, resolution='l')
  r2d = 180./np.pi
  
  for iTime in xrange(nTimes):
    plt.figure()
    m.drawcoastlines()
    
    allSites0, corrSites, typesCorr = read_corr_iTime(fCorr, iTime)
    nSites0 = len(allSites0)
    for iSite in xrange(nSites0):
      site0 = allSites0[iSite]
      sites1 = corrSites[iSite]; nSites1 = len(sites1)
      minorMajor = typesCorr[iSite]
      if (nSites1<1):
        continue
      
      lat0, lon0 = mesh.get_latLon_inds(site0)
      lat1, lon1 = mesh.get_latLon_inds(np.array(sites1,dtype=int))
      lat0 = lat0*r2d; lon0 = lon0*r2d;
      lat1 = lat1*r2d; lon1 = lon1*r2d
      
      x0,y0 = m(lon0,lat0)
      m.scatter(x0,y0, marker='+', color='g', s=55)
      for iSite1 in xrange(nSites1):
        c = 'r'; lw=.5
        if (minorMajor[iSite1]>1):
          c='b'; lw=2
        m.drawgreatcircle(lon0, lat0, lon1[iSite1], lat1[iSite1], del_s=50.0, color=c, lw=lw)
        x1,y1 = m(lon1[iSite1], lat1[iSite1])
        m.scatter(x1,y1, marker='o', color='r', s=20)
    
    if (False):
      plt.show()
    else:
      fName = 'corr_debug_{0}.png'.format(iTime)
      fSave = fDirSave+fName
      print "Saving file to: "+fSave
      plt.savefig(fSave); plt.close()
      
def read_corr_iTime(fName, iTimeIn):
  #read/return correspondences for the specified time index
  
  f = open(fName, 'rb')
  
  for iTime in xrange(iTimeIn): #will go [0,iTimeIn)
    #get to serialized timestep in sequentially pickled objects
    pickle.load(f)
    
  #now at the proper time (assuming time is in file)
  obj = pickle.load(f)
  f.close()
  
  iTime = obj['iTime']
  if (iTime != iTimeIn):
    print "Uhoh. Time mismatch in unpickling file ", iTime, iTimeIn
  sites0 = obj['sites0']
  corrSites = obj['corrSites']
  corrTypes = obj['corrTypes']
  
  return (sites0, corrSites, corrTypes)

def get_correspondingSites(fName, iTime, site):
  allSites0, corrSites, typeCorr = read_corr_iTime(fName, iTime)
  if (site not in allSites0):
    print "Uhoh, site doesn't correspond to another..."
    print site, allSites0
  iSite = np.where(allSites0==site)[0][0]
  return (corrSites[iSite], typeCorr[iSite])
