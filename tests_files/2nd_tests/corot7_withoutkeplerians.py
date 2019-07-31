#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
#np.random.seed(2102018)
import matplotlib.pyplot as plt
plt.close('all')

from gprn.complexGP import complexGP
from gprn import weightFunction, nodeFunction, meanFunction


post_analysis = False
###### Data .rdb file #####
time,rv,rverr,fwhm,fwhmerr,bis,biserr,rhk,rhkerr = np.loadtxt("corot7_outlierclean.rdb", 
                                                              skiprows=102, unpack=True, 
                                                              usecols=(0,1,2,3,4,5,6,7,8))

##### GP object #####
nodes = [nodeFunction.QuasiPeriodic(3.28, 22.21, 0.93, 0)]
weight = weightFunction.Constant(0)
weight_values = [9.31, 2, 1, 1]
means = [meanFunction.Constant(0),
         meanFunction.Constant(0), 
         meanFunction.Constant(0), 
         meanFunction.Constant(0)]
jitters =[0, 0, 0, 0]
 
GPobj = complexGP(nodes, weight, weight_values, means, jitters, time, 
                  rv, rverr, fwhm, fwhmerr, bis, biserr, rhk, rhkerr)

loglike = GPobj.new_log_like(nodes, weight, weight_values, means, jitters)
print(loglike)

##### Setting priors #####
from scipy import stats
def loguniform(low=0, high=1, size=None):
    return np.exp(stats.uniform(low, high -low).rvs())

#node function
eta2 = stats.uniform(np.exp(-20), 40 -np.exp(-10)) 
eta3 = stats.uniform(20, 30- 20) 
eta4 = stats.uniform(np.exp(-20), 2 -np.exp(-20)) 
s = stats.uniform(np.exp(-20), 1 -np.exp(-20))

#weight function
weight_1 = stats.uniform(np.exp(-20), 20 -np.exp(-20))

#means
mean_c1 = stats.uniform(rv.min(), rv.max() -rv.min())
mean_c2 = stats.uniform(fwhm.min(), fwhm.max() -fwhm.min())
mean_c3 = stats.uniform(bis.min(), bis.max() -bis.min())
mean_c4 = stats.uniform(rhk.min(), rhk.max() -rhk.min())

#jitters
jitt1 = stats.uniform(np.exp(-20), 10 -np.exp(-20))
jitt2 = stats.uniform(np.exp(-20), 10 -np.exp(-20))
jitt3 = stats.uniform(np.exp(-20), 10 -np.exp(-20))
jitt4= stats.uniform(np.exp(-20), 10 -np.exp(-20))

def from_prior():
    return np.array([eta2.rvs(), eta3.rvs(), eta4.rvs(), s.rvs(),
                     weight_1.rvs(), weight_1.rvs(), weight_1.rvs(), weight_1.rvs(),
                     mean_c1.rvs(), mean_c2.rvs(), mean_c3.rvs(), -mean_c4.rvs(),
                     jitt1.rvs(), jitt2.rvs(), jitt3.rvs(), jitt4.rvs()])

##### MCMC properties #####
import emcee
runs, burns = 20000, 20000 #Defining runs and burn-ins

#Probabilistic model
def logprob(p):
    if any([p[0] < -20, p[0] > np.log(40.0),  
            p[1] < np.log(20.0), p[1] > np.log(30.0), 
            p[2] < -20, p[2] > np.log(2), 
            p[3] < -20, p[3] > np.log(1), 
            
            p[4] < -20, p[4] > np.log(20),
            p[5] < -20, p[5] > np.log(20),
            p[6] < -20, p[6] > np.log(20),
            p[7] < -20, p[7] > np.log(20),

            p[8] < np.log(rv.min()), p[8] > np.log(rv.max()),
            p[9] < np.log(fwhm.min()), p[9] > np.log(fwhm.max()),
            p[10] < np.log(bis.min()), p[10] > np.log(bis.max()),
            p[11] < np.log(-rhk.max()), p[11] > np.log(-rhk.min()),

            p[12] < -20, p[12] > np.log(20),
            p[13] < -20, p[13] > np.log(20),
            p[14] < -20, p[14] > np.log(20),
            p[15] < -20, p[15] > np.log(20)]):
        return -np.inf
    else:
        logprior = 0.0
        new_node = [nodeFunction.QuasiPeriodic(np.exp(p[0]), np.exp(p[1]), 
                                               np.exp(p[2]), np.exp(p[3]))]
    
        new_weight_values = [np.exp(p[4]), np.exp(p[5]), 
                             np.exp(p[6]), np.exp(p[7])]
        
        new_mean = [meanFunction.Constant(np.exp(p[8])), 
                    meanFunction.Constant(np.exp(p[9])),
                    meanFunction.Constant(np.exp(p[10])),
                    meanFunction.Constant(-np.exp(p[11]))]
        
        new_jitt = [np.exp(p[12]), np.exp(p[13]), np.exp(p[14]), np.exp(p[15])]
        return logprior + GPobj.new_log_like(new_node, 
                                             weight, new_weight_values, 
                                             new_mean, new_jitt)

#Seting up the sampler
nwalkers, ndim = 2*16, 16
sampler = emcee.EnsembleSampler(nwalkers, ndim, logprob, threads= 4)

#Initialize the walkers
p0=[np.log(from_prior()) for i in range(nwalkers)]

print("Running burn-in")
p0, _, _ = sampler.run_mcmc(p0, burns)
print("Running production chain")
sampler.run_mcmc(p0, runs);


##### MCMC analysis #####
burnin = burns
samples = sampler.chain[:, burnin:, :].reshape((-1, ndim))
samples = np.exp(samples)
samples[:, 11] = -samples[:,11]

#median and quantiles
l1,p1,l2,wn1, w1,w2,w3,w4, \
c1, c2, c3, c4, j1, j2, j3, j4 = map(lambda v: (v[1], v[2]-v[1], v[1]-v[0]),
                             zip(*np.percentile(samples, [16, 50, 84],axis=0)))

#printing results
print()
print('eta2 = {0[0]} +{0[1]} -{0[2]}'.format(l1))
print('eta3 = {0[0]} +{0[1]} -{0[2]}'.format(p1))
print('eta4 = {0[0]} +{0[1]} -{0[2]}'.format(l2))
print('s = {0[0]} +{0[1]} -{0[2]}'.format(wn1))
print()
print('RVs weight = {0[0]} +{0[1]} -{0[2]}'.format(w1))
print('FWHM weight = {0[0]} +{0[1]} -{0[2]}'.format(w2))
print('BIS weight = {0[0]} +{0[1]} -{0[2]}'.format(w3))
print('Rhk weight = {0[0]} +{0[1]} -{0[2]}'.format(w4))
print()
print('RVS offset = {0[0]} +{0[1]} -{0[2]}'.format(c1))
print('FWHM offset = {0[0]} +{0[1]} -{0[2]}'.format(c2))
print('BIS offset = {0[0]} +{0[1]} -{0[2]}'.format(c3))
print('Rhk offset = {0[0]} +{0[1]} -{0[2]}'.format(c4))
print()
print('RVs jitter = {0[0]} +{0[1]} -{0[2]}'.format(j1))
print('FWHM jitter = {0[0]} +{0[1]} -{0[2]}'.format(j2))
print('BIS jitter = {0[0]} +{0[1]} -{0[2]}'.format(j3))
print('Rhk jitter = {0[0]} +{0[1]} -{0[2]}'.format(j4))
print()

plt.figure()
for i in range(sampler.lnprobability.shape[0]):
    plt.plot(sampler.lnprobability[i, :])


##### first results #####
nodes = [nodeFunction.QuasiPeriodic(l1[0], p1[0], l2[0], wn1[0])]

weight = weightFunction.Constant(0)
weight_values = [w1[0], w2[0], w3[0], w4[0]]

means = [meanFunction.Constant(c1[0]), meanFunction.Constant(c2[0]), 
         meanFunction.Constant(c3[0]), meanFunction.Constant(c4[0])]

jitters = [j1[0], j2[0], j3[0], j4[0]]

loglike = GPobj.new_log_like(nodes, weight, weight_values, means, jitters)
print(loglike)

##### final plots #####
mu11, std11, cov11 = GPobj.predict_gp(nodes = nodes, weight = weight, 
                                      weight_values = weight_values, means = means,
                                      jitters = jitters,
                                      time = np.linspace(time.min(), time.max(), 500),
                                      dataset = 1)
mu22, std22, cov22 = GPobj.predict_gp(nodes = nodes, weight = weight, 
                                      weight_values = weight_values, means = means,
                                      jitters = jitters,
                                      time = np.linspace(time.min(), time.max(), 500),
                                      dataset = 2)
mu33, std33, cov33 = GPobj.predict_gp(nodes = nodes, weight = weight, 
                                      weight_values = weight_values, means = means,
                                      jitters = jitters,
                                      time = np.linspace(time.min(), time.max(), 500),
                                      dataset = 3)
mu44, std44, cov44 = GPobj.predict_gp(nodes = nodes, weight = weight, 
                                      weight_values = weight_values, means = means,
                                      jitters = jitters,
                                      time = np.linspace(time.min(), time.max(), 500),
                                      dataset = 4)

f, (ax1, ax2, ax3, ax4) = plt.subplots(4, sharex=True)
ax1.set_title('Fits')
ax1.fill_between(np.linspace(time.min(), time.max(), 500), 
                 mu11+std11, mu11-std11, color="grey", alpha=0.5)
ax1.plot(np.linspace(time.min(), time.max(), 500), mu11, "k--", alpha=1, lw=1.5)
ax1.errorbar(time,rv, rverr, fmt = "b.")
ax1.set_ylabel("RVs")

ax2.fill_between(np.linspace(time.min(), time.max(), 500), 
                 mu22+std22, mu22-std22, color="grey", alpha=0.5)
ax2.plot(np.linspace(time.min(), time.max(), 500), mu22, "k--", alpha=1, lw=1.5)
ax2.errorbar(time,fwhm, fwhmerr, fmt = "b.")
ax2.set_ylabel("FWHM")

ax3.fill_between(np.linspace(time.min(), time.max(), 500), 
                 mu33+std33, mu33-std33, color="grey", alpha=0.5)
ax3.plot(np.linspace(time.min(), time.max(), 500), mu33, "k--", alpha=1, lw=1.5)
ax3.errorbar(time,bis, biserr, fmt = "b.")
ax3.set_ylabel("BIS")

ax4.fill_between(np.linspace(time.min(), time.max(), 500), 
                 mu44+std44, mu44-std44, color="grey", alpha=0.5)
ax4.plot(np.linspace(time.min(), time.max(), 500), mu44, "k--", alpha=1, lw=1.5)
ax4.errorbar(time, rhk, rhkerr, fmt = "b.")
ax4.set_ylabel("R'hk")
f.savefig('corot7_withoutkeplerians_fit.png')
plt.show()


likes=[] #likelihoods calculation
for i in range(samples[:,0].size):
    new_node = [nodeFunction.QuasiPeriodic(samples[i,0], samples[i,1], 
                                           samples[i,2], samples[i,3])]

    new_weight = [samples[i,4], samples[i,5], samples[i,6], samples[i,7]]
    
    new_means = [meanFunction.Constant(samples[i,8]), 
                 meanFunction.Constant(samples[i,9]),
                 meanFunction.Constant(samples[i,10]),
                 meanFunction.Constant(samples[i,11])]

    new_jitt = [samples[i,12], samples[i,13], samples[i,14], samples[i,15]]
    
    likes.append(GPobj.new_log_like(new_node, weight, new_weight, new_means,
                                    new_jitt))
plt.figure()
plt.hist(likes, bins = 20, label='likelihood')
plt.show()

new_samples = np.vstack([samples.T,np.array(likes).T]).T
#checking the likelihood that matters to us
values = np.where(new_samples[:,-1] > 0)
new_samples = new_samples[values,:]
new_samples = new_samples.reshape(-1, 17)

#median and quantiles
l11,p11,l12,wn11, w11,w12,w13,w14, \
c11, c12, c13, c14, j11, j12, j13, j14, logl1 = map(lambda v: (v[1], v[2]-v[1], v[1]-v[0]),
                             zip(*np.percentile(new_samples, [16, 50, 84],axis=0)))

#printing results
print('FINAL SOLUTION')
print()
print('eta2 = {0[0]} +{0[1]} -{0[2]}'.format(l1))
print('eta3 = {0[0]} +{0[1]} -{0[2]}'.format(p1))
print('eta4 = {0[0]} +{0[1]} -{0[2]}'.format(l2))
print('s = {0[0]} +{0[1]} -{0[2]}'.format(wn1))
print()
print('RVs weight = {0[0]} +{0[1]} -{0[2]}'.format(w1))
print('FWHM weight = {0[0]} +{0[1]} -{0[2]}'.format(w2))
print('BIS weight = {0[0]} +{0[1]} -{0[2]}'.format(w3))
print('Rhk weight = {0[0]} +{0[1]} -{0[2]}'.format(w4))
print()
print('RVS offset = {0[0]} +{0[1]} -{0[2]}'.format(c1))
print('FWHM offset = {0[0]} +{0[1]} -{0[2]}'.format(c2))
print('BIS offset = {0[0]} +{0[1]} -{0[2]}'.format(c3))
print('Rhk offset = {0[0]} +{0[1]} -{0[2]}'.format(c4))
print()
print('RVs jitter = {0[0]} +{0[1]} -{0[2]}'.format(j1))
print('FWHM jitter = {0[0]} +{0[1]} -{0[2]}'.format(j2))
print('BIS jitter = {0[0]} +{0[1]} -{0[2]}'.format(j3))
print('Rhk jitter = {0[0]} +{0[1]} -{0[2]}'.format(j4))
print()

##### Corner plots of the data #####
import corner

corner.corner(samples[:,0:8], 
                    labels=["eta2", "eta3", "eta4", "s", 
                            "RVs weight", "FWHM weight", "BIS weight", "Rhk weight"],
                    show_titles=True, fill_contours=True)
plt.savefig('corot7_withoutkeplerians_corner1.png')
corner.corner(samples[:,8:12], 
                    labels=["RV offset", "FWHM offset", "BIS offset", "Rhk offset"],
                    show_titles=True, fill_contours=True)
plt.savefig('corot7_withoutkeplerians_corner2.png')
corner.corner(samples[:,12:16], 
                    labels=["RV jitter", "FWHM jitter", "BIS jitter", "Rhk jitter"],
                    show_titles=True, fill_contours=True)
plt.savefig('corot7_withoutkeplerians_corner3.png')



fig, axes = plt.subplots(8, sharex=True)
labels=["eta 2", "eta 3", "eta 4", "s", 
                            "RVs weight", "FWHM weight", "BIS weight", "Rhk weight"]
for i in range(8):
    ax = axes[i]
    ax.plot(np.exp(sampler.chain[:, :, i]).T, "k", alpha=0.3)
    ax.set_xlim(runs, runs+burns)
    ax.set_ylabel(labels[i])
    ax.yaxis.set_label_coords(-0.1, 0.5)
axes[-1].set_xlabel("step number");
plt.savefig('corot7_withoutkeplerians_chains1.png')

fig, axes = plt.subplots(4, sharex=True)
labels=["RVs offset", "FWHM offset", "BIS offset", "Rhk offset"]
for i in range(8,12):
    ax = axes[i-8]
    ax.plot(np.exp(sampler.chain[:, :, i]).T, "k", alpha=0.3)
    ax.set_xlim(runs, runs+burns)
    ax.set_ylabel(labels[i-8])
    ax.yaxis.set_label_coords(-0.1, 0.5)
axes[-1].set_xlabel("step number");
plt.savefig('corot7_withoutkeplerians_chains2.png')

fig, axes = plt.subplots(4, sharex=True)
labels=["RVs jitter", "FWHM jitter", "BIS jitter", "Rhk jitter"]
for i in range(12,16):
    ax = axes[i-12]
    ax.plot(np.exp(sampler.chain[:, :, i]).T, "k", alpha=0.3)
    ax.set_xlim(runs, runs+burns)
    ax.set_ylabel(labels[i-12])
    ax.yaxis.set_label_coords(-0.1, 0.5)
axes[-1].set_xlabel("step number");
plt.savefig('corot7_withoutkeplerians_chains3.png')


##### Saving data #####
np.save('corot7_withoukeplerians.npy', samples)