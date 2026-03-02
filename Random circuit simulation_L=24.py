import numpy as np
import math
import itertools
from matplotlib import pyplot as plt
import matplotlib.patches as mpatches
import itertools
from scipy.optimize import curve_fit
import time
import pandas as pd
import multiprocessing as mp

def init_pool_processes():
    np.random.seed()
    
# Pauli matrices
s_x = np.array([[0,1.],[1,0]])
s_y = np.array([[0,-1j],[1j,0]])
s_z = np.array([[1.,0],[0,-1]])
Id = np.array([[1.,0],[0,1]])

# Gates
H = np.array([[1.,1.],[1.,-1.]])/np.sqrt(2) # Hardmard gate(two-qubit)

# Define a function that returns a d by d haar random gate
def haar_rand(d):
    A = np.random.randn(d,d) # an dxd array with random floats sampled from the "standard normal distribution"
    Q, R = np.linalg.qr(A) # QR decomposition, where Q is a unitary matrix and R is an upper triangular matrix
    diag = np.diag(R) # extract the diagonal elements to put in a 1D array
    Q = Q @ np.diag(diag/np.abs(diag)) # np.abs: take the absolute value of every element. # 1D array/1D array: elements are divided one by one.
    return Q                           # np.diag(1D array): put 1D array into a square zero matrix. Ex. np.diag(np.array([1,1,1,1,1,1]))


# Define a function that returns a random U(1)-conserving gate
def random_U1_gate():
    U = np.zeros((4,4), dtype = complex)
    U[0,0] = 1 # |00> is eigenstate, phase can be fixed to 0
    U[3,3] = np.exp(2*np.pi*1j*np.random.rand()) # |11> is eigenstate with random phase
    sl = slice(1,3) # slice(m,n): start from position m and stop at position (n-1). The first position labeled as 0!!!
    U[sl,sl] = haar_rand(2) # |01> and |10> have a nontrivial 2x2 block
    return U

def layer_U1(psi): # U(1) circuit
    for i0 in range(2): # even and odd layers
        for i in range(i0, L-1, 2): # loop over pairs of qubits
            U = random_U1_gate()
            dim_l = 2**i # dimension of Hilbert space to the left of i
            psi = psi.reshape(dim_l, 4, -1) # reshape into 3-index tensor
            psi = np.einsum("ij,ajb->aib", U, psi) # tensor contraction
    return psi.ravel() # reshape back to vector

def rho_H(LA,k): # Haar moment in the symmetric basis
  DA = 2**LA
  D_symm = math.comb(DA+k-1, k)
  R_H =  np.eye(D_symm)/D_symm
  return R_H

# k: number of replicas
def find_solutions(k, dim_A, current_solution, configs):
    if dim_A == 1:
        current_solution.append(k)
        configs.append(tuple(current_solution))
        current_solution.pop()
    else:
        for i in range(k + 1):
            current_solution.append(i)
            find_solutions(k - i, dim_A - 1, current_solution, configs)
            current_solution.pop()

def count_and_list_solutions(k, dim_A):
    configs = []
    find_solutions(k, dim_A, [], configs)
    return len(configs), configs
# configs is the list of non-negative solutions.

def moment_op(psi,L,LA,k):
  # L:system size
  # LA:subsystem size
  # psi:quantum state
  # k: number of replicas
  LB = L - LA # size of the complement ('bath')
  dim_A = 2**LA # dimension of the subsystem
  dim_B = 2**LB # dimension of the bath
  psi=psi.reshape(2**(LA),2**(LB))
  Norm = np.linalg.norm(psi, axis=0)
  P_z = Norm**2
  Norm[np.abs(Norm) < 10**(-10)] = 1.
  p = 1./Norm
  psi_z = np.einsum("ij,j->ij", psi, p) # normalize

  dim_symsub, configs = count_and_list_solutions(k, dim_A)
  configs = np.array(configs)
  factorial_vec = np.vectorize(math.factorial)
  N_ = np.sqrt(factorial_vec(configs).prod(1)*math.factorial(k)) # normalization constant

  psi_z = psi_z.reshape(1,dim_A,dim_B)
  configs = configs.reshape(dim_symsub,dim_A,1)
  norm = math.factorial(k)/(N_.reshape(dim_symsub,1))

  psi_z_k = (psi_z**configs).prod(1)*norm # replicated psi_z
  d=np.linalg.norm(psi_z_k, axis=0).sum() - dim_B # check the normalization, should be zero.

  out_product = np.einsum("ji,ki->ijk", psi_z_k, psi_z_k.conjugate())
  rho = np.einsum("ijk,i->jk",out_product,P_z)
  return rho#, d

def one_realization(arg):
    L = arg['L']
    LA = arg['LA']
    k = arg['k']
    T = arg['T']
    initial = arg['initial']
    
    row = []
    for t in range(T):
        if t==0:
            psi = initial
        else:
            psi = layer_U1(psi)
        rho = moment_op(psi,L,LA,k)
        dis= np.linalg.norm(rho-rho_H(LA,k),'nuc') / np.linalg.norm(rho_H(LA,k),'nuc') 
        row.append(dis)
    return row

if __name__ == '__main__':

    num_cores = mp.cpu_count()

    T = 600
    k = 2
    L = 24
    LA = 2
    N=num_cores #100
    
    #---------------create the initial state----------------------------
    th = np.pi/4
    two_qubit_state = np.array([np.cos(th)*np.sin(th),(np.cos(th))**2,(np.sin(th))**2,np.sin(th)*np.cos(th)]) # theta state
    initial = np.ones(1, dtype=complex)
    for i in range(0, L//2): # we assume L even
        initial = np.kron(initial, two_qubit_state) # tensor product
    #-------------------------------------------------------------------
    
    arg = {}
    arg['T'] = T
    arg['k'] = k
    arg['L'] = L
    arg['LA'] = LA
    arg['initial'] = initial

    with mp.Pool(num_cores, initializer=init_pool_processes) as pool:
        args = [arg for i in range(N)]
        results = pool.imap(one_realization, args)
        results_list = list(results)  # Collect all rows into a list
        results_array = np.array(results_list)  # Convert list of rows to a 2D NumPy array

results_array = results_array.mean(axis=0)

Tx = np.linspace(0,T-1,T)
#plt.loglog(Tx,results_array)
#plt.savefig(f"{L}_{LA}.pdf")
#plt.show()

Norm = {}
Norm["t"] = Tx
Norm[(LA,L)] = results_array

df = pd.DataFrame(Norm)
csv_file_path = f'L={L}_LA={LA}_N={N}_T={T}.csv'
df.to_csv(csv_file_path, index=False)