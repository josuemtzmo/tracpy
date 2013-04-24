import numpy as np
import sys
import os
import op
import tracmass
import netCDF4 as netCDF
from mpl_toolkits.basemap import Basemap
import pdb
from matplotlib import delaunay
from matplotlib.pyplot import *
import glob
from datetime import datetime, timedelta
from readfields import *
from setupROMSfiles import *
from readgrid import *
from mpl_toolkits.basemap import Basemap
import time


'''

To re-compile tracmass fortran code, type "make f2py", which will give 
a file tracmass.so, which is the module we import above. Then in ipython, "run run.py"
xend,yend,zend are particle locations at next step
some variables are not specifically because f2py is hiding them from me:
 imt, jmt, km, ntractot
Look at tracmass.step to see what it is doing and making optional at the end.
Do this by importing tracmass and then tracmass.step?

I am assuming here that the velocity field at two times are being input into tracmass
such that the output is the position for the drifters at the time corresponding to the
second velocity time. Each drifter may take some number of steps in between, but those
are not saved.

     hs 			Two time steps of ssh [imt,jmt,2] (m)
'''
tic = time.time()
# Units for time conversion with netCDF.num2date and .date2num
units = 'seconds since 1970-01-01'

if 'rainier' in os.uname():
	loc = '/Users/kthyng/Documents/research/postdoc/' # for model outputs
elif 'hafen.tamu.edu' in os.uname():
	loc = '/home/kthyng/shelf/' # for model outputs

# Initialize parameters
nsteps = 10 # Number of steps to do between model outputs (iter in tracmass)
ndays = 1 # number of days to track the particles
ff = -1 # 1 forward, -1 backward
# Start date
date = datetime(2009,11, 30, 0)
# Convert date to number
date = netCDF.date2num(date,units)
# Time between outputs
Dt = 14400. # in seconds (4 hours), nc.variables['dt'][:] 
# Number of model outputs to use
tout = np.int((ndays*(24*3600))/Dt)
tseas = 4*3600 # 4 hours between outputs, in seconds, time between model outputs 
ah = 100. # horizontal diffusion in m^2/s. See project values of 350, 100, 0, 2000. For -turb,-diffusion
av = 1.e-5 # m^2/s, or try 5e-6

# THINK I NEED THIS STARTED HERE AND THEN UPDATED IN STEP
# tt = ints*tseas

# Figure out what files will be used for this tracking
nc,tinds = setupROMSfiles(loc,date,ff,tout)

# Read in grid parameters into dictionary, grid
grid = readgrid(loc,nc)



# Need to input x,y as relative to their grid box. Let's assume they are at 
# some position relative to a grid node
# xstart0 = np.array([[525.2]])#525.2]])
# ystart0 = np.array([[40.3]])
# Read in starting locations from HAB experiment to test
d = np.load(loc + 'hab/data/exp1b/starting_locations.npz')
# pdb.set_trace()
x0,y0 = grid['basemap'](d['lon0'],d['lat0'])
# Interpolate to get starting positions in grid space
fX = grid['tric'].nn_interpolator(grid['X'].flatten())
fY = grid['tric'].nn_interpolator(grid['Y'].flatten())
xstart0 = fX(x0,y0)
ystart0 = fY(x0,y0)
zstart0 = np.ones(xstart0.shape)*grid['km'] # The surface in tracmass is at k=KM
# Initialize seed locations # make these, e.g., ia=ceil(xstart0) (this was realized in cross.f95)
# # want ceil(xstart0) for drifter positions within the cell, but if xstart0 is on a grid cell border,
# # want ceil(xstart0+1)
# ia = np.ceil(xstart0)+(1-(np.ceil(xstart0)-np.floor(xstart0)))
# ja = np.ceil(ystart0)+(1-(np.ceil(ystart0)-np.floor(ystart0)))
# ka = np.ceil(zstart0)+(1-(np.ceil(zstart0)-np.floor(zstart0)))
ia = np.ceil(xstart0) #[253]#,525]
ja = np.ceil(ystart0) #[57]#,40]
ka = np.ceil(zstart0) #[1]#,1]

# pdb.set_trace()
dates = nc.variables['ocean_time'][:]	
t0save = dates[0] # time at start of file in seconds since 1970-01-01, add this on at the end since it is big

# Initialize drifter grid positions and indices
xend = np.ones(((len(tinds))*nsteps,ia.size))*np.nan
yend = np.ones(((len(tinds))*nsteps,ia.size))*np.nan
zend = np.ones(((len(tinds))*nsteps,ia.size))*np.nan
iend = np.ones(((len(tinds))*nsteps,ia.size))*np.nan
jend = np.ones(((len(tinds))*nsteps,ia.size))*np.nan
kend = np.ones(((len(tinds))*nsteps,ia.size))*np.nan
ttend = np.ones(((len(tinds))*nsteps,ia.size))*np.nan
# t0 = np.zeros(((len(tinds))*nsteps+1))
t0=0
t = np.zeros(((len(tinds))*nsteps+1))
flag = np.zeros((ia.size),dtype=np.int) # initialize all exit flags for in the domain

# Initialize free surface and fluxes
hs = np.ones((grid['imt'],grid['jmt'],2))*np.nan # free surface, 2 times
uflux = np.ones((grid['imt']-1,grid['jmt'],grid['km'],2))*np.nan # uflux, 2 times
vflux = np.ones((grid['imt'],grid['jmt']-1,grid['km'],2))*np.nan # vflux, 2 times
dzt = np.ones((grid['imt'],grid['jmt'],grid['km'],2))*np.nan # 2 times
# Read initial field in - to 2nd time spot since will be moved
# at the beginning of the time loop ahead
hs[:,:,1],uflux[:,:,:,1],vflux[:,:,:,1],dzt[:,:,:,1] = readfields(tinds[0],grid,nc)

j = 0 # index for number of saved steps for drifters
# Loop through model outputs. tinds is in proper order for moving forward
# or backward in time, I think.
for tind in tinds:
	# pdb.set_trace()
	# Move previous new time step to old time step info
	hs[:,:,0] = hs[:,:,1]
	uflux[:,:,:,0] = uflux[:,:,:,1]
	vflux[:,:,:,0] = vflux[:,:,:,1]
	dzt[:,:,:,0] = dzt[:,:,:,1]

	# Read stuff in for next time loop
	hs[:,:,1],uflux[:,:,:,1],vflux[:,:,:,1],dzt[:,:,:,1] = readfields(tind+1,grid,nc)
	# pdb.set_trace()

	print j
	#  flux fields at starting time for this step
	if j != 0:
		xstart = xend[j*nsteps-1,:]
		ystart = yend[j*nsteps-1,:]
		zstart = zend[j*nsteps-1,:]
		ia = iend[j*nsteps-1,:]
		ja = jend[j*nsteps-1,:]
		ka = kend[j*nsteps-1,:]
		# mask out drifters that have exited the domain
		xstart = np.ma.masked_where(flag[:]==1,xstart)
		ystart = np.ma.masked_where(flag[:]==1,ystart)
		zstart = np.ma.masked_where(flag[:]==1,zstart)
		ia = np.ma.masked_where(flag[:]==1,ia)
		ja = np.ma.masked_where(flag[:]==1,ja)
		ka = np.ma.masked_where(flag[:]==1,ka)
		ind = (flag[:] == 0) # indices where the drifters are still inside the domain
	else: # first loop, j==0
		xstart = xstart0
		ystart = ystart0
		zstart = zstart0
		# TODO: Do a check to make sure all drifter starting locations are within domain
		ind = (flag[:] == 0) # indices where the drifters are inside the domain to start
		# t0[0] = tseas/nsteps # want to start time at the first moved step, will add on initial zero at the end

	# Find drifter locations
	# pdb.set_trace()
	# only send unmasked values to step
	if not np.ma.compressed(xstart).any(): # exit if all of the drifters have exited the domain
		break
	else:
		xend[j*nsteps:j*nsteps+nsteps,ind],yend[j*nsteps:j*nsteps+nsteps,ind],zend[j*nsteps:j*nsteps+nsteps,ind], \
						iend[j*nsteps:j*nsteps+nsteps,ind],jend[j*nsteps:j*nsteps+nsteps,ind],kend[j*nsteps:j*nsteps+nsteps,ind],flag[ind],ttend[j*nsteps:j*nsteps+nsteps,ind] = \
						tracmass.step(np.ma.compressed(xstart),np.ma.compressed(ystart),
						np.ma.compressed(zstart),t0,np.ma.compressed(ia),np.ma.compressed(ja),
						np.ma.compressed(ka),tseas,uflux,vflux,ff,grid['kmt'].astype(int),
						dzt,hs,grid['dxdy'],grid['dxv'],grid['dyu'],grid['h'],nsteps,ah,av)#dz.data,dxdy)
		# if np.sum(flag)>0:
		# pdb.set_trace()
		# CHECK THIS, want time for each time step between model outputs
		# TIMES ARE WRONG
		t[j*nsteps+1:j*nsteps+nsteps+1] = t[j*nsteps] + np.linspace(tseas/nsteps,tseas,nsteps)    #tseas/float(nsteps) # update time in seconds to match drifters
		# if i == 8:
		# 	pdb.set_trace()
	j = j + 1

nc.close()
# grid.close()

# # Add on time for first time step
# t0=np.concatenate((0,t0),axis=0)

t = t + t0save # add back in base time in seconds

# Add on to front location for first time step
xg=np.concatenate((xstart0.reshape(1,xstart0.size),xend),axis=0)
yg=np.concatenate((ystart0.reshape(1,ystart0.size),yend),axis=0)
zg=np.concatenate((zstart0.reshape(1,zstart0.size),zend),axis=0)

# Recreate Cartesian particle locations from their index-relative locations
# just by interpolating. These are in tracmass ordering
fxr = grid['tri'].nn_interpolator(grid['xr'].flatten())
fyr = grid['tri'].nn_interpolator(grid['yr'].flatten())
xp = fxr(xg,yg)
yp = fyr(xg,yg)

# Plot tracks
figure()
grid['basemap'].drawcoastlines()
grid['basemap'].fillcontinents('0.8')
grid['basemap'].drawparallels(np.arange(18, 35), dashes=(1, 0), linewidth=0.15, labels=[1, 0, 0, 0])
grid['basemap'].drawmeridians(np.arange(-100, -80), dashes=(1, 0), linewidth=0.15, labels=[0, 0, 0, 1])
hold('on')
contour(grid['xr'], grid['yr'], grid['h'], np.hstack(([10,20],np.arange(50,500,50))), colors='lightgrey', linewidths=0.15)
plot(xp,yp,'g.')
# Outline numerical domain
plot(grid['xr'][0,:],grid['yr'][0,:],'k:')
#ax1.plot(grid['xr'][-1,:],grid['yr'][-1,:],'k:')
plot(grid['xr'][:,0],grid['yr'][:,0],'k:')
plot(grid['xr'][:,-1],grid['yr'][:,-1],'k:')
show()
toc = time.time()
print "run time:",toc-tic
# if __name__=='__main__':
# 	run()
