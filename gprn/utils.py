# -*- coding: utf-8 -*-
import  numpy as np

##### Semi amplitude calculation ##############################################
def semi_amplitude(period, Mplanet, Mstar, ecc):
    """
        Calculates the semi-amplitude (K) caused by a planet with a given
    period and mass Mplanet, around a star of mass Mstar, with a 
    eccentricity ecc.
        Parameters:
            period = period in years
            Mplanet = planet's mass in Jupiter masses, tecnically is the M.sin i
            Mstar = star mass in Solar masses
            ecc = eccentricity
        Returns:
            Semi-amplitude K
    """
    per = np.float(np.power(1/period, 1/3))
    Pmass = Mplanet / 1
    Smass = np.float(np.power(1/Mstar, 2/3))
    Ecc = 1 / np.sqrt(1 - ecc**2)

    return 28.435 * per * Pmass* Smass * Ecc


##### Keplerian function ######################################################
def keplerian(P=365, K=.1, e=0,  w=np.pi, T=0, phi=None, gamma=0, t=None):
    """
        keplerian() simulates the radial velocity signal of a planet in a 
    keplerian orbit around a star.
        Parameters:
            P = period in days
            K = RV amplitude
            e = eccentricity
            w = longitude of the periastron
            T = zero phase
            phi = orbital phase
            gamma = constant system RV
            t = time of measurements
        Returns:
            t = time of measurements
            RV = rv signal generated
    """
    if t is  None:
        print()
        print('TEMPORAL ERROR, time is nowhere to be found')
        print()

    #mean anomaly
    if phi is None:
        mean_anom = [2*np.pi*(x1-T)/P  for x1 in t]
    else:
        T = t[0] - (P*phi)/(2.*np.pi)
        mean_anom = [2*np.pi*(x1-T)/P  for x1 in t]

    #eccentric anomaly -> E0=M + e*sin(M) + 0.5*(e**2)*sin(2*M)
    E0 = [x + e*np.sin(x)  + 0.5*(e**2)*np.sin(2*x) for x in mean_anom]
    #mean anomaly -> M0=E0 - e*sin(E0)
    M0 = [x - e*np.sin(x) for x in E0]

    i = 0
    while i < 1000:
        #[x + y for x, y in zip(first, second)]
        calc_aux = [x2-y for x2,y in zip(mean_anom, M0)]    
        E1 = [x3 + y/(1-e*np.cos(x3)) for x3,y in zip(E0, calc_aux)]
        M1 = [x4 - e*np.sin(x4) for x4 in E0]   
        i += 1
        E0 = E1
        M0 = M1

    nu = [2*np.arctan(np.sqrt((1+e)/(1-e))*np.tan(x5/2)) for x5 in E0]
    RV = [ gamma + K*(e*np.cos(w)+np.cos(w+x6)) for x6 in nu]
    RV = [x for x in RV] #m/s 
    return t, RV


##### Phase-folding function ##################################################
def phase_folding(t, y, yerr, period):
    """
        phase_folding() allows the phase folding (duh...) of a given data
    accordingly to a given period
        Parameters:
            t = time
            y = measurements
            yerr = measurement errors
            period = period to fold the data
        Returns:
            phase = phase
            folded_y = sorted measurments according to the phase
            folded_yerr = sorted errors according to the phase
    """
    #divide the time by the period to convert to phase
    foldtimes = t / period
    #remove the whole number part of the phase
    foldtimes = foldtimes % 1
    
    if yerr is None:
        yerr = 0 * y
    
    #sort everything
    phase, folded_y, folded_yerr = zip(*sorted(zip(foldtimes, y, yerr)))
    return phase, folded_y, folded_yerr


##### MCMC with dynesty or emcee ##############################################
def run_mcmc(prior_func, elbo_func, iterations = 1000, sampler = 'emcee'):
    """
        run_mcmc() allow the user to run emcee or dynesty automatically
        Parameters:
            prior_func = function that return an array with the priors
            elbo_func = function that calculates the ELBO 
            iterations = number of iterations; in emcee the same number of 
                        iterations will be used as mcmc burn-in followed by the 
                        same number of iterations as mcmc run
            sampler = 'emcee' or 'dynesty'
        Returns:
            result = return the sampler's results accordingly to the sampler
    """
    import dynesty, emcee
    from multiprocessing import Pool
    if sampler == 'emcee':
        ndim = prior_func().size
        burns, runs = int(iterations), int(iterations)
        #defining emcee properties
        nwalkers = 2*ndim
        sampler = emcee.EnsembleSampler(nwalkers, ndim, 
                                        elbo_func, threads= 4)
        
        #Initialize the walkers
        p0=[prior_func() for i in range(nwalkers)]
        #running burns and runs
        print("Running burn-in...")
        p0, _, _ = sampler.run_mcmc(p0, burns)
        print("\nRunning production chain...")
        sampler.reset()
        sampler.run_mcmc(p0, runs)
        
        #preparing samples to return
        samples = sampler.chain[:, :, :].reshape((-1, ndim))
        lnprob = sampler.lnprobability[:, :].reshape(nwalkers*runs, 1)
        results = np.vstack([samples.T,np.array(lnprob).T]).T
    if sampler == 'dynesty':
        ndim = prior_func(0).size
        dsampler = dynesty.DynamicNestedSampler(elbo_func, prior_func, ndim=ndim, 
                                        nlive = 5, sample='rwalk',
                                        queue_size=4, pool=Pool(4))
        print("Running dynesty...")
        dsampler.run_nested(nlive_init = 20, maxiter = iterations)
        results = dsampler.results
    return results


##### scipy minimization ######################################################
def run_minimization(elbo_func, init_x, constraints, iterations=1000):
    """
        run_mcmc() allow the user to run the COBYLA minimization method
        Parameters:
            elbo_func = function that calculates the ELBO 
            init_x = initial values
            constraints = constraints for ‘trust-constr’ 
            iterations = number of iterations;
    """
    from scipy.optimize import minimize
    #defining the constraints
    cons = []
    for factor in range(len(constraints)):
        lower, upper = constraints[factor]
        l = {'type': 'ineq',
             'fun': lambda x, lb=lower, i=factor: x[i] - lb}
        u = {'type': 'ineq',
             'fun': lambda x, ub=upper, i=factor: ub - x[i]}
        cons.append(l)
        cons.append(u)
    #initial values of the parameters
    x0 = np.array(init_x)
    #running minimization
    res = minimize(elbo_func, x0, constraints=cons, method='COBYLA',
               options={'disp': True, 'maxiter': iterations})
    return res


# ##### One function to run them all ###########################################
#def runThemAll(num_nodes, time, val1, val1err, val2, val2err,
#               nodes, weights, jitter, iterations, x0):
#    from gprn.mf import inference
#    #Our GPRN object
#    GPRN = inference(num_nodes, time, val1, val1err, val2, val2err)
#    
#    nodeParsSize = []
#    for i in range(num_nodes):
#        nodeParsSize.append(len(nodes[i].pars))
#    weightParsSize = [len(weights[0].pars)]
#    
#    def ELBO(x):
#        #x <- parameters to optimize
#        z = 0
#        for i in range(num_nodes):
#            for j in range(nodeParsSize[i]):
#                nodes[i].pars[j] = x
#                
#                
#        nodes = [SquaredExponential(1,ell1,j1)]
#     #   nodes = [WhiteNoise(j1)]
#        weight = [SquaredExponential(1,ell2, j2)]
#        means = [Constant(m1), Constant(m2)]
#        jitter = [1]
#            
#        ELB, _, _ = GPRN.EvidenceLowerBound(nodes, weight, means, jitter, 
#                                            iterations = 50000,
#                                            prints = False, plots = False)
#        return -ELB
#
#    
#    
#    return GPRN

### END
