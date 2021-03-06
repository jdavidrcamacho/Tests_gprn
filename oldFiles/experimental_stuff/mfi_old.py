#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
import matplotlib.pylab as plt
from scipy.linalg import inv, cholesky, cho_factor, cho_solve, LinAlgError
from scipy.stats import multivariate_normal
from copy import copy

from gprn.covFunction import Linear as covL
from gprn.covFunction import Polynomial as covP
from gprn.covFunction import WhiteNoise as covWN

class inference(object):
    """ 
        Class to perform variational inference for GPRNs. 
        See Nguyen & Bonilla (2013) for more information.
        Parameters:
            nodes = latent noide functions f(x), called f hat in the article
            weight = latent weight funtion w(x)
            means = array of means functions being used, set it to None if a 
                    model doesn't use it
            jitters = jitter value of each dataset
            time = time
            *args = the data (or components), it needs be given in order of
                data1, data1_error, data2, data2_error, etc...
    """ 
    def  __init__(self, nodes, weight, means, jitters, time, *args):
        #node functions; f(x) in Wilson et al. (2012)
        self.nodes = np.array(nodes)
        #weight function; w(x) in Wilson et al. (2012)
        self.weight = weight
        #mean functions
        self.means = np.array(means)
        #jitters
        self.jitters = np.array(jitters)
        #time
        self.time = time 
        #the data, it should be given as data1, data1_error, data2, ...
        self.args = args 
        
        #number of nodes being used; q in Wilson et al. (2012)
        self.q = len(self.nodes)
        #number of outputs y(x); p in Wilson et al. (2012)
        self.p = int(len(self.args)/2)
        #total number of weights, we will have q*p weights in total
        self.qp =  self.q * self.p
        #number of observations, N in Wilson et al. (2012)
        self.N = self.time.size
        
        #to organize the data we now join everything
        self.tt = np.tile(time, self.p) #"extended" time because why not?
        ys = [] 
        yerrs = []
        for i,j  in enumerate(args):
            if i%2 == 0:
                ys.append(j)
            else:
                yerrs.append(j)
        self.y = np.array(ys).reshape(self.p, self.N) #matrix p*N of outputs
        self.yerr = np.array(yerrs).reshape(self.p, self.N) #matrix p*N of errors

        #check if the input was correct
        assert self.means.size == self.p, \
        'The numbers of means should be equal to the number of components'
        assert (i+1)/2 == self.p, \
        'Given data and number of components dont match'


##### mean functions definition ################################################
    @property
    def mean_pars_size(self):
        return self._mean_pars_size

    @mean_pars_size.getter
    def mean_pars_size(self):
        self._mean_pars_size = 0
        for m in self.means:
            if m is None: self._mean_pars_size += 0
            else: self._mean_pars_size += m._parsize
        return self._mean_pars_size

    @property
    def mean_pars(self):
        return self._mean_pars

    @mean_pars.setter
    def mean_pars(self, pars):
        pars = list(pars)
        assert len(pars) == self.mean_pars_size
        self._mean_pars = copy(pars)
        for _, m in enumerate(self.means):
            if m is None: 
                continue
            j = 0
            for j in range(m._parsize):
                m.pars[j] = pars.pop(0)

    def _mean(self, means, time=None):
        """
            Returns the values of the mean functions
        """
        if time is None:
            N = self.time.size
            m = np.zeros_like(self.tt)
            for i, meanfun in enumerate(means):
                if meanfun is None:
                    continue
                else:
                    m[i*N : (i+1)*N] = meanfun(self.time)
        else:
            N = time.size
            tt = np.tile(time, self.p)
            m = np.zeros_like(tt)
            for i, meanfun in enumerate(means):
                if meanfun is None:
                    continue
                else:
                    m[i*N : (i+1)*N] = meanfun(time)
        return m


##### To create matrices and samples ###########################################
    def _kernelMatrix(self, kernel, time = None):
        """
            Returns the covariance matrix created by evaluating a given kernel 
        at inputs time.
        """
        r = time[:, None] - time[None, :]
        
        #to deal with the non-stationary kernels problem
        if isinstance(kernel, (covL, covP)):
            K = kernel(None, time[:, None], time[None, :])
        else:
            K = kernel(r) + 1e-6*np.diag(np.diag(np.ones_like(r)))
        return K

    def _predictKernelMatrix(self, kernel, time):
        """
            To be used in predict_gp()
        """
        if isinstance(kernel, (covL, covP)):
            K = kernel(None, time, self.time[None, :])
        if isinstance(kernel, covWN):
            K = 0*np.ones_like(self.time) 
        else:
            if time.size == 1:
                r = time - self.time[None, :]
            else:
                r = time[:,None] - self.time[None,:]
            K = kernel(r) 
        return K

    def _kernel_pars(self, kernel):
        """
            Returns the hyperparameters of a given kernel
        """
        return kernel.pars

    def _CB_matrix(self, nodes, weight, time):
        """
            Creates the matrix CB (eq. 5 from Wilson et al. 2012), that will be 
        an N*q*(p+1) X N*q*(p+1) block diagonal matrix
            Parameters:
                nodes = array of node functions 
                weight = weight function
                time = array containing the time
            Returns:
                CB = matrix CB
        """
        CB_size = time.size * self.q * (self.p + 1)
        CB = np.zeros((CB_size, CB_size)) #initial empty matrix
        
        pos = 0 #we start filling CB at position (0,0)
        #first we enter the nodes
        for i in range(self.q):
            node_CovMatrix = self._kernelMatrix(nodes[i], time)
            CB[pos:pos+time.size, pos:pos+time.size] = node_CovMatrix
            pos += time.size
        weight_CovMatrix = self._kernelMatrix(weight, time)
        #then we enter the weights
        for i in range(self.qp):
            CB[pos:pos+time.size, pos:pos+time.size] = weight_CovMatrix
            pos += time.size
        return CB

    def _sample_CB(self, nodes, weight, time):
        """ 
            Returns samples from the matrix CB
            Parameters:
                nodes = array of node functions 
                weight = weight function
                time = array containing the time
            Returns:
                Samples of CB
        """
        mean = np.zeros(time.size*self.q*(self.p+1))
        cov = self._CB_matrix(nodes, weight, time)
        norm = multivariate_normal(mean, cov, allow_singular=True)
        return norm.rvs()

    def _fhat_and_w(self, u):
        """
            Given a list, divides it in the corresponding nodes (f hat) and
        weights (w) parts.
            Parameters:
                u = array
            Returns:
                f = array with the samples of the nodes
                w = array with the samples of the weights
        """
        f = u[:self.q * self.N].reshape((1, self.q, self.N))
        w = u[self.q * self.N:].reshape((self.p, self.q, self.N))
        return f, w

    def u_to_fhatW(self, nodes, weight, time):
        """
            Returns the samples of CB that corresponds to the nodes f hat and
        weights w.
            Parameters:
                nodes = array of node functions 
                weight = weight function
                time = array containing the time
            Returns:
                fhat = array with the samples of the nodes
                w = array with the samples of the weights
        """
        u = self._sample_CB(nodes, weight, time)
        fhat = u[:self.q * time.size].reshape((1, self.q, time.size))
        w = u[self.q * time.size:].reshape((self.p, self.q, time.size))
        return fhat, w

    def get_y(self, n, w, time, means = None):
        # obscure way to do it
        y = np.einsum('ij...,jk...->ik...', w, n).reshape(self.p, time.size)
        y = (y + self._mean(means, time)) if means else time
        return y

    def _cholNugget(self, matrix, maximum=10):
        """
            Returns the cholesky decomposition to a given matrix, if this matrix
        is not positive definite, a nugget is added to its diagonal.
            Parameters:
                matrix = matrix to decompose
                maximum = number of times a nugget is added.
            Returns:
                L = matrix containing the Cholesky factor
                nugget = nugget added to the diagonal
        """
        nugget = 0 #our nugget starts as zero
        try:
            nugget += np.abs(np.diag(matrix).mean()) * 1e-5
            L = cholesky(matrix).T
            return L, nugget
        except LinAlgError:
            print('NUGGET ADDED TO DIAGONAL!')
            n = 0 #number of tries
            while n < maximum:
                print ('n:', n+1, ', nugget:', nugget)
                try:
                    L = cholesky(matrix + nugget*np.identity(matrix.shape[0])).T
                    return L, nugget
                except LinAlgError:
                    nugget *= 10.0
                finally:
                    n += 1
            raise LinAlgError("Still not positive definite, even with nugget.")


##### Mean-Field Inference functions ###########################################
    def EvidenceLowerBound(self, nodes, weight, means, jitters, time, 
                               iterations = 100, prints = False, plots = False):
        """
            Returns the Evidence Lower bound, eq.10 in Nguyen & Bonilla (2013)
            Parameters:
                nodes = array of node functions 
                weight = weight function
                means = array with the mean functions
                jitters = jitters array
                time = time array
                iterations = number of iterations
                prints = True to print ELB value at each iteration
                plots = True to plot ELB evolution 
            Returns:
                sum_ELB = Evidence lower bound
                muF = array with the new means for each node
                muW = array with the new means for each weight
        """ 
        #Initial variational parameters
        D = self.time.size * self.q *(self.p+1)
        mu = np.random.randn(D,1)
        var = np.random.rand(D,1)
        muF, muW = self._fhat_and_w(mu)
        varF, varW = self._fhat_and_w(var)

        #experiment
        D = self.time.size * self.q *(self.p+1)
        np.random.seed(100)
        mu = np.random.rand(D,1);
        np.random.seed(200)
        var = np.random.rand(D,1);
        muF, muW = self._fhat_and_w(mu)
        varF, varW = self._fhat_and_w(var)
        
        iterNumber = 0
        ELB = [0]
        if plots:
            ELP, ELL, ENT = [0], [0], [0]
        while iterNumber < iterations:
            #print(muW)
            sigmaF, muF, sigmaW, muW = self._updateSigmaMu_new(nodes, weight, 
                                                               means, jitters, time,
                                                               muF, varF, muW, varW)
            #print(muW)
            muF = muF.reshape(1, self.q, self.N) #new mean for the nodes
            varF =  []
            for i in range(self.q):
                varF.append(np.diag(sigmaF[i]))
            varF = np.array(varF).reshape(1, self.q, self.N) #new variance for the nodes
            muW = muW.reshape(self.p, self.q, self.N) #new mean for the weights
            varW =  []
            for j in range(self.q):
                for i in range(self.p):
                    varW.append(np.diag(sigmaW[j, i, :]))
            varW = np.array(varW).reshape(self.p, self.q, self.N) #new variance for the weights
            #Entropy
            Entropy = self._entropy(sigmaF, sigmaW)
            #Expected log prior
            ExpLogPrior = self._expectedLogPrior(nodes, weight, 
                                                sigmaF, muF,  sigmaW, muW)
            #Expected log-likelihood
            ExpLogLike = self._expectedLogLike_new(nodes, weight, means, jitters,
                                                   sigmaF, muF, sigmaW, muW)
            if plots:
                ELL.append(ExpLogLike)
                ELP.append(ExpLogPrior)
                ENT.append(Entropy)
            
            #Evidence Lower Bound
            sum_ELB = (ExpLogLike + ExpLogPrior + Entropy)
            ELB.append(sum_ELB)
            if prints:
                self._prints(sum_ELB, ExpLogLike, ExpLogPrior, Entropy)
            #Stoping criteria
            criteria = np.abs(np.mean(ELB[-10:]) - sum_ELB)
            if criteria < 1e-10 and criteria != 0 :
                if prints:
                    print('\nELB converged to ' +str(sum_ELB) \
                          + '; algorithm stopped at iteration ' \
                          +str(iterNumber) +'\n')
                if plots:
                    self._plots(ELB[1:], ELL[1:-1], ELP[1:-1], ENT[1:-1])
                print(' it took ' +str(iterNumber) + ' iterations')
                return sum_ELB, muF, muW
            iterNumber += 1
        if plots:
            self._plots(ELB[1:], ELL[1:-1], ELP[1:-1], ENT[1:-1])
        print(' it took ' +str(iterNumber) + ' iterations')
        return sum_ELB, muF, muW
        
    
    
    def Prediction_new(self, nodes, weights, means, jitters, tstar, muF, muW):
        """
            Prediction for mean-field inference
            Parameters:
                nodes = array of node functions 
                weight = weight function
                means = array with the mean functions
                jitters = jitters array
                tstar = predictions time
                muF = array with the initial means for each node
                varF = array with the initial variance for each node
                muW = array with the initial means for each weight
            Returns:
                ystar = predicted means
        """
        Kf = np.array([self._kernelMatrix(i, self.time) for i in nodes])
        Lf = np.array([self._cholNugget(i)[0] for i in Kf])
        Kw = np.array([self._kernelMatrix(j, self.time) for j in weights])
        Lw = np.array([self._cholNugget(j)[0] for j in Kw])

        #mean functions
        means = self._mean(means, tstar)
        means = np.array_split(means, self.p)

        ystar = np.zeros((self.p, tstar.size))

        for i in range(tstar.size):
            Kf_s = np.array([self._predictKernelMatrix(i1, tstar[i]) for i1 in nodes])
            Kw_s = np.array([self._predictKernelMatrix(i2, tstar[i]) for i2 in weights])
            print(Lf.shape, Kf_s.shape)
#            alphaLf = inv(np.squeeze(Lf)) @ np.squeeze(Kf_s).T
            alphaLw = inv(np.squeeze(Lw)) @ np.squeeze(Kw_s).T
            idx_f, idx_w = 1, 1
            Wstar, fstar = np.zeros((self.p, self.q)), np.zeros((self.q, 1))
            for q in range(self.q):
                alphaLf = inv(np.squeeze(Lf[q,:,:])) @ np.squeeze(Kf_s[q,:,:]).T
                print(alphaLf.shape, Lf.shape, muF.shape)
                fstar[q] = alphaLf @ (inv(np.squeeze(Lf[q,:,:])) @ muF[:,q,:].T)
                idx_f += self.N
                for p in range(self.p):
                    Wstar[p, q] = alphaLw @ (inv(np.squeeze(Lw[0])) @ muW[p][q].T)
                    idx_w += self.N
            ystar[:,i] = ystar[:, i] + np.squeeze(Wstar @ fstar)
                    
#        ystar += self._mean(means, tstar) #adding the mean function
#        print(ystar.shape)
        combined_ystar = []
        for i in range(self.p):
            combined_ystar.append(ystar[i] + means[i])
        combined_ystar = np.array(combined_ystar)
#        print(combined_ystar.shape)
        return combined_ystar

    
        
    def Prediction(self, nodes, weights, means, jitters, tstar, muF, muW):
        """
            Prediction for mean-field inference
            Parameters:
                nodes = array of node functions 
                weight = weight function
                means = array with the mean functions
                jitters = jitters array
                tstar = predictions time
                muF = array with the initial means for each node
                varF = array with the initial variance for each node
                muW = array with the initial means for each weight
            Returns:
                ystar = predicted means
        """
        Kf = np.array([self._kernelMatrix(i, self.time) for i in nodes])
        invKf = np.array([inv(i) for i in Kf])
        Kw = np.array([self._kernelMatrix(j, self.time) for j in weights])
        invKw = np.array([inv(j) for j in Kw])

        #mean functions
        means = self._mean(means, tstar)
        means = np.array_split(means, self.p)

        ystar = []
        for n in range(tstar.size):
            Kfstar = np.array([self._predictKernelMatrix(i1, tstar[n]) for i1 in nodes])
            Kwstar = np.array([self._predictKernelMatrix(i2, tstar[n]) for i2 in weights])
            Efstar, Ewstar = 0, 0
            for j in range(self.q):
#                print(Kfstar.shape, invKf.shape, muF.shape)
                Efstar += Kfstar[j,:,:] @(invKf[j,:,:] @muF[:,j,:].T) 
                for i in range(self.p):
                    Ewstar += Kwstar[0] @(invKw[0] @muW[i][j].T)
            ystar.append(Ewstar@ Efstar)
        ystar = np.array(ystar).reshape(tstar.size) #final mean

#        ystar += self._mean(means, tstar) #adding the mean function

        combined_ystar = []
        for i in range(self.p):
            combined_ystar.append(ystar + means[i])
        combined_ystar = np.array(combined_ystar)
        
        
        
#        Kf = np.array([self._kernelMatrix(i, self.time) for i in nodes])
#        invKf = np.array([inv(i) for i in Kf])
#        Kw = np.array([self._kernelMatrix(j, self.time) for j in weights])
#        invKw = np.array([inv(j) for j in Kw])
#
#        final_ystars = []
#        for p in range(self.p):
#            #mean
#            ystar = []
#            for n in range(tstar.size):
#                Kfstar = np.array([self._predictKernelMatrix(i1, tstar[n]) for i1 in nodes])
#                Kwstar = np.array([self._predictKernelMatrix(i2, tstar[n]) for i2 in weights])
#                Efstar, Ewstar = 0, 0
#                for j in range(self.q):
#                    Efstar += Kfstar[j] @(invKf[j] @muF[j].T) 
#                    for i in range(self.p):
#                        Ewstar += Kwstar[0] @(invKw[0] @muW[i][j].T)
#                ystar.append(Ewstar@ Efstar)
#            ystar = np.array(ystar).reshape(tstar.size) #final mean
#            #ystar += self._mean(means[p], tstar) #adding the mean function
#            final_ystars.append(ystar)
#        final_ystars = np.concatenate(final_ystars, axis=0)
#        final_ystars += self._mean(means, tstar)
#        final_ystars = np.array_split(final_ystars, self.p)


#        #standard deviation
#        Kfstar = np.array([self._predictKernelMatrix(i, tstar) for i in nodes])
#        Kwstar = np.array([self._predictKernelMatrix(j, tstar) for j in weights])
#        Kfstarstar = np.array([self._kernelMatrix(i, tstar) for i in nodes])
#        Kwstarstar = np.array([self._kernelMatrix(j, tstar) for j in weights])
#        
#        #firstTerm = tstar.size x tstar.size matrix
#        firstTermAux1 = (Kwstar[0] @invKw[0].T @muW[0].T).T @(Kwstar[0] @invKw[0] @muW[0].T)
#        firstTermAux2 = Kfstarstar - (Kfstar[0] @invKf[0].T @Kfstar[0].T)
#        firstTerm = np.array(firstTermAux1 * firstTermAux2).reshape(tstar.size, tstar.size)
#        #secondTerm = tstar.size x tstar.size matrix
#        secondTermAux1 = Kwstarstar - Kwstar[0] @invKw[0].T @Kwstar[0].T
#        secondTermAux2 = firstTermAux2.reshape(tstar.size, tstar.size)
#        secondTermAux3 = (Kfstar[0] @invKf[0].T @muF[0].T) @(Kfstar[0] @invKf[0].T @muF[0].T).T
#        secondTerm = secondTermAux1[0] @(secondTermAux2 + secondTermAux3)
#        
#        errors = np.identity(tstar.size) * ((np.sum(jitters)/self.p)**2 \
#                            + (np.sum(self.yerr[0,:])/self.N)**2)
#        total = firstTerm + secondTerm + errors
#        stdstar = np.sqrt(np.diag(total)) #final standard deviation
        return combined_ystar

    def _updateSigmaMu_new(self, nodes, weight, means, jitters, time,
                           muF, varF, muW, varW):
        """
            Efficient closed-form updates fot variational parameters. This
        corresponds to eqs. 16, 17, 18, and 19 of Nguyen & Bonilla (2013) 
            Parameters:
                nodes = array of node functions 
                weight = weight function
                jitters = jitters array
                time = array containing the time
                muF = array with the initial means for each node
                varF = array with the initial variance for each node
                muW = array with the initial means for each weight
                varW = array with the initial variance for each weight
            Returns:
                sigma_f = array with the covariance for each node
                mu_f = array with the means for each node
                sigma_w = array with the covariance for each weight
                mu_w = array with the means for each weight
        """
        new_y = np.concatenate(self.y) - self._mean(means)
        new_y = np.array_split(new_y, self.p)
        
#        error_term = 0
#        for i in range(self.p):
#            error_term += jitters[i]**2 + (np.sum(self.yerr[i,:]**2))#/self.N)**2
#        error_term /= self.p
#        error_term = 1
        error_term = np.sqrt(np.sum(np.array(jitters)**2)) / self.p
        for i in range(self.p):
            error_term += np.sqrt(np.sum(self.yerr[i,:]**2)) / (self.N)
        error_term = error_term
        error_term = 1
        
        #kernel matrix for the nodes
        Kf = np.array([self._kernelMatrix(i, time) for i in nodes])
        #kernel matrix for the weights
        Kw = np.array([self._kernelMatrix(j, time) for j in weight]) 
        
        #we have Q nodes => j in the paper; we have P y(x)s => i in the paper
        sigma_f, mu_f = [], [] #creation of Sigma_fj and mu_fj
        for j in range(self.q):
            Diag_fj, tmp = 0, 0
            for i in range(self.p):
                Diag_fj += muW[i, j, :] * muW[i, j, :] + varW[i, j, :]
                Sum_nj = np.zeros(self.N)
                for k in range(self.q):
                    if k != j:
                        muF = muF.T.reshape(1, self.q, self.N )
                        Sum_nj += muW[i, k, :] * muF[:, k,:].reshape(self.N)
                tmp += (new_y[i][:] - Sum_nj) * muW[i, j, :]
            CovF = np.diag(error_term / Diag_fj) + Kf[j]
            CovF = Kf[j] - Kf[j] @ (inv(CovF) @ Kf[j])
            sigma_f.append(CovF)
            mu_f.append(CovF @ tmp / error_term)
        sigma_f = np.array(sigma_f)
        mu_f = np.array(mu_f)
        
        sigma_w, mu_w = [], [] #creation of Sigma_wij and mu_wij
        for i in range(self.p):
            for j in range(self.q):
                mu_fj = mu_f[j]
                var_fj = np.diag(sigma_f[j])
                Diag_ij = mu_fj * mu_fj + var_fj
                Kw = np.squeeze(Kw)
                CovWij = np.diag(error_term / Diag_ij) + Kw
                CovWij = Kw - Kw @ (inv(CovWij) @ Kw)
                Sum_nj = 0
                for k in range(self.q):
                    if k != j:
                        Sum_nj += mu_f[k].reshape(self.N) * np.array(muW[i, k, :])
                tmp = (new_y[i][:] - Sum_nj) * mu_f[j,:]
                sigma_w.append(CovWij)
                mu_w.append(CovWij @ tmp / error_term)
        sigma_w = np.array(sigma_w).reshape(self.q, self.p, self.N, self.N)
        mu_w = np.array(mu_w)
        return sigma_f, mu_f, sigma_w, mu_w
    
    def _expectedLogLike_new(self, nodes, weight, means, jitters, 
                             sigma_f, mu_f, sigma_w, mu_w):
        """
            Calculates the expected log-likelihood in mean-field inference, 
        corresponds to eq.14 in Nguyen & Bonilla (2013)
            Parameters:
                nodes = array of node functions 
                weight = weight function
                jitters = jitters array
                sigma_f = array with the covariance for each node
                mu_f = array with the means for each node
                sigma_w = array with the covariance for each weight
                mu_w = array with the means for each weight
            Returns:
                expected log-likelihood
        """
        new_y = np.concatenate(self.y) - self._mean(means, self.time)
        new_y = np.array(np.array_split(new_y, self.p)).T #NxP dimensional vector
        
#        error_term = 0
#        for i in range(self.p):
#            error_term += jitters[i]**2 + (np.sum(self.yerr[i,:]**2))#/self.N)**2
#        error_term /= self.p
#        error_term = 1
        error_term = np.sqrt(np.sum(np.array(jitters)**2)) / self.p
        for i in range(self.p):
            error_term += np.sqrt(np.sum(self.yerr[i,:]**2)) / (self.N)
        error_term = error_term
        error_term = 1

        Wblk = np.array([])
        for n in range(self.N):
            for p in range(self.p):
                Wblk = np.append(Wblk, mu_w[p,:,n])
        Fblk = np.array([])
        for n in range(self.N):
            for q in range(self.q):
                for p in range(self.p):
#                    print(mu_f.shape)
                    Fblk = np.append(Fblk, mu_f[:, q, n])
        Ymean = (Wblk * Fblk)#.reshape(self.N, self.p)
        yy = np.array([])                           ###Start of sketchy part
        for i in range(self.q):
            yy = np.append(yy, new_y)
        new_y = yy                                  ###End of sketchy part
        Ydiff = (new_y - Ymean) * (new_y - Ymean)
        logl = -0.5 * np.sum(Ydiff) / error_term

#        #ORIGINAL
#        Wblk = np.array([])
#        for n in range(self.N):
#            for p in range(self.p):
#                Wblk = np.append(Wblk, mu_w[p,:,n])
#        Fblk = np.array([])
#        for n in range(self.N):
#            for q in range(self.q):
#                for p in range(self.p):
#                    Fblk = np.append(Fblk, mu_f[:,q,n])
#        Ymean = (Wblk * Fblk).reshape(self.N, self.p)
#        Ydiff = (new_y - Ymean) * (new_y - Ymean)
#        logl = -0.5 * np.sum(Ydiff) / error_term
#
#        value = 0
#        for i in range(self.p):
#            for j in range(self.q):
#                value += np.sum(np.diag(sigma_f[j,:,:]) * mu_w[i,j,:] * mu_w[i,j,:]) +\
#                    np.sum(np.diag(sigma_w[j,i,:,:]) * mu_f[j] * mu_f[j]) +\
#                    np.sum(np.diag(sigma_f[j,:,:]) * np.diag(sigma_w[j,i,:,:]))
#        logl += -0.5* value / error_term
        return logl
    
    def _expectedLogPrior(self, nodes, weights, sigma_f, mu_f, sigma_w, mu_w):
        """
            Calculates the expection of the log prior wrt q(f,w) in mean-field 
        inference, corresponds to eq.15 in Nguyen & Bonilla (2013)
            Parameters:
                nodes = array of node functions 
                weight = weight function
                sigma_f = array with the covariance for each node
                mu_f = array with the means for each node
                sigma_w = array with the covariance for each weight
                mu_w = array with the means for each weight
            Returns:
                expected log prior
        """
        Kf = np.array([self._kernelMatrix(i, self.time) for i in nodes])
        Kw = np.array([self._kernelMatrix(j, self.time) for j in weights]) 
        
        #we have Q nodes -> j in the paper; we have P y(x)s -> i in the paper
        first_term = 0 #calculation of the first term of eq.15 of Nguyen & Bonilla (2013)
        second_term = 0 #calculation of the second term of eq.15 of Nguyen & Bonilla (2013)
        Lw = self._cholNugget(Kw[0])[0]
        Kw_inv = inv(Kw[0])
        #logKw = -self.q * np.sum(np.log(np.diag(L2)))
        logKw = -np.float(np.sum(np.log(np.diag(Lw))))
        mu_w = mu_w.reshape(self.q, self.p, self.N)
        
        for j in range(self.q):
            Lf = self._cholNugget(Kf[j])[0]
            #logKf = - self.q * np.sum(np.log(np.diag(L1)))
            logKf = -np.float(np.sum(np.log(np.diag(Lf))))
            Kf_inv = inv(Kf[j])
#            print(mu_f.shape)
            muKmu = (Kf_inv @mu_f[:,j, :].reshape(self.N)) @mu_f[:,j, :].reshape(self.N)
            trace = np.trace(sigma_f[j] @Kf_inv)
            first_term += logKf -0.5*muKmu -0.5*trace
            for i in range(self.p):
                muKmu = (Kw_inv @mu_w[j,i])  @mu_w[j,i].T
                trace = np.trace(sigma_w[j, i, :, :] @Kw_inv)
                second_term += logKw -0.5*muKmu -0.5*trace
        return first_term + second_term
    
    def _entropy(self, sigma_f, sigma_w):
        """
            Calculates the entropy in mean-field inference, corresponds to 
        eq.14 in Nguyen & Bonilla (2013)
            Parameters:
                sigma_f = array with the covariance for each node
                sigma_w = array with the covariance for each weight
            Returns:
                ent_sum = final entropy
        """
        ent_sum = 0 #starts at zero then we sum everything
        for j in range(self.q):
            L1 = self._cholNugget(sigma_f[j])
            #print(np.diag(L1[0]))
            ent_sum += np.sum(np.log(np.diag(L1[0])))
            #print(ent_sum)
            for i in range(self.p):
                L2 = self._cholNugget(sigma_w[j, i, :, :])
                #print(np.diag(L2[0]))
                ent_sum += np.sum(np.log(np.diag(L2[0])))
                #print(ent_sum)
        return ent_sum


#    def _updateSigmaMu(self, nodes, weight, means, jitters, time,
#                               muF, varF, muW, varW):
#        """
#            Efficient closed-form updates fot variational parameters. This
#        corresponds to eqs. 16, 17, 18, and 19 of Nguyen & Bonilla (2013) 
#            Parameters:
#                nodes = array of node functions 
#                weight = weight function
#                jitters = jitters array
#                time = array containing the time
#                muF = array with the initial means for each node
#                varF = array with the initial variance for each node
#                muW = array with the initial means for each weight
#                varW = array with the initial variance for each weight
#            Returns:
#                sigma_f = array with the covariance for each node
#                mu_f = array with the means for each node
#                sigma_w = array with the covariance for each weight
#                mu_w = array with the means for each weight
#        """
#        new_y = np.concatenate(self.y) - self._mean(means)
#        new_y = np.array_split(new_y, self.p)
#        #new_y = self.y
#        
#        #kernel matrix for the nodes
#        Kf = np.array([self._kernelMatrix(i, time) for i in nodes])
#        invKf = []
#        for i in range(self.q):
#            invKf.append(inv(Kf[i]))
#        invKf = np.array(invKf) #inverse matrix of Kf
#        #kernel matrix for the weights
#        Kw = np.array([self._kernelMatrix(j, time) for j in weight]) 
#        invKw = []
#        for i,j in enumerate(Kw):
#            invKw = inv(j)
#        invKw = np.array(invKw) #inverse matrix of Kw
#        
#        #we have Q nodes => j in the paper; we have P y(x)s => i in the paper
#        sigma_f = [] #creation of Sigma_fj
#        for j in range(self.q):
#            muWmuWVarW = np.zeros((self.N, self.N))
#            for i in range(self.p):
#                muWmuWVarW += np.diag(muW[i, j, :] * muW[i, j, :] + varW[i, j, :])
##                error_term = jitters[i]**2 + (np.sum(self.yerr[i,:])/self.N)**2
#                error_term = 1
#            sigma_f.append(inv(invKf[j] + muWmuWVarW/error_term))
#        sigma_f = np.array(sigma_f)
#        #print(np.diag(np.squeeze(sigma_f)))
#        
#        muF = muF.reshape(self.q, self.N)
#        mu_f = [] #creation of mu_fj
#        for j in range(self.q):
#            sum_YminusSum = np.zeros(self.N)
#            for i in range(self.p):
##                error_term = jitters[i]**2 + (np.sum(self.yerr[i,:])/self.N)**2
#                error_term = 1
#                sum_muWmuF = np.zeros(self.N)
#                for k in range(self.q):
#                    if k != j:
#                        sum_muWmuF += np.array(muW[i, j, :]) * muF[j].reshape(self.N)
#                    sum_YminusSum += new_y[i][:] - sum_muWmuF
#                sum_YminusSum *= muW[i, j, :]
#            mu_f.append(np.dot(sigma_f[j], sum_YminusSum/error_term))
#        mu_f = np.array(mu_f)
#
#        sigma_w = [] #creation of Sigma_wij
#        for j in range(self.q):
#            muFmuFVarF = np.zeros((self.N, self.N))
#            for i in range(self.p):
##                error_term = jitters[i]**2 + (np.sum(self.yerr[i,:])/self.N)**2
#                error_term = 1
#                muFmuFVarF += np.diag(mu_f[j] * mu_f[j] + np.diag(sigma_f[j]))
#                sigma_w.append(inv(invKw + muFmuFVarF/error_term))
#        sigma_w = np.array(sigma_w).reshape(self.q, self.p, self.N, self.N)
#        
#        mu_w = [] #creation of mu_wij
#        for j in range(self.q):
#            sum_YminusSum = np.zeros(self.N)
#            for i in range(self.p):
#                sum_muFmuW = np.zeros(self.N)
#                for k in range(self.q):
#                    if k != j:
#                        sum_muFmuW += mu_f[j].reshape(self.N) * np.array(muW[i][j][:])
#                    sum_YminusSum += new_y[i][:] - sum_muFmuW
#                sum_YminusSum *= mu_f[j].reshape(self.N)
##                error = jitters[i]**2 + (np.sum(self.yerr[i,:])/self.N)**2
#                error = 1
#                mu_w.append(np.dot(sigma_w[j][i], sum_YminusSum/error))
#        mu_w = np.array(mu_w)
#        return sigma_f, mu_f, sigma_w, mu_w

#    def _expectedLogLike(self, nodes, weight, means, jitters, 
#                             sigma_f, mu_f, sigma_w, mu_w):
#        """
#            Calculates the expected log-likelihood in mean-field inference, 
#        corresponds to eq.14 in Nguyen & Bonilla (2013)
#            Parameters:
#                nodes = array of node functions 
#                weight = weight function
#                jitters = jitters array
#                sigma_f = array with the covariance for each node
#                mu_f = array with the means for each node
#                sigma_w = array with the covariance for each weight
#                mu_w = array with the means for each weight
#            Returns:
#                expected log-likelihood
#        """
#        new_y = np.concatenate(self.y) - self._mean(means, self.time)
#        new_y = np.array(np.array_split(new_y, self.p)) #Px1 dimensional vector
#        muw = mu_w.reshape(self.p, self.q, self.N) #PxQ dimensional vector
#        muf = mu_f.reshape(self.q, self.N) #Qx1 dimensional vector
#        
#        first_term = 0
#        second_term = 0
#        third_term = 0
#        for i in range(self.p):
##            first_term += np.log(jitters[i]**2 + (np.sum(self.yerr[i,:])/self.N)**2)
#            first_term += 1
#            for n in range(self.N):
##                error = jitters[i]**2 + self.yerr[i,n]**2
#                error = 1
#                #first_term += np.log(error)
#                YOmegaMu = np.array(new_y[i,n].T - muw[i,:,n] @ muf[:,n])
#                second_term += np.dot(YOmegaMu.T, YOmegaMu) / error
#            for j in range(self.q):
##### CHECK i,j of the weights!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#                first = np.diag(sigma_f[j,:,:]) * muw[i,j] @ muw[i,j]
#                second = np.diag(sigma_w[j,i,:,:]) * mu_f[j] @ mu_f[j].T
#                third = np.diag(sigma_f[j,:,:]) @ np.diag(sigma_w[j,i,:])
##                error = jitters[i]**2 + (np.sum(self.yerr[i,:])/self.N)**2
#                error = 1
#                third_term += (first + second[0][0] + third)/ error
#        first_term = -0.5 * first_term
#        second_term = -0.5 * second_term
#        third_term = -0.5 * third_term
#        return first_term + second_term + third_term


    def _plots(self, ELB, ELL, ELP, ENT):
        """
            Plots the evolution of the evidence lower bound, expected log 
        likelihood, expected log prior, and entropy
        """
        plt.figure()
        ax1 = plt.subplot(411)
        plt.plot(ELB, '-')
        plt.ylabel('Evidence lower bound')
        plt.subplot(412, sharex=ax1)
        plt.plot(ELL, '-')
        plt.ylabel('Expected log likelihood')
        plt.subplot(413, sharex=ax1)
        plt.plot(ELP, '-')
        plt.ylabel('Expected log prior')
        plt.subplot(414, sharex=ax1)
        plt.plot(ENT, '-')
        plt.ylabel('Entropy')
        plt.xlabel('iteration')
        plt.show()
        return 0


    def _prints(self, sum_ELB, ExpLogLike, ExpLogPrior, Entropy):
        """
            Prints the evidence lower bound, expected log likelihood, expected
        log prior, and entropy
        """
        print('ELB: ' + str(sum_ELB))
        print(' loglike: ' + str(ExpLogLike) + ' \n logprior: ' \
              + str(ExpLogPrior) + ' \n entropy: ' + str(Entropy) + ' \n')
        return 0


