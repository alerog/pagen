import sys
from math import pi, sqrt
from numpy import linspace, logspace, loadtxt, unique, log10
import subprocess
import FitPA
import h5py as h5

def GenIlkkaSquarerInput(D,tau,L,particles,nGrid,nSquare):
    N = len(particles)
    f = open('INPUT','w')
    f.write('LABEL\n')
    f.write('%i %i\n' % (N, 2*N)) # of species, # of particles
    for [type,lam,Z] in particles:
        f.write('2 %f %f 1 64 5 0\n' % (Z, 1./(2.*lam))) # of particles, charge (Z), mass, spin, Trotter #, multilevel L, 0 for bolzmannons and 1 for fermions (i.e. exchange)
    f.write('%i\n' % (2*N)) # of particles to be moved (top to bottom)
    f.write('100\n') # frequency of calculating observables
    f.write('%f 0\n' % (tau)) # tau, 0 or temperature, 1
    f.write('5000 100000\n') # of blocks, # of MC steps in a block
    f.write('Squaring %i %i 1\n' % (nGrid,nSquare)) # text, grid points, # of squaring steps
    f.write('Box %f %f %f\n' % (L,L,L)) # text, box dimensions in atomic units (Bohr radius)
    f.write('NumOfImages 0\n') # # of images
    f.write('DisplaceMove 0 0.0\n') # text, 0 if not used (1 if used), 0.1 would mean 10 percent of moves are displace moves
    f.write('Estimator 1\n') # 0=IK_type (atoms and if all quantum particles), 1=thermal estimator
    f.write('PairCorr 0.0 10.0 200\n') # grid_start, grid_end, # of grid points (if 0 then not calculated)
    f.write('LongRange 0 0.0\n')
    f.write('GetConf 0\n')
    f.write('LevelUpdate 1 0.40 0.55\n')
    f.close()

# Input parameters (label, lambda, Z)
particles = [['e',0.5,1.0],['p',0.5,-1.0]]
particles = [['e',0.5,1.0],['p',0.0002723089072243553,-1.0]]

## PIMC simulation
D = 3 # dimension
T = 0.025 # desired temperature of PIMC simulation
tau = 0.125 # desired timestep of PIMC simulation
M = int((1/T)/tau) # number of time slices
tau = (1/T)/M # used tau

## Squarer
bigL = 100.0 # length of box
bigNGrid = 300 # number of grid points
nSquare = 20 # total number of squarings to reach lowest temperature
nOrder = -1 # order of off-diagonal PA fit: -1 = no fit (direct spline), 0 = only diagonal, 1-3 = fit off-diagonal to 1-3 order
showPlots = 0 # show plots of fit to PA

# Create Ilkka Squarer input
print '**** Performing squaring ****'
GenIlkkaSquarerInput(D,tau,bigL,particles,bigNGrid,nSquare)
subprocess.call(['ilkkaSquarer'])

## Long-range breakup
L = 10.0 # length of box
r0 = 0.001 # first grid point
rCut = L/2. # r cutoff for ewald
nGrid = 300 # number of grid points
gridType = "LINEAR" # LOG/LINEAR
breakupType = 1 # 2 - Short-ranged only, 1 - Optimized breakup, 0 - Classical Ewald breakup
nKnots = 20 # number of knots in spline (probably fine)
nImages = 100 # Naive check

# Pair action objects (object type, max index in kspace)
# 2 - dU/dBeta, 1 - U, 0 - V
paObjects = [[2,10]]


print '**** Performing breakup ****\n'
paIndex = 0
for i in xrange(0, len(particles)):
    for j in xrange(i, len(particles)):
        paIndex += 1
        [type1, lam1, Z1] = particles[i]
        [type2, lam2, Z2] = particles[j]
        print '****************************************'
        print '****', type1, ', lam1 =', lam1, ', Z1 =', Z1
        print '****', type2, ', lam2 =', lam2, ', Z2 =', Z2

        # Write potential
        f = open('v.'+str(paIndex)+'.txt','w')
        if gridType=="LINEAR":
            gridIndex = 0
            rs = linspace(r0,bigL,num=bigNGrid,endpoint=True)
        elif gridType=="LOG":
            gridIndex = 1
            rs = logspace(log10(r0),log10(bigL),num=bigNGrid,endpoint=True)
        else:
            print 'Unrecognized grid'
        for r in rs:
            f.write('%.10E %.10E\n' % (r,Z1*Z2/r))
        f.close()

        # Perform breakup
        for [paObject,nMax] in paObjects:
            if paObject == 2:
                paPrefix = 'du'
            elif paObject == 1:
                paPrefix = 'u'
            elif paObject == 0:
                paPrefix = 'v'
            print '****\n', '****', paPrefix, '\n****'

            if breakupType != 2:
                subprocess.call(['ewald',str(L),str(nMax),str(r0),str(rCut),str(nGrid),str(gridIndex),str(Z1*Z2),str(breakupType),str(paObject),str(paIndex),str(nKnots),str(tau),str(nImages)])
            else:
                subprocess.call(['cp',paPrefix+'d.'+str(paIndex)+'.txt',paPrefix+'d.'+str(paIndex)+'.r.txt'])

            # Fit off-diagonal
            if paObject != 0:
                FitPA.main(['',nOrder,paPrefix+'s.'+str(paIndex)+'.txt',showPlots])
            elif breakupType != 2:
                subprocess.call(['cp',paPrefix+'.'+str(paIndex)+'.r.txt',paPrefix+'d.'+str(paIndex)+'.r.txt'])
                subprocess.call(['cp',paPrefix+'.'+str(paIndex)+'.k.txt',paPrefix+'d.'+str(paIndex)+'.k.txt'])


        # Write to h5 file
        f = h5.File(type1+'-'+type2+'.h5','w')
        info = f.create_group('Info')
        info.attrs.create('type1',type1)
        info.attrs.create('type2',type2)
        info.attrs.create('lam1',lam1)
        info.attrs.create('lam2',lam2)
        info.attrs.create('Z1',Z1)
        info.attrs.create('Z2',Z2)
        for [paObject,nMax] in paObjects:
            if paObject == 2:
                paPrefix = 'du'
            elif paObject == 1:
                paPrefix = 'u'
            elif paObject == 0:
                paPrefix = 'v'
            paGroup = f.create_group(paPrefix)

            # Write out diagonal PA
            paSubgroup = paGroup.create_group('diag')
            paArray = loadtxt(paPrefix+'d.'+str(paIndex)+'.r.txt', comments='#')
            if breakupType != 2:
                paSubgroup.create_dataset(paPrefix+'Long_r0',data=[paArray[0,1]])
                paSubgroup.create_dataset('r',data=paArray[1:,0])
                paSubgroup.create_dataset(paPrefix+'Short_r',data=paArray[1:,1])
                paArray = loadtxt(paPrefix+'d.'+str(paIndex)+'.k.txt', comments='#')
                paSubgroup.create_dataset(paPrefix+'Long_k0',data=[paArray[0,1]])
                paSubgroup.create_dataset('k',data=paArray[:,0])
                paSubgroup.create_dataset(paPrefix+'Long_k',data=paArray[:,1])
            else:
                paSubgroup.create_dataset('r',data=paArray[:,0])
                paSubgroup.create_dataset(paPrefix+'Short_r',data=paArray[:,1])


            # Write out off diagonal PA
            if paObject != 0:
                paSubgroup = paGroup.create_group('offDiag')
                paArray = loadtxt(paPrefix+'s.'+str(paIndex)+'.md.txt', comments='#')
                xs = unique(paArray[:,0])
                ys = unique(paArray[:,1])
                zs = paArray[:,2].reshape((len(xs),len(ys)))
                paSubgroup.create_dataset('x',data=xs)
                paSubgroup.create_dataset('y',data=ys)
                paSubgroup.create_dataset(paPrefix+'OffDiag',data=zs)

                # Write out fit to off diagonal PA if desired
                for iOrder in range(1,nOrder+1):
                    paSubSubgroup = paSubgroup.create_group('A.'+str(iOrder))
                    paArray = loadtxt(paPrefix+'s.'+str(paIndex)+'.A.'+str(iOrder)+'.txt', comments='#')
                    paSubSubgroup.create_dataset('r',data=paArray[:,0])
                    paSubSubgroup.create_dataset('A',data=paArray[:,1])

        f.flush()
        f.close()

        print '****************************************'
